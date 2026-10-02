\set ON_ERROR_STOP on

-- Partial Capture & Partial Refund Semantics PostgreSQL V1

begin;

insert into auth.users (id, email, raw_user_meta_data)
values
  ('56000000-0000-0000-0000-000000000001', 'partial@nadid.local', '{}'::jsonb);

-- PARTIAL-DB-001: partial capture cannot grant a full subscription.
do $$
declare
  intent record;
  event record;
begin
  select * into intent
  from public.create_payment_intent(
    '56000000-0000-0000-0000-000000000001',
    'subscription',
    'basic_monthly',
    '56000000-0000-4000-8000-000000000101',
    'test'
  );

  select * into event
  from public.apply_payment_webhook_event(
    'moyasar',
    'partial-capture-001',
    'payment_captured',
    intent.payment_id::text,
    2900,
    'SAR',
    1000,
    0,
    false,
    now(),
    'partial-capture-001-digest'
  );

  if event.outcome <> 'rejected_mismatch' then
    raise exception 'PARTIAL-DB-001 partial capture was accepted';
  end if;

  if (
    select status from public.payments where id = intent.payment_id
  ) <> 'pending' then
    raise exception 'PARTIAL-DB-001 partial capture mutated payment status';
  end if;

  if exists (
    select 1 from public.subscriptions where payment_id = intent.payment_id
  ) then
    raise exception 'PARTIAL-DB-001 partial capture created subscription';
  end if;
end
$$;

-- PARTIAL-DB-002: full capture marks paid and records captured_minor.
do $$
declare
  intent record;
  event record;
begin
  select * into intent
  from public.create_payment_intent(
    '56000000-0000-0000-0000-000000000001',
    'subscription',
    'basic_monthly',
    '56000000-0000-4000-8000-000000000102',
    'test'
  );

  select * into event
  from public.apply_payment_webhook_event(
    'moyasar',
    'full-capture-001',
    'payment_captured',
    intent.payment_id::text,
    2900,
    'SAR',
    2900,
    0,
    false,
    now(),
    'full-capture-001-digest'
  );

  if event.outcome <> 'applied' then
    raise exception 'PARTIAL-DB-002 full capture not applied';
  end if;

  if (
    select status from public.payments where id = intent.payment_id
  ) <> 'paid' then
    raise exception 'PARTIAL-DB-002 full capture not paid';
  end if;

  if (
    select captured_minor from public.payments where id = intent.payment_id
  ) <> 2900 then
    raise exception 'PARTIAL-DB-002 captured amount not recorded';
  end if;

  perform *
  from public.activate_subscription_from_payment(
    intent.payment_id,
    'basic_monthly'
  );
end
$$;

-- PARTIAL-DB-003: a partial refund is explicit and revokes future entitlement.
do $$
declare
  v_payment_id uuid;
  event record;
begin
  select id into v_payment_id
  from public.payments
  where user_id = '56000000-0000-0000-0000-000000000001'
    and client_request_id = '56000000-0000-4000-8000-000000000102';

  select * into event
  from public.apply_payment_webhook_event(
    'moyasar',
    'partial-refund-001',
    'payment_refunded',
    v_payment_id::text,
    2900,
    'SAR',
    2900,
    1000,
    false,
    now(),
    'partial-refund-001-digest'
  );

  if event.outcome <> 'applied' then
    raise exception 'PARTIAL-DB-003 partial refund not applied';
  end if;

  if (
    select status from public.payments where id = v_payment_id
  ) <> 'partially_refunded' then
    raise exception 'PARTIAL-DB-003 partial refund state missing';
  end if;

  if (
    select refunded_minor from public.payments where id = v_payment_id
  ) <> 1000 then
    raise exception 'PARTIAL-DB-003 refunded amount not recorded';
  end if;

  if exists (
    select 1 from public.subscriptions
    where payment_id = v_payment_id
      and status = 'active'
  ) then
    raise exception 'PARTIAL-DB-003 entitlement survived partial refund';
  end if;
end
$$;

-- PARTIAL-DB-004: delayed paid/captured events cannot resurrect partial refunds.
do $$
declare
  v_payment_id uuid;
  event record;
begin
  select id into v_payment_id
  from public.payments
  where user_id = '56000000-0000-0000-0000-000000000001'
    and client_request_id = '56000000-0000-4000-8000-000000000102';

  select * into event
  from public.apply_payment_webhook_event(
    'moyasar',
    'late-paid-after-partial-refund',
    'payment_paid',
    v_payment_id::text,
    2900,
    'SAR',
    2900,
    1000,
    false,
    now(),
    'late-paid-after-partial-refund-digest'
  );

  if event.outcome <> 'ignored' then
    raise exception 'PARTIAL-DB-004 late paid event not ignored';
  end if;

  if (
    select status from public.payments where id = v_payment_id
  ) <> 'partially_refunded' then
    raise exception 'PARTIAL-DB-004 partially refunded payment resurrected';
  end if;
end
$$;

-- PARTIAL-DB-005: full refund of a paid top-up zeroes remaining credit.
do $$
declare
  intent record;
begin
  select * into intent
  from public.create_payment_intent(
    '56000000-0000-0000-0000-000000000001',
    'credit_topup',
    'topup_100k',
    '56000000-0000-4000-8000-000000000103',
    'test'
  );

  perform *
  from public.apply_payment_webhook_event(
    'moyasar',
    'topup-paid-partial-suite',
    'payment_paid',
    intent.payment_id::text,
    900,
    'SAR',
    900,
    0,
    false,
    now(),
    'topup-paid-partial-suite-digest'
  );

  perform *
  from public.activate_topup_from_payment(
    intent.payment_id,
    'topup_100k'
  );

  perform *
  from public.apply_payment_webhook_event(
    'moyasar',
    'topup-full-refund-partial-suite',
    'payment_refunded',
    intent.payment_id::text,
    900,
    'SAR',
    900,
    900,
    false,
    now(),
    'topup-full-refund-partial-suite-digest'
  );

  if (
    select status from public.payments where id = intent.payment_id
  ) <> 'refunded' then
    raise exception 'PARTIAL-DB-005 full refund state missing';
  end if;

  if (
    select refunded_minor from public.payments where id = intent.payment_id
  ) <> 900 then
    raise exception 'PARTIAL-DB-005 full refund amount missing';
  end if;

  if (
    select characters_remaining from public.credit_topups
    where payment_id = intent.payment_id
  ) <> 0 then
    raise exception 'PARTIAL-DB-005 refunded topup retains credit';
  end if;
end
$$;

-- PARTIAL-DB-006: refund greater than original amount is rejected without mutation.
do $$
declare
  intent record;
  event record;
begin
  select * into intent
  from public.create_payment_intent(
    '56000000-0000-0000-0000-000000000001',
    'subscription',
    'pro_monthly',
    '56000000-0000-4000-8000-000000000104',
    'test'
  );

  perform *
  from public.apply_payment_webhook_event(
    'moyasar',
    'pro-paid-before-invalid-refund',
    'payment_paid',
    intent.payment_id::text,
    5900,
    'SAR',
    5900,
    0,
    false,
    now(),
    'pro-paid-before-invalid-refund-digest'
  );

  select * into event
  from public.apply_payment_webhook_event(
    'moyasar',
    'invalid-over-refund',
    'payment_refunded',
    intent.payment_id::text,
    5900,
    'SAR',
    5900,
    6000,
    false,
    now(),
    'invalid-over-refund-digest'
  );

  if event.outcome <> 'rejected_mismatch' then
    raise exception 'PARTIAL-DB-006 excessive refund accepted';
  end if;

  if (
    select status from public.payments where id = intent.payment_id
  ) <> 'paid' then
    raise exception 'PARTIAL-DB-006 invalid refund mutated status';
  end if;

  if (
    select refunded_minor from public.payments where id = intent.payment_id
  ) <> 0 then
    raise exception 'PARTIAL-DB-006 invalid refund mutated amount';
  end if;
end
$$;

-- PARTIAL-DB-007: currency mismatch on a refund cannot mutate state.
do $$
declare
  intent record;
  event record;
begin
  select * into intent
  from public.create_payment_intent(
    '56000000-0000-0000-0000-000000000001',
    'subscription',
    'pro_yearly',
    '56000000-0000-4000-8000-000000000105',
    'test'
  );

  perform *
  from public.apply_payment_webhook_event(
    'moyasar',
    'yearly-paid-before-currency-mismatch',
    'payment_paid',
    intent.payment_id::text,
    59000,
    'SAR',
    59000,
    0,
    false,
    now(),
    'yearly-paid-before-currency-mismatch-digest'
  );

  select * into event
  from public.apply_payment_webhook_event(
    'moyasar',
    'refund-currency-mismatch',
    'payment_refunded',
    intent.payment_id::text,
    59000,
    'USD',
    59000,
    1000,
    false,
    now(),
    'refund-currency-mismatch-digest'
  );

  if event.outcome <> 'rejected_mismatch' then
    raise exception 'PARTIAL-DB-007 refund currency mismatch accepted';
  end if;

  if (
    select status from public.payments where id = intent.payment_id
  ) <> 'paid' then
    raise exception 'PARTIAL-DB-007 currency mismatch mutated status';
  end if;
end
$$;

-- PARTIAL-DB-009: a stale partial refund cannot downgrade a full refund.
do $
declare
  intent record;
  event record;
begin
  select * into intent
  from public.create_payment_intent(
    '56000000-0000-0000-0000-000000000001',
    'subscription',
    'basic_monthly',
    '56000000-0000-4000-8000-000000000106',
    'test'
  );

  perform *
  from public.apply_payment_webhook_event(
    'moyasar',
    'full-refund-monotonic-paid',
    'payment_paid',
    intent.payment_id::text,
    2900,
    'SAR',
    2900,
    0,
    false,
    now(),
    'full-refund-monotonic-paid-digest'
  );

  perform *
  from public.apply_payment_webhook_event(
    'moyasar',
    'full-refund-monotonic-full',
    'payment_refunded',
    intent.payment_id::text,
    2900,
    'SAR',
    2900,
    2900,
    false,
    now(),
    'full-refund-monotonic-full-digest'
  );

  select * into event
  from public.apply_payment_webhook_event(
    'moyasar',
    'full-refund-monotonic-stale-partial',
    'payment_refunded',
    intent.payment_id::text,
    2900,
    'SAR',
    2900,
    1000,
    false,
    now() - interval '5 minutes',
    'full-refund-monotonic-stale-partial-digest'
  );

  if event.outcome <> 'ignored' then
    raise exception 'PARTIAL-DB-009 stale partial refund not ignored';
  end if;

  if (
    select status from public.payments where id = intent.payment_id
  ) <> 'refunded' then
    raise exception 'PARTIAL-DB-009 full refund was downgraded';
  end if;

  if (
    select refunded_minor from public.payments where id = intent.payment_id
  ) <> 2900 then
    raise exception 'PARTIAL-DB-009 refunded total moved backwards';
  end if;
end
$;

-- PARTIAL-DB-010: refunded amount cannot exceed captured amount.
do $
declare
  intent record;
  event record;
begin
  select * into intent
  from public.create_payment_intent(
    '56000000-0000-0000-0000-000000000001',
    'subscription',
    'basic_monthly',
    '56000000-0000-4000-8000-000000000107',
    'test'
  );

  select * into event
  from public.apply_payment_webhook_event(
    'moyasar',
    'refund-over-captured',
    'payment_refunded',
    intent.payment_id::text,
    2900,
    'SAR',
    1000,
    1500,
    false,
    now(),
    'refund-over-captured-digest'
  );

  if event.outcome <> 'rejected_mismatch' then
    raise exception 'PARTIAL-DB-010 refund above captured amount accepted';
  end if;

  if (
    select status from public.payments where id = intent.payment_id
  ) <> 'pending' then
    raise exception 'PARTIAL-DB-010 invalid refund mutated payment status';
  end if;

  if (
    select refunded_minor from public.payments where id = intent.payment_id
  ) <> 0 then
    raise exception 'PARTIAL-DB-010 invalid refund mutated refund total';
  end if;
end
$;

-- PARTIAL-DB-008: authenticated clients cannot execute the new RPC signature.
do $$
begin
  if has_function_privilege(
    'authenticated',
    'public.apply_payment_webhook_event(text,text,text,text,bigint,text,bigint,bigint,boolean,timestamptz,text)',
    'EXECUTE'
  ) then
    raise exception 'PARTIAL-DB-008 authenticated can execute webhook RPC';
  end if;
end
$$;

rollback;

select 'Partial Capture & Partial Refund Semantics PostgreSQL V1: PASS' as result;
