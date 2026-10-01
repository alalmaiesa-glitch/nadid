-- Payment & Subscription Activation Integrity V1

alter table public.payments
  drop constraint if exists payments_purpose_check;

alter table public.payments
  add constraint payments_purpose_check
  check (purpose in ('service', 'subscription', 'credit_topup'));

alter table public.subscriptions
  add column if not exists payment_id uuid null
    references public.payments(id) on delete set null;

create unique index if not exists subscriptions_payment_unique_idx
  on public.subscriptions(payment_id)
  where payment_id is not null;

create unique index if not exists credit_topups_payment_unique_idx
  on public.credit_topups(payment_id)
  where payment_id is not null;

create or replace function public.activate_subscription_from_payment(
  p_payment_id uuid,
  p_plan_id text
)
returns table (
  subscription_id uuid,
  reused boolean,
  period_start timestamptz,
  period_end timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_payment public.payments%rowtype;
  v_plan public.billing_plans%rowtype;
  v_existing public.subscriptions%rowtype;
  v_start timestamptz;
  v_end timestamptz;
  v_subscription_id uuid;
begin
  if p_payment_id is null or coalesce(length(trim(p_plan_id)), 0) = 0 then
    raise exception 'invalid_subscription_activation_request'
      using errcode = 'P0001';
  end if;

  select * into v_payment
  from public.payments
  where id = p_payment_id
  for update;

  if not found then
    raise exception 'payment_not_found' using errcode = 'P0001';
  end if;

  if v_payment.user_id is null
     or v_payment.status <> 'paid'
     or v_payment.purpose <> 'subscription'
     or v_payment.paid_at is null
  then
    raise exception 'payment_not_eligible_for_subscription'
      using errcode = 'P0001';
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended(v_payment.user_id::text, 32001)
  );

  select * into v_existing
  from public.subscriptions
  where payment_id = p_payment_id
  limit 1;

  if found then
    if v_existing.plan_id <> p_plan_id then
      raise exception 'payment_already_used_for_different_plan'
        using errcode = 'P0001';
    end if;

    return query
    select
      v_existing.id,
      true,
      v_existing.current_period_start,
      v_existing.current_period_end;
    return;
  end if;

  select * into v_plan
  from public.billing_plans
  where id = p_plan_id
    and active = true;

  if not found or v_plan.tier = 'free' then
    raise exception 'paid_plan_not_found'
      using errcode = 'P0001';
  end if;

  if v_payment.amount_minor <> v_plan.amount_minor
     or upper(v_payment.currency) <> upper(v_plan.currency)
  then
    raise exception 'payment_amount_or_currency_mismatch'
      using errcode = 'P0001';
  end if;

  v_start := v_payment.paid_at;
  v_end := case v_plan.billing_interval
    when 'month' then v_start + interval '1 month'
    when 'year' then v_start + interval '1 year'
    else null
  end;

  if v_end is null then
    raise exception 'unsupported_billing_interval'
      using errcode = 'P0001';
  end if;

  update public.subscriptions
  set status = 'cancelled',
      current_period_end = least(
        coalesce(current_period_end, clock_timestamp()),
        clock_timestamp()
      ),
      updated_at = clock_timestamp()
  where user_id = v_payment.user_id
    and status = 'active';

  insert into public.subscriptions (
    user_id,
    plan_id,
    payment_id,
    provider,
    provider_reference,
    status,
    current_period_start,
    current_period_end,
    created_at,
    updated_at
  )
  values (
    v_payment.user_id,
    v_plan.id,
    v_payment.id,
    v_payment.provider,
    v_payment.provider_payment_id,
    'active',
    v_start,
    v_end,
    clock_timestamp(),
    clock_timestamp()
  )
  returning id into v_subscription_id;

  return query
  select v_subscription_id, false, v_start, v_end;
end;
$$;

create or replace function public.activate_topup_from_payment(
  p_payment_id uuid,
  p_pack_id text
)
returns table (
  topup_id uuid,
  reused boolean,
  characters_remaining bigint
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_payment public.payments%rowtype;
  v_pack public.credit_packs%rowtype;
  v_existing public.credit_topups%rowtype;
  v_topup_id uuid;
begin
  if p_payment_id is null or coalesce(length(trim(p_pack_id)), 0) = 0 then
    raise exception 'invalid_topup_activation_request'
      using errcode = 'P0001';
  end if;

  select * into v_payment
  from public.payments
  where id = p_payment_id
  for update;

  if not found then
    raise exception 'payment_not_found' using errcode = 'P0001';
  end if;

  if v_payment.user_id is null
     or v_payment.status <> 'paid'
     or v_payment.purpose <> 'credit_topup'
     or v_payment.paid_at is null
  then
    raise exception 'payment_not_eligible_for_topup'
      using errcode = 'P0001';
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended(v_payment.user_id::text, 32002)
  );

  select * into v_existing
  from public.credit_topups
  where payment_id = p_payment_id
  limit 1;

  if found then
    if v_existing.pack_id <> p_pack_id then
      raise exception 'payment_already_used_for_different_pack'
        using errcode = 'P0001';
    end if;

    return query
    select
      v_existing.id,
      true,
      v_existing.characters_remaining;
    return;
  end if;

  select * into v_pack
  from public.credit_packs
  where id = p_pack_id
    and active = true;

  if not found then
    raise exception 'credit_pack_not_found'
      using errcode = 'P0001';
  end if;

  if v_payment.amount_minor <> v_pack.amount_minor
     or upper(v_payment.currency) <> upper(v_pack.currency)
  then
    raise exception 'payment_amount_or_currency_mismatch'
      using errcode = 'P0001';
  end if;

  insert into public.credit_topups (
    user_id,
    pack_id,
    payment_id,
    characters_total,
    characters_remaining,
    status,
    activated_at,
    created_at,
    updated_at
  )
  values (
    v_payment.user_id,
    v_pack.id,
    v_payment.id,
    v_pack.characters,
    v_pack.characters,
    'available',
    clock_timestamp(),
    clock_timestamp(),
    clock_timestamp()
  )
  returning id into v_topup_id;

  return query
  select v_topup_id, false, v_pack.characters;
end;
$$;

revoke all on function public.activate_subscription_from_payment(uuid, text)
from public, anon, authenticated;
revoke all on function public.activate_topup_from_payment(uuid, text)
from public, anon, authenticated;

grant execute on function public.activate_subscription_from_payment(uuid, text)
to service_role;
grant execute on function public.activate_topup_from_payment(uuid, text)
to service_role;
