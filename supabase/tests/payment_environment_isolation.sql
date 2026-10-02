\set ON_ERROR_STOP on

-- Payment Environment Isolation PostgreSQL V1

begin;

insert into auth.users (id, email, raw_user_meta_data)
values
  ('55000000-0000-0000-0000-000000000001', 'mode@nadid.local', '{}'::jsonb);

-- ENV-DB-001: new test intent persists test mode.
do $$
declare
  r record;
  v_mode text;
begin
  select * into r
  from public.create_payment_intent(
    '55000000-0000-0000-0000-000000000001',
    'subscription',
    'basic_monthly',
    '55000000-0000-4000-8000-000000000101',
    'test'
  );

  select provider_mode into v_mode
  from public.payments
  where id = r.payment_id;

  if v_mode <> 'test'
     or r.payment_metadata->>'provider_mode' <> 'test'
  then
    raise exception 'ENV-DB-001 test mode not persisted';
  end if;
end
$$;

-- ENV-DB-002: live webhook cannot activate a test-mode intent.
do $$
declare
  v_payment_id uuid;
  r record;
begin
  select id into v_payment_id
  from public.payments
  where user_id = '55000000-0000-0000-0000-000000000001'
    and client_request_id = '55000000-0000-4000-8000-000000000101';

  select * into r
  from public.apply_payment_webhook_event(
    'moyasar',
    'env-live-to-test',
    'payment_paid',
    v_payment_id::text,
    2900,
    'SAR',
    2900,
    0,
    true,
    now(),
    'env-live-to-test-digest'
  );

  if r.outcome <> 'rejected_mismatch' then
    raise exception 'ENV-DB-002 live event not rejected';
  end if;

  if (
    select status from public.payments where id = v_payment_id
  ) <> 'pending' then
    raise exception 'ENV-DB-002 test payment mutated by live event';
  end if;
end
$$;

-- ENV-DB-003: matching test webhook can activate the test intent.
do $$
declare
  v_payment_id uuid;
  r record;
begin
  select id into v_payment_id
  from public.payments
  where user_id = '55000000-0000-0000-0000-000000000001'
    and client_request_id = '55000000-0000-4000-8000-000000000101';

  select * into r
  from public.apply_payment_webhook_event(
    'moyasar',
    'env-test-to-test',
    'payment_paid',
    v_payment_id::text,
    2900,
    'SAR',
    2900,
    0,
    false,
    now(),
    'env-test-to-test-digest'
  );

  if r.outcome <> 'applied' then
    raise exception 'ENV-DB-003 matching test event not applied';
  end if;

  if (
    select status from public.payments where id = v_payment_id
  ) <> 'paid' then
    raise exception 'ENV-DB-003 matching test payment not paid';
  end if;
end
$$;

-- ENV-DB-004: test webhook cannot activate a live-mode intent.
do $$
declare
  r_intent record;
  r_event record;
begin
  select * into r_intent
  from public.create_payment_intent(
    '55000000-0000-0000-0000-000000000001',
    'credit_topup',
    'topup_100k',
    '55000000-0000-4000-8000-000000000102',
    'live'
  );

  select * into r_event
  from public.apply_payment_webhook_event(
    'moyasar',
    'env-test-to-live',
    'payment_paid',
    r_intent.payment_id::text,
    900,
    'SAR',
    900,
    0,
    false,
    now(),
    'env-test-to-live-digest'
  );

  if r_event.outcome <> 'rejected_mismatch' then
    raise exception 'ENV-DB-004 test event not rejected for live intent';
  end if;

  if (
    select status from public.payments where id = r_intent.payment_id
  ) <> 'pending' then
    raise exception 'ENV-DB-004 live payment mutated by test event';
  end if;
end
$$;

-- ENV-DB-005: idempotency key cannot cross provider modes.
do $$
begin
  perform *
  from public.create_payment_intent(
    '55000000-0000-0000-0000-000000000001',
    'subscription',
    'pro_monthly',
    '55000000-0000-4000-8000-000000000103',
    'test'
  );

  begin
    perform *
    from public.create_payment_intent(
      '55000000-0000-0000-0000-000000000001',
      'subscription',
      'pro_monthly',
      '55000000-0000-4000-8000-000000000103',
      'live'
    );
    raise exception 'ENV-DB-005 cross-mode idempotency reuse accepted';
  exception
    when others then
      if position('payment_intent_idempotency_mismatch' in sqlerrm) = 0 then
        raise;
      end if;
  end;
end
$$;

-- ENV-DB-006: invalid provider mode is rejected.
do $$
begin
  begin
    perform *
    from public.create_payment_intent(
      '55000000-0000-0000-0000-000000000001',
      'subscription',
      'pro_monthly',
      '55000000-0000-4000-8000-000000000104',
      'staging'
    );
    raise exception 'ENV-DB-006 invalid provider mode accepted';
  exception
    when others then
      if position('invalid_payment_intent_request' in sqlerrm) = 0 then
        raise;
      end if;
  end;
end
$$;

rollback;

select 'Payment Environment Isolation PostgreSQL V1: PASS' as result;
