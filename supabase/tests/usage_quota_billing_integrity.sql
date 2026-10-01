\set ON_ERROR_STOP on

-- Usage Quota Accounting & Billing Integrity PostgreSQL V1

begin;

insert into auth.users (id, email, raw_user_meta_data)
values
  ('52000000-0000-0000-0000-000000000001', 'quota-free@nadid.local', '{}'::jsonb),
  ('52000000-0000-0000-0000-000000000002', 'quota-pro@nadid.local', '{}'::jsonb);

insert into public.subscriptions (
  user_id, plan_id, status, current_period_start, current_period_end
)
values (
  '52000000-0000-0000-0000-000000000002',
  'pro_monthly',
  'active',
  now() - interval '1 day',
  now() + interval '29 days'
);

insert into public.credit_topups (
  user_id, pack_id, characters_total, characters_remaining,
  status, activated_at
)
values (
  '52000000-0000-0000-0000-000000000001',
  'topup_100k',
  100000,
  100000,
  'available',
  now()
);

-- QUOTA-DB-001: free plan falls back to 50,000 included characters.
do $$
declare
  r record;
begin
  select * into r
  from public.consume_character_quota(
    '52000000-0000-0000-0000-000000000001',
    '52000000-0000-0000-0000-000000000101',
    'analyze',
    40000
  );

  if not r.allowed or r.included_used <> 40000 or r.topup_used <> 0 then
    raise exception 'QUOTA-DB-001 free included quota failed';
  end if;

  if r.remaining_included <> 10000 then
    raise exception 'QUOTA-DB-001 remaining included mismatch';
  end if;
end
$$;

-- QUOTA-DB-002: same operation is idempotent and is not charged twice.
do $$
declare
  r record;
  v_used bigint;
begin
  select * into r
  from public.consume_character_quota(
    '52000000-0000-0000-0000-000000000001',
    '52000000-0000-0000-0000-000000000101',
    'analyze',
    40000
  );

  if not r.allowed or not r.already_charged then
    raise exception 'QUOTA-DB-002 idempotency flag missing';
  end if;

  select used_characters into v_used
  from public.character_usage_monthly
  where user_id = '52000000-0000-0000-0000-000000000001'
    and period_start = date_trunc('month', now())::date;

  if v_used <> 40000 then
    raise exception 'QUOTA-DB-002 duplicate charge detected';
  end if;
end
$$;

-- QUOTA-DB-003: included balance is consumed before top-up credits.
do $$
declare
  r record;
begin
  select * into r
  from public.consume_character_quota(
    '52000000-0000-0000-0000-000000000001',
    '52000000-0000-0000-0000-000000000102',
    'analyze',
    25000
  );

  if not r.allowed or r.included_used <> 10000 or r.topup_used <> 15000 then
    raise exception 'QUOTA-DB-003 included/topup order failed';
  end if;

  if (
    select characters_remaining
    from public.credit_topups
    where user_id = '52000000-0000-0000-0000-000000000001'
      and status = 'available'
    order by created_at
    limit 1
  ) <> 85000 then
    raise exception 'QUOTA-DB-003 topup debit mismatch';
  end if;
end
$$;

-- QUOTA-DB-004: insufficient total balance fails without partial mutation.
do $$
declare
  r record;
  before_usage bigint;
  before_topup bigint;
  after_usage bigint;
  after_topup bigint;
begin
  select used_characters into before_usage
  from public.character_usage_monthly
  where user_id = '52000000-0000-0000-0000-000000000001'
    and period_start = date_trunc('month', now())::date;

  select coalesce(sum(characters_remaining), 0) into before_topup
  from public.credit_topups
  where user_id = '52000000-0000-0000-0000-000000000001'
    and status = 'available';

  select * into r
  from public.consume_character_quota(
    '52000000-0000-0000-0000-000000000001',
    '52000000-0000-0000-0000-000000000103',
    'analyze',
    90000
  );

  if r.allowed then
    raise exception 'QUOTA-DB-004 insufficient balance allowed';
  end if;

  select used_characters into after_usage
  from public.character_usage_monthly
  where user_id = '52000000-0000-0000-0000-000000000001'
    and period_start = date_trunc('month', now())::date;

  select coalesce(sum(characters_remaining), 0) into after_topup
  from public.credit_topups
  where user_id = '52000000-0000-0000-0000-000000000001'
    and status = 'available';

  if before_usage <> after_usage or before_topup <> after_topup then
    raise exception 'QUOTA-DB-004 partial debit detected';
  end if;

  if exists (
    select 1 from public.character_usage_events
    where operation_id = '52000000-0000-0000-0000-000000000103'
  ) then
    raise exception 'QUOTA-DB-004 rejected operation was ledgered';
  end if;
end
$$;

-- QUOTA-DB-005: active paid subscription resolves its larger allowance.
do $$
declare
  r record;
begin
  select * into r
  from public.consume_character_quota(
    '52000000-0000-0000-0000-000000000002',
    '52000000-0000-0000-0000-000000000201',
    'analyze',
    1500000
  );

  if not r.allowed or r.included_used <> 1500000 or r.topup_used <> 0 then
    raise exception 'QUOTA-DB-005 pro entitlement not used';
  end if;

  if r.remaining_included <> 500000 then
    raise exception 'QUOTA-DB-005 pro remaining mismatch';
  end if;
end
$$;

-- QUOTA-DB-006: direct authenticated execution of privileged RPC is denied.
do $$
begin
  if has_function_privilege(
    'authenticated',
    'public.consume_character_quota(uuid,uuid,text,bigint)',
    'EXECUTE'
  ) then
    raise exception 'QUOTA-DB-006 authenticated can execute quota RPC';
  end if;
end
$$;

-- QUOTA-DB-007: ledger has one row per successful operation.
do $$
begin
  if (
    select count(*)
    from public.character_usage_events
    where user_id = '52000000-0000-0000-0000-000000000001'
  ) <> 2 then
    raise exception 'QUOTA-DB-007 ledger count mismatch';
  end if;
end
$$;

rollback;

select 'Usage Quota Accounting & Billing Integrity PostgreSQL V1: PASS' as result;
