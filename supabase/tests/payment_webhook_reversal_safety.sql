\set ON_ERROR_STOP on

-- Payment Webhook Authenticity, Replay & Reversal Safety PostgreSQL V1

begin;

insert into auth.users (id, email, raw_user_meta_data)
values
  ('53000000-0000-0000-0000-000000000001', 'webhook@nadid.local', '{}'::jsonb);

insert into public.payments (
  id, user_id, purpose, provider, provider_payment_id,
  amount_minor, currency, status, metadata
)
values
  (
    '53000000-0000-0000-0000-000000000101',
    '53000000-0000-0000-0000-000000000001',
    'subscription',
    'moyasar',
    'pay_sub_001',
    5900,
    'SAR',
    'pending',
    '{"plan_id":"pro_monthly"}'::jsonb
  ),
  (
    '53000000-0000-0000-0000-000000000102',
    '53000000-0000-0000-0000-000000000001',
    'credit_topup',
    'moyasar',
    'pay_topup_001',
    900,
    'SAR',
    'pending',
    '{"pack_id":"topup_100k"}'::jsonb
  );

-- WEBHOOK-DB-001: paid event applies only when amount/currency match.
do $$
declare
  r record;
begin
  select * into r
  from public.apply_payment_webhook_event(
    'moyasar',
    'evt-paid-001',
    'payment_paid',
    'pay_sub_001',
    5900,
    'SAR',
    5900,
    0,
    false,
    now(),
    'digest-paid-001'
  );

  if r.reused or r.outcome <> 'applied' then
    raise exception 'WEBHOOK-DB-001 paid event not applied';
  end if;

  if (
    select status from public.payments
    where id = '53000000-0000-0000-0000-000000000101'
  ) <> 'paid' then
    raise exception 'WEBHOOK-DB-001 payment not marked paid';
  end if;
end
$$;

-- WEBHOOK-DB-002: exact replay is idempotent.
do $$
declare
  r record;
begin
  select * into r
  from public.apply_payment_webhook_event(
    'moyasar',
    'evt-paid-001',
    'payment_paid',
    'pay_sub_001',
    5900,
    'SAR',
    5900,
    0,
    false,
    now(),
    'digest-paid-001'
  );

  if not r.reused or r.outcome <> 'applied' then
    raise exception 'WEBHOOK-DB-002 exact replay not reused';
  end if;

  if (
    select count(*) from public.payment_webhook_events
    where provider = 'moyasar' and provider_event_id = 'evt-paid-001'
  ) <> 1 then
    raise exception 'WEBHOOK-DB-002 duplicate ledger row created';
  end if;
end
$$;

-- WEBHOOK-DB-003: same event ID with a different digest is rejected.
do $$
begin
  begin
    perform *
    from public.apply_payment_webhook_event(
      'moyasar',
      'evt-paid-001',
      'payment_paid',
      'pay_sub_001',
      5900,
      'SAR',
      5900,
      0,
      false,
      now(),
      'different-digest'
    );
    raise exception 'WEBHOOK-DB-003 replay mismatch was accepted';
  exception
    when others then
      if position('webhook_event_replay_mismatch' in sqlerrm) = 0 then
        raise;
      end if;
  end;
end
$$;

-- Activate the subscription using the already hardened activation RPC.
select *
from public.activate_subscription_from_payment(
  '53000000-0000-0000-0000-000000000101',
  'pro_monthly'
);

-- WEBHOOK-DB-004: refund revokes future subscription entitlement.
do $$
declare
  r record;
begin
  select * into r
  from public.apply_payment_webhook_event(
    'moyasar',
    'evt-refund-001',
    'payment_refunded',
    'pay_sub_001',
    5900,
    'SAR',
    5900,
    5900,
    false,
    now(),
    'digest-refund-001'
  );

  if r.outcome <> 'applied' then
    raise exception 'WEBHOOK-DB-004 refund not applied';
  end if;

  if (
    select status from public.payments
    where id = '53000000-0000-0000-0000-000000000101'
  ) <> 'refunded' then
    raise exception 'WEBHOOK-DB-004 payment not refunded';
  end if;

  if exists (
    select 1 from public.subscriptions
    where payment_id = '53000000-0000-0000-0000-000000000101'
      and status = 'active'
  ) then
    raise exception 'WEBHOOK-DB-004 active subscription survived refund';
  end if;
end
$$;

-- WEBHOOK-DB-005: delayed paid event cannot resurrect a refunded payment.
do $$
declare
  r record;
begin
  select * into r
  from public.apply_payment_webhook_event(
    'moyasar',
    'evt-paid-late-001',
    'payment_paid',
    'pay_sub_001',
    5900,
    'SAR',
    5900,
    5900,
    false,
    now(),
    'digest-paid-late-001'
  );

  if r.outcome <> 'ignored' then
    raise exception 'WEBHOOK-DB-005 terminal payment resurrection not ignored';
  end if;

  if (
    select status from public.payments
    where id = '53000000-0000-0000-0000-000000000101'
  ) <> 'refunded' then
    raise exception 'WEBHOOK-DB-005 refunded payment was resurrected';
  end if;
end
$$;

-- WEBHOOK-DB-006: amount mismatch cannot mark a payment paid.
do $$
declare
  r record;
begin
  select * into r
  from public.apply_payment_webhook_event(
    'moyasar',
    'evt-mismatch-001',
    'payment_paid',
    'pay_topup_001',
    999,
    'SAR',
    999,
    0,
    false,
    now(),
    'digest-mismatch-001'
  );

  if r.outcome <> 'rejected_mismatch' then
    raise exception 'WEBHOOK-DB-006 amount mismatch not rejected';
  end if;

  if (
    select status from public.payments
    where id = '53000000-0000-0000-0000-000000000102'
  ) <> 'pending' then
    raise exception 'WEBHOOK-DB-006 mismatched payment mutated';
  end if;
end
$$;

-- Correct top-up payment and activation.
select *
from public.apply_payment_webhook_event(
  'moyasar',
  'evt-topup-paid-001',
  'payment_paid',
  'pay_topup_001',
  900,
  'SAR',
  900,
  0,
  false,
  now(),
  'digest-topup-paid-001'
);

select *
from public.activate_topup_from_payment(
  '53000000-0000-0000-0000-000000000102',
  'topup_100k'
);

-- WEBHOOK-DB-007: refund removes all remaining top-up credit.
do $$
begin
  perform *
  from public.apply_payment_webhook_event(
    'moyasar',
    'evt-topup-refund-001',
    'payment_refunded',
    'pay_topup_001',
    900,
    'SAR',
    900,
    900,
    false,
    now(),
    'digest-topup-refund-001'
  );

  if (
    select status from public.credit_topups
    where payment_id = '53000000-0000-0000-0000-000000000102'
  ) <> 'refunded' then
    raise exception 'WEBHOOK-DB-007 topup not refunded';
  end if;

  if (
    select characters_remaining from public.credit_topups
    where payment_id = '53000000-0000-0000-0000-000000000102'
  ) <> 0 then
    raise exception 'WEBHOOK-DB-007 refunded topup retains balance';
  end if;
end
$$;

-- WEBHOOK-DB-008: unmatched provider payment is acknowledged but not invented.
do $$
declare
  r record;
begin
  select * into r
  from public.apply_payment_webhook_event(
    'moyasar',
    'evt-unmatched-001',
    'payment_paid',
    'unknown-provider-payment',
    100,
    'SAR',
    100,
    0,
    false,
    now(),
    'digest-unmatched-001'
  );

  if r.outcome <> 'unmatched' or r.local_payment_id is not null then
    raise exception 'WEBHOOK-DB-008 unmatched event handling failed';
  end if;
end
$$;

-- WEBHOOK-DB-009: authenticated clients cannot call the privileged RPC.
do $$
begin
  if has_function_privilege(
    'authenticated',
    'public.apply_payment_webhook_event(text,text,text,text,bigint,text,bigint,bigint,boolean,timestamptz,text)',
    'EXECUTE'
  ) then
    raise exception 'WEBHOOK-DB-009 authenticated can execute webhook RPC';
  end if;
end
$$;

rollback;

select 'Payment Webhook Authenticity, Replay & Reversal Safety PostgreSQL V1: PASS' as result;
