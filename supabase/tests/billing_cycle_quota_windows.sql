\set ON_ERROR_STOP on

-- Billing-Cycle Aligned Character Quota Windows PostgreSQL V1

begin;

insert into auth.users (id, email, raw_user_meta_data)
values
  ('58000000-0000-0000-0000-000000000001', 'quota-cycle-monthly@nadid.local', '{}'::jsonb),
  ('58000000-0000-0000-0000-000000000002', 'quota-cycle-annual@nadid.local', '{}'::jsonb),
  ('58000000-0000-0000-0000-000000000003', 'quota-cycle-free@nadid.local', '{}'::jsonb);

-- QUOTA-CYCLE-DB-001:
-- A paid monthly subscription that began before the calendar boundary must
-- retain the same quota bucket after the calendar month changes.
do $$
declare
  v_start timestamptz := date_trunc('month', clock_timestamp()) - interval '1 day';
  v_end timestamptz;
  v_window record;
  v_result record;
  v_operation uuid := '58000000-0000-4000-8000-000000000101';
begin
  v_end := v_start + interval '1 month';

  insert into public.subscriptions (
    user_id, plan_id, status, current_period_start, current_period_end
  )
  values (
    '58000000-0000-0000-0000-000000000001',
    'basic_monthly',
    'active',
    v_start,
    v_end
  );

  select * into v_window
  from public.resolve_character_quota_window(
    '58000000-0000-0000-0000-000000000001'
  );

  if v_window.plan_id <> 'basic_monthly'
     or v_window.period_start <> v_start::date
  then
    raise exception 'QUOTA-CYCLE-DB-001 monthly quota window lost billing anchor';
  end if;

  insert into public.character_usage_monthly (
    user_id, period_start, included_characters, used_characters, updated_at
  )
  values (
    '58000000-0000-0000-0000-000000000001',
    v_start::date,
    500000,
    400000,
    clock_timestamp()
  );

  select * into v_result
  from public.consume_character_quota(
    '58000000-0000-0000-0000-000000000001',
    v_operation,
    'analyze',
    150000
  );

  if v_result.allowed then
    raise exception 'QUOTA-CYCLE-DB-001 calendar boundary granted duplicate included quota';
  end if;

  if v_result.remaining_included <> 100000 then
    raise exception 'QUOTA-CYCLE-DB-001 wrong remaining balance in anchored window';
  end if;

  if exists (
    select 1
    from public.character_usage_monthly
    where user_id = '58000000-0000-0000-0000-000000000001'
      and period_start = date_trunc('month', clock_timestamp())::date
      and period_start <> v_start::date
  ) then
    raise exception 'QUOTA-CYCLE-DB-001 calendar-month bucket was created for paid user';
  end if;
end
$$;

-- QUOTA-CYCLE-DB-002:
-- Annual billing still receives monthly character windows, anchored to the
-- subscription anniversary rather than the first day of the calendar month.
do $$
declare
  v_start timestamptz := clock_timestamp() - interval '40 days';
  v_window record;
  v_expected date;
begin
  insert into public.subscriptions (
    user_id, plan_id, status, current_period_start, current_period_end
  )
  values (
    '58000000-0000-0000-0000-000000000002',
    'pro_yearly',
    'active',
    v_start,
    v_start + interval '1 year'
  );

  select * into v_window
  from public.resolve_character_quota_window(
    '58000000-0000-0000-0000-000000000002'
  );

  v_expected := (v_start + interval '1 month')::date;

  if v_window.plan_id <> 'pro_yearly' then
    raise exception 'QUOTA-CYCLE-DB-002 annual plan not resolved';
  end if;

  if v_window.period_start <> v_expected then
    raise exception 'QUOTA-CYCLE-DB-002 annual monthly window not anchored to anniversary';
  end if;

  if v_window.period_start = date_trunc('month', clock_timestamp())::date
     and v_window.period_start <> v_expected
  then
    raise exception 'QUOTA-CYCLE-DB-002 annual quota fell back to calendar month';
  end if;
end
$$;

-- QUOTA-CYCLE-DB-003:
-- A queued future renewal must not become effective before its period starts.
do $$
declare
  v_current_start timestamptz := clock_timestamp() - interval '5 days';
  v_current_end timestamptz := clock_timestamp() + interval '25 days';
  v_window record;
begin
  delete from public.subscriptions
  where user_id = '58000000-0000-0000-0000-000000000001';

  insert into public.subscriptions (
    user_id, plan_id, status, current_period_start, current_period_end
  )
  values
    (
      '58000000-0000-0000-0000-000000000001',
      'basic_monthly',
      'active',
      v_current_start,
      v_current_end
    ),
    (
      '58000000-0000-0000-0000-000000000001',
      'basic_monthly',
      'active',
      v_current_end,
      v_current_end + interval '1 month'
    );

  select * into v_window
  from public.resolve_character_quota_window(
    '58000000-0000-0000-0000-000000000001'
  );

  if v_window.period_start <> v_current_start::date then
    raise exception 'QUOTA-CYCLE-DB-003 future renewal activated quota early';
  end if;
end
$$;

-- QUOTA-CYCLE-DB-004:
-- Free users have no billing anchor, so the calendar month remains correct.
do $$
declare
  v_window record;
begin
  select * into v_window
  from public.resolve_character_quota_window(
    '58000000-0000-0000-0000-000000000003'
  );

  if v_window.plan_id <> 'free_monthly'
     or v_window.period_start <> date_trunc('month', clock_timestamp())::date
  then
    raise exception 'QUOTA-CYCLE-DB-004 free quota window changed unexpectedly';
  end if;
end
$$;

-- QUOTA-CYCLE-DB-005:
-- Clients cannot choose or inspect privileged quota-window resolution directly.
do $$
begin
  if has_function_privilege(
    'authenticated',
    'public.resolve_character_quota_window(uuid)',
    'EXECUTE'
  ) then
    raise exception 'QUOTA-CYCLE-DB-005 authenticated can execute quota window resolver';
  end if;
end
$$;

-- QUOTA-CYCLE-DB-006:
-- Existing quota consumption RPC remains service-role only.
do $$
begin
  if has_function_privilege(
    'authenticated',
    'public.consume_character_quota(uuid,uuid,text,bigint)',
    'EXECUTE'
  ) then
    raise exception 'QUOTA-CYCLE-DB-006 authenticated can execute quota consumption';
  end if;
end
$$;

rollback;

select 'Billing-Cycle Aligned Character Quota Windows PostgreSQL V1: PASS' as result;
