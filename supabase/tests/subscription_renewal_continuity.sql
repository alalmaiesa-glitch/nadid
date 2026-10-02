\set ON_ERROR_STOP on

-- Subscription Renewal & Billing Cycle Continuity PostgreSQL V1

begin;

insert into auth.users (id, email, raw_user_meta_data)
values (
  '57000000-0000-0000-0000-000000000001',
  'renewal@nadid.local',
  '{}'::jsonb
);

-- RENEW-DB-001: first activation starts from verified paid_at.
do $$
declare
  intent record;
  activated record;
  v_paid_at timestamptz := clock_timestamp();
begin
  select * into intent
  from public.create_payment_intent(
    '57000000-0000-0000-0000-000000000001',
    'subscription',
    'basic_monthly',
    '57000000-0000-4000-8000-000000000101',
    'test'
  );

  perform *
  from public.apply_payment_webhook_event(
    'moyasar',
    'renew-first-paid',
    'payment_paid',
    intent.payment_id::text,
    2900,
    'SAR',
    2900,
    0,
    false,
    v_paid_at,
    'renew-first-paid-digest'
  );

  select * into activated
  from public.activate_subscription_from_payment(
    intent.payment_id,
    'basic_monthly'
  );

  if activated.reused then
    raise exception 'RENEW-DB-001 first activation reused unexpectedly';
  end if;

  if activated.period_start <> v_paid_at then
    raise exception 'RENEW-DB-001 first activation did not start at paid_at';
  end if;
end
$$;

-- RENEW-DB-002: early same-plan renewal starts exactly after current paid term.
do $$
declare
  v_first public.subscriptions%rowtype;
  intent record;
  activated record;
begin
  select * into v_first
  from public.subscriptions
  where user_id = '57000000-0000-0000-0000-000000000001'
    and plan_id = 'basic_monthly'
  order by created_at
  limit 1;

  select * into intent
  from public.create_payment_intent(
    '57000000-0000-0000-0000-000000000001',
    'subscription',
    'basic_monthly',
    '57000000-0000-4000-8000-000000000102',
    'test'
  );

  perform *
  from public.apply_payment_webhook_event(
    'moyasar',
    'renew-second-paid',
    'payment_paid',
    intent.payment_id::text,
    2900,
    'SAR',
    2900,
    0,
    false,
    v_first.current_period_start + interval '10 days',
    'renew-second-paid-digest'
  );

  select * into activated
  from public.activate_subscription_from_payment(
    intent.payment_id,
    'basic_monthly'
  );

  if activated.period_start <> v_first.current_period_end then
    raise exception 'RENEW-DB-002 early renewal discarded paid time';
  end if;

  if activated.period_end <> v_first.current_period_end + interval '1 month' then
    raise exception 'RENEW-DB-002 renewal duration incorrect';
  end if;

  if (
    select status from public.subscriptions where id = v_first.id
  ) <> 'active' then
    raise exception 'RENEW-DB-002 current same-plan period was cancelled';
  end if;
end
$$;

-- RENEW-DB-003: a third early renewal chains after the queued renewal.
do $$
declare
  v_latest_end timestamptz;
  v_reference_start timestamptz;
  intent record;
  activated record;
begin
  select
    max(current_period_end),
    min(current_period_start)
  into v_latest_end, v_reference_start
  from public.subscriptions
  where user_id = '57000000-0000-0000-0000-000000000001'
    and plan_id = 'basic_monthly'
    and status = 'active';

  select * into intent
  from public.create_payment_intent(
    '57000000-0000-0000-0000-000000000001',
    'subscription',
    'basic_monthly',
    '57000000-0000-4000-8000-000000000103',
    'test'
  );

  perform *
  from public.apply_payment_webhook_event(
    'moyasar',
    'renew-third-paid',
    'payment_paid',
    intent.payment_id::text,
    2900,
    'SAR',
    2900,
    0,
    false,
    v_reference_start + interval '15 days',
    'renew-third-paid-digest'
  );

  select * into activated
  from public.activate_subscription_from_payment(
    intent.payment_id,
    'basic_monthly'
  );

  if activated.period_start <> v_latest_end then
    raise exception 'RENEW-DB-003 queued renewal chain overlapped';
  end if;

  if activated.period_end <> v_latest_end + interval '1 month' then
    raise exception 'RENEW-DB-003 third renewal duration incorrect';
  end if;
end
$$;

-- RENEW-DB-004: replaying the same payment cannot extend the chain twice.
do $$
declare
  v_payment_id uuid;
  first_result record;
  second_result record;
  v_count_before bigint;
  v_count_after bigint;
begin
  select payment_id into v_payment_id
  from public.subscriptions
  where user_id = '57000000-0000-0000-0000-000000000001'
    and plan_id = 'basic_monthly'
  order by current_period_end desc
  limit 1;

  select count(*) into v_count_before
  from public.subscriptions
  where user_id = '57000000-0000-0000-0000-000000000001';

  select * into first_result
  from public.activate_subscription_from_payment(
    v_payment_id,
    'basic_monthly'
  );

  select * into second_result
  from public.activate_subscription_from_payment(
    v_payment_id,
    'basic_monthly'
  );

  select count(*) into v_count_after
  from public.subscriptions
  where user_id = '57000000-0000-0000-0000-000000000001';

  if not first_result.reused or not second_result.reused then
    raise exception 'RENEW-DB-004 replay was not idempotent';
  end if;

  if v_count_after <> v_count_before then
    raise exception 'RENEW-DB-004 replay created extra subscription';
  end if;

  if first_result.period_end <> second_result.period_end then
    raise exception 'RENEW-DB-004 replay changed period';
  end if;
end
$$;

-- RENEW-DB-005: plan change remains immediate and cancels old active chain.
do $$
declare
  intent record;
  activated record;
  v_paid_at timestamptz := clock_timestamp();
begin
  select * into intent
  from public.create_payment_intent(
    '57000000-0000-0000-0000-000000000001',
    'subscription',
    'pro_monthly',
    '57000000-0000-4000-8000-000000000104',
    'test'
  );

  perform *
  from public.apply_payment_webhook_event(
    'moyasar',
    'renew-plan-change-paid',
    'payment_paid',
    intent.payment_id::text,
    5900,
    'SAR',
    5900,
    0,
    false,
    v_paid_at,
    'renew-plan-change-paid-digest'
  );

  select * into activated
  from public.activate_subscription_from_payment(
    intent.payment_id,
    'pro_monthly'
  );

  if activated.period_start <> v_paid_at then
    raise exception 'RENEW-DB-005 plan change did not start immediately';
  end if;

  if exists (
    select 1
    from public.subscriptions
    where user_id = '57000000-0000-0000-0000-000000000001'
      and plan_id = 'basic_monthly'
      and status = 'active'
  ) then
    raise exception 'RENEW-DB-005 old plan chain remained active';
  end if;
end
$$;

-- RENEW-DB-006: authenticated clients still cannot execute activation.
do $$
begin
  if has_function_privilege(
    'authenticated',
    'public.activate_subscription_from_payment(uuid,text)',
    'EXECUTE'
  ) then
    raise exception 'RENEW-DB-006 authenticated can activate subscription';
  end if;
end
$$;

rollback;

select 'Subscription Renewal & Billing Cycle Continuity PostgreSQL V1: PASS' as result;
