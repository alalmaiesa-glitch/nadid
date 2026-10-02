-- Partial Capture & Partial Refund Semantics V1

alter table public.payments
  drop constraint if exists payments_status_check;

alter table public.payments
  add constraint payments_status_check
  check (status in (
    'pending',
    'paid',
    'failed',
    'partially_refunded',
    'refunded',
    'voided'
  ));

alter table public.payments
  add column if not exists captured_minor bigint not null default 0,
  add column if not exists refunded_minor bigint not null default 0;

alter table public.payments
  drop constraint if exists payments_captured_minor_check;
alter table public.payments
  add constraint payments_captured_minor_check
  check (captured_minor >= 0 and captured_minor <= amount_minor);

alter table public.payments
  drop constraint if exists payments_refunded_minor_check;
alter table public.payments
  add constraint payments_refunded_minor_check
  check (refunded_minor >= 0 and refunded_minor <= amount_minor);

drop function if exists public.apply_payment_webhook_event(
  text, text, text, text, bigint, text, boolean, timestamptz, text
);

create or replace function public.apply_payment_webhook_event(
  p_provider text,
  p_event_id text,
  p_event_type text,
  p_provider_payment_id text,
  p_amount_minor bigint,
  p_currency text,
  p_captured_minor bigint,
  p_refunded_minor bigint,
  p_live boolean,
  p_occurred_at timestamptz,
  p_payload_digest text
)
returns table (
  local_payment_id uuid,
  reused boolean,
  outcome text,
  purpose text,
  payment_metadata jsonb
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_existing public.payment_webhook_events%rowtype;
  v_payment public.payments%rowtype;
  v_outcome text;
begin
  if coalesce(length(trim(p_provider)), 0) = 0
     or coalesce(length(trim(p_event_id)), 0) = 0
     or coalesce(length(trim(p_event_type)), 0) = 0
     or coalesce(length(trim(p_provider_payment_id)), 0) = 0
     or coalesce(length(trim(p_payload_digest)), 0) = 0
     or p_live is null
  then
    raise exception 'invalid_webhook_event'
      using errcode = 'P0001';
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended(lower(trim(p_provider)) || ':' || trim(p_event_id), 33001)
  );

  select * into v_existing
  from public.payment_webhook_events
  where provider = lower(trim(p_provider))
    and provider_event_id = trim(p_event_id)
  limit 1;

  if found then
    if v_existing.payload_digest <> p_payload_digest
       or v_existing.event_type <> p_event_type
       or coalesce(v_existing.provider_payment_id, '') <> trim(p_provider_payment_id)
       or v_existing.live is distinct from p_live
    then
      raise exception 'webhook_event_replay_mismatch'
        using errcode = 'P0001';
    end if;

    if v_existing.local_payment_id is null then
      return query
      select null::uuid, true, v_existing.outcome, null::text, '{}'::jsonb;
      return;
    end if;

    select * into v_payment
    from public.payments
    where id = v_existing.local_payment_id;

    return query
    select
      v_existing.local_payment_id,
      true,
      v_existing.outcome,
      v_payment.purpose,
      v_payment.metadata;
    return;
  end if;

  insert into public.payment_webhook_events (
    provider,
    provider_event_id,
    event_type,
    provider_payment_id,
    live,
    payload_digest
  )
  values (
    lower(trim(p_provider)),
    trim(p_event_id),
    trim(p_event_type),
    trim(p_provider_payment_id),
    p_live,
    p_payload_digest
  )
  returning * into v_existing;

  select * into v_payment
  from public.payments
  where provider = lower(trim(p_provider))
    and provider_payment_id = trim(p_provider_payment_id)
  for update;

  if not found then
    update public.payment_webhook_events
    set outcome = 'unmatched',
        processed_at = clock_timestamp()
    where id = v_existing.id;

    return query
    select null::uuid, false, 'unmatched'::text, null::text, '{}'::jsonb;
    return;
  end if;

  update public.payment_webhook_events
  set local_payment_id = v_payment.id
  where id = v_existing.id;

  if (p_live and v_payment.provider_mode <> 'live')
     or ((not p_live) and v_payment.provider_mode <> 'test')
  then
    update public.payment_webhook_events
    set outcome = 'rejected_mismatch',
        processed_at = clock_timestamp()
    where id = v_existing.id;

    return query
    select
      v_payment.id,
      false,
      'rejected_mismatch'::text,
      v_payment.purpose,
      v_payment.metadata;
    return;
  end if;

  -- Every payment event carries the provider's original payment amount and
  -- currency. A mismatch is never allowed to mutate local financial state.
  if p_amount_minor is null
     or p_currency is null
     or v_payment.amount_minor <> p_amount_minor
     or upper(v_payment.currency) <> upper(p_currency)
  then
    update public.payment_webhook_events
    set outcome = 'rejected_mismatch',
        processed_at = clock_timestamp()
    where id = v_existing.id;

    return query
    select
      v_payment.id,
      false,
      'rejected_mismatch'::text,
      v_payment.purpose,
      v_payment.metadata;
    return;
  end if;

  if p_event_type = 'payment_paid' then
    if v_payment.status in (
      'partially_refunded',
      'refunded',
      'voided'
    ) then
      v_outcome := 'ignored';
    elsif v_payment.status = 'paid' then
      v_outcome := 'applied';
    else
      update public.payments
      set status = 'paid',
          captured_minor = amount_minor,
          paid_at = coalesce(p_occurred_at, clock_timestamp()),
          updated_at = clock_timestamp()
      where id = v_payment.id;
      v_outcome := 'applied';
    end if;

  elsif p_event_type = 'payment_captured' then
    if p_captured_minor is null
       or p_captured_minor <> v_payment.amount_minor
    then
      v_outcome := 'rejected_mismatch';
    elsif v_payment.status in (
      'partially_refunded',
      'refunded',
      'voided'
    ) then
      v_outcome := 'ignored';
    elsif v_payment.status = 'paid' then
      v_outcome := 'applied';
    else
      update public.payments
      set status = 'paid',
          captured_minor = p_captured_minor,
          paid_at = coalesce(p_occurred_at, clock_timestamp()),
          updated_at = clock_timestamp()
      where id = v_payment.id;
      v_outcome := 'applied';
    end if;

  elsif p_event_type = 'payment_refunded' then
    if p_refunded_minor is null
       or p_refunded_minor <= 0
       or p_refunded_minor > v_payment.amount_minor
    then
      v_outcome := 'rejected_mismatch';
    elsif v_payment.status = 'voided' then
      v_outcome := 'ignored';
    else
      update public.payments
      set status = case
            when p_refunded_minor = amount_minor then 'refunded'
            else 'partially_refunded'
          end,
          refunded_minor = greatest(refunded_minor, p_refunded_minor),
          updated_at = clock_timestamp()
      where id = v_payment.id;

      -- V1 is deliberately conservative: any monetary refund removes future
      -- entitlement. Historical usage stays immutable for audit.
      update public.subscriptions
      set status = 'cancelled',
          current_period_end = least(
            coalesce(current_period_end, clock_timestamp()),
            clock_timestamp()
          ),
          updated_at = clock_timestamp()
      where payment_id = v_payment.id
        and status = 'active';

      update public.credit_topups
      set status = 'refunded',
          characters_remaining = 0,
          updated_at = clock_timestamp()
      where payment_id = v_payment.id
        and status in ('pending', 'available', 'consumed');

      v_outcome := 'applied';
    end if;

  elsif p_event_type = 'payment_voided' then
    update public.payments
    set status = 'voided',
        updated_at = clock_timestamp()
    where id = v_payment.id;

    update public.subscriptions
    set status = 'cancelled',
        current_period_end = least(
          coalesce(current_period_end, clock_timestamp()),
          clock_timestamp()
        ),
        updated_at = clock_timestamp()
    where payment_id = v_payment.id
      and status = 'active';

    update public.credit_topups
    set status = 'voided',
        characters_remaining = 0,
        updated_at = clock_timestamp()
    where payment_id = v_payment.id
      and status in ('pending', 'available', 'consumed');

    v_outcome := 'applied';

  elsif p_event_type in ('payment_failed', 'payment_faild') then
    if v_payment.status = 'pending' then
      update public.payments
      set status = 'failed',
          updated_at = clock_timestamp()
      where id = v_payment.id;
      v_outcome := 'applied';
    else
      v_outcome := 'ignored';
    end if;

  else
    v_outcome := 'ignored';
  end if;

  update public.payment_webhook_events
  set outcome = v_outcome,
      processed_at = clock_timestamp()
  where id = v_existing.id;

  select * into v_payment
  from public.payments
  where id = v_payment.id;

  return query
  select
    v_payment.id,
    false,
    v_outcome,
    v_payment.purpose,
    v_payment.metadata;
end;
$$;

revoke all on function public.apply_payment_webhook_event(
  text, text, text, text, bigint, text, bigint, bigint,
  boolean, timestamptz, text
) from public, anon, authenticated;

grant execute on function public.apply_payment_webhook_event(
  text, text, text, text, bigint, text, bigint, bigint,
  boolean, timestamptz, text
) to service_role;
