-- Subscription Renewal & Billing Cycle Continuity V1

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
  v_current public.subscriptions%rowtype;
  v_chain_end timestamptz;
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

  -- Determine the subscription that was active when the verified provider
  -- payment became paid. This avoids losing already-paid time if activation
  -- is delayed after the provider timestamp.
  select s.* into v_current
  from public.subscriptions s
  where s.user_id = v_payment.user_id
    and s.status = 'active'
    and s.current_period_start is not null
    and s.current_period_end is not null
    and s.current_period_start <= v_payment.paid_at
    and s.current_period_end > v_payment.paid_at
  order by s.current_period_end desc, s.updated_at desc
  limit 1;

  if found and v_current.plan_id = p_plan_id then
    -- Same-plan renewal is additive. Chain after the farthest already-paid
    -- active period for the same plan, including queued future renewals.
    select max(s.current_period_end)
    into v_chain_end
    from public.subscriptions s
    where s.user_id = v_payment.user_id
      and s.plan_id = p_plan_id
      and s.status = 'active'
      and s.current_period_end is not null
      and s.current_period_end > v_payment.paid_at;

    v_start := greatest(
      v_payment.paid_at,
      coalesce(v_chain_end, v_payment.paid_at)
    );

    -- Clean up any inconsistent overlapping active rows from other plans
    -- without touching the paid same-plan renewal chain.
    update public.subscriptions
    set status = 'cancelled',
        current_period_end = least(
          coalesce(current_period_end, clock_timestamp()),
          clock_timestamp()
        ),
        updated_at = clock_timestamp()
    where user_id = v_payment.user_id
      and status = 'active'
      and plan_id <> p_plan_id;
  else
    -- Plan changes remain immediate: the new paid plan starts at its verified
    -- paid_at timestamp and supersedes every previously active plan.
    v_start := v_payment.paid_at;

    update public.subscriptions
    set status = 'cancelled',
        current_period_end = least(
          coalesce(current_period_end, clock_timestamp()),
          clock_timestamp()
        ),
        updated_at = clock_timestamp()
    where user_id = v_payment.user_id
      and status = 'active';
  end if;

  v_end := case v_plan.billing_interval
    when 'month' then v_start + interval '1 month'
    when 'year' then v_start + interval '1 year'
    else null
  end;

  if v_end is null then
    raise exception 'unsupported_billing_interval'
      using errcode = 'P0001';
  end if;

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

revoke all on function public.activate_subscription_from_payment(uuid, text)
from public, anon, authenticated;

grant execute on function public.activate_subscription_from_payment(uuid, text)
to service_role;
