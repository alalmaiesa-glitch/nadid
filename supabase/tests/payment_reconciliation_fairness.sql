\set ON_ERROR_STOP on

-- Payment Reconciliation Fairness, Claiming & Starvation Safety PostgreSQL V1

begin;

insert into auth.users (id, email, raw_user_meta_data)
values ('59000000-0000-0000-0000-000000000001', 'recon-fairness@nadid.local', '{}'::jsonb);

insert into public.payments (
  id, user_id, purpose, provider, provider_payment_id,
  amount_minor, currency, status, updated_at, reconciliation_checked_at
)
values
  ('59000000-0000-0000-0000-000000000101','59000000-0000-0000-0000-000000000001','subscription','moyasar','fair-101',2900,'SAR','paid',clock_timestamp()-interval '5 days',null),
  ('59000000-0000-0000-0000-000000000102','59000000-0000-0000-0000-000000000001','subscription','moyasar','fair-102',2900,'SAR','paid',clock_timestamp()-interval '4 days',null),
  ('59000000-0000-0000-0000-000000000103','59000000-0000-0000-0000-000000000001','subscription','moyasar','fair-103',2900,'SAR','paid',clock_timestamp()-interval '3 days',null),
  ('59000000-0000-0000-0000-000000000104','59000000-0000-0000-0000-000000000001','subscription','moyasar','fair-104',2900,'SAR','paid',clock_timestamp()-interval '2 days',null),
  ('59000000-0000-0000-0000-000000000105','59000000-0000-0000-0000-000000000001','subscription','moyasar','fair-105',2900,'SAR','paid',clock_timestamp()-interval '1 day',null);

-- RECON-FAIR-DB-001: first claim returns the oldest never-checked rows.
do $$
declare
  ids uuid[];
begin
  select array_agg(id order by id) into ids
  from public.claim_payment_reconciliation_batch(2);

  if ids <> array[
    '59000000-0000-0000-0000-000000000101'::uuid,
    '59000000-0000-0000-0000-000000000102'::uuid
  ] then
    raise exception 'RECON-FAIR-DB-001 first fair claim mismatch: %', ids;
  end if;
end
$$;

-- RECON-FAIR-DB-002: second claim rotates to rows that have never been checked.
do $$
declare
  ids uuid[];
begin
  select array_agg(id order by id) into ids
  from public.claim_payment_reconciliation_batch(2);

  if ids <> array[
    '59000000-0000-0000-0000-000000000103'::uuid,
    '59000000-0000-0000-0000-000000000104'::uuid
  ] then
    raise exception 'RECON-FAIR-DB-002 starvation rotation failed: %', ids;
  end if;
end
$$;

-- RECON-FAIR-DB-003: the last never-checked row is reached before older rows repeat.
do $$
declare
  ids uuid[];
begin
  select array_agg(id order by id) into ids
  from public.claim_payment_reconciliation_batch(2);

  if not ('59000000-0000-0000-0000-000000000105'::uuid = any(ids)) then
    raise exception 'RECON-FAIR-DB-003 tail candidate was starved: %', ids;
  end if;
end
$$;

-- RECON-FAIR-DB-004: every claimed row receives a durable checked timestamp.
do $$
begin
  if exists (
    select 1
    from public.payments
    where id in (
      '59000000-0000-0000-0000-000000000101',
      '59000000-0000-0000-0000-000000000102',
      '59000000-0000-0000-0000-000000000103',
      '59000000-0000-0000-0000-000000000104',
      '59000000-0000-0000-0000-000000000105'
    )
      and reconciliation_checked_at is null
  ) then
    raise exception 'RECON-FAIR-DB-004 claimed row missing reconciliation timestamp';
  end if;
end
$$;

-- RECON-FAIR-DB-005: hard cap remains 100 even if caller asks for more.
do $$
declare
  v_count integer;
begin
  select count(*) into v_count
  from public.claim_payment_reconciliation_batch(1000);

  if v_count > 100 then
    raise exception 'RECON-FAIR-DB-005 batch cap exceeded: %', v_count;
  end if;
end
$$;

-- RECON-FAIR-DB-006: browser-authenticated callers cannot claim financial work.
do $$
begin
  if has_function_privilege(
    'authenticated',
    'public.claim_payment_reconciliation_batch(integer)',
    'EXECUTE'
  ) then
    raise exception 'RECON-FAIR-DB-006 authenticated can claim reconciliation batch';
  end if;
end
$$;

rollback;

select 'Payment Reconciliation Fairness, Claiming & Starvation Safety PostgreSQL V1: PASS' as result;
