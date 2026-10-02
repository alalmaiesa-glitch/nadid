-- Payment Reconciliation Claim Lease & Overlap Suppression V1

begin;

do $$
declare
  v_user uuid := gen_random_uuid();
  v_first uuid;
  v_second uuid;
  v_first_lease timestamptz;
  v_count integer;
begin
  insert into auth.users (id, email)
  values (v_user, 'recon-lease@example.invalid');

  insert into public.profiles (id)
  values (v_user)
  on conflict (id) do nothing;

  insert into public.payments (
    id, user_id, provider, provider_payment_id, status,
    amount_minor, currency, environment
  )
  values
    (
      gen_random_uuid(), v_user, 'moyasar', 'lease-pay-001', 'pending',
      1000, 'SAR', 'test'
    ),
    (
      gen_random_uuid(), v_user, 'moyasar', 'lease-pay-002', 'pending',
      1000, 'SAR', 'test'
    );

  select id, reconciliation_claimed_until
  into v_first, v_first_lease
  from public.claim_payment_reconciliation_batch(1, 900)
  limit 1;

  if v_first is null or v_first_lease <= clock_timestamp() then
    raise exception 'RECON-LEASE-DB-001 failed';
  end if;

  select id into v_second
  from public.claim_payment_reconciliation_batch(1, 900)
  limit 1;

  if v_second is null or v_second = v_first then
    raise exception 'RECON-LEASE-DB-002 failed';
  end if;

  select count(*) into v_count
  from public.claim_payment_reconciliation_batch(100, 900);

  if v_count <> 0 then
    raise exception 'RECON-LEASE-DB-003 failed';
  end if;

  update public.payments
  set reconciliation_claimed_until = clock_timestamp() - interval '1 second'
  where id = v_first;

  select count(*) into v_count
  from public.claim_payment_reconciliation_batch(1, 60)
  where id = v_first;

  if v_count <> 1 then
    raise exception 'RECON-LEASE-DB-004 failed';
  end if;

  update public.payments
  set reconciliation_claimed_until = null;

  perform *
  from public.claim_payment_reconciliation_batch(1, 1);

  select extract(epoch from (reconciliation_claimed_until - reconciliation_checked_at))::integer
  into v_count
  from public.payments
  where reconciliation_claimed_until is not null
  order by reconciliation_checked_at desc
  limit 1;

  if v_count < 59 then
    raise exception 'RECON-LEASE-DB-005 failed';
  end if;

  update public.payments
  set reconciliation_claimed_until = null;

  perform *
  from public.claim_payment_reconciliation_batch(1, 999999);

  select extract(epoch from (reconciliation_claimed_until - reconciliation_checked_at))::integer
  into v_count
  from public.payments
  where reconciliation_claimed_until is not null
  order by reconciliation_checked_at desc
  limit 1;

  if v_count > 3601 then
    raise exception 'RECON-LEASE-DB-006 failed';
  end if;
end
$$;

set local role authenticated;
select set_config('request.jwt.claim.sub', gen_random_uuid()::text, true);

do $$
begin
  begin
    perform * from public.claim_payment_reconciliation_batch(1, 900);
    raise exception 'RECON-LEASE-DB-007 failed';
  exception
    when insufficient_privilege then
      null;
  end;
end
$$;

rollback;
