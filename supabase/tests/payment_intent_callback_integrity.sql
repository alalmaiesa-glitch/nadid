\set ON_ERROR_STOP on

-- Payment Intent Creation & Callback Verification PostgreSQL V1

begin;

insert into auth.users (id, email, raw_user_meta_data)
values
  ('54000000-0000-0000-0000-000000000001', 'intent@nadid.local', '{}'::jsonb);

-- INTENT-DB-001: trusted subscription pricing comes from billing_plans.
do $$
declare
  r record;
begin
  select * into r
  from public.create_payment_intent(
    '54000000-0000-0000-0000-000000000001',
    'subscription',
    'pro_monthly',
    '54000000-0000-4000-8000-000000000101',
    'test'
  );

  if r.reused then
    raise exception 'INTENT-DB-001 unexpected reuse';
  end if;

  if r.amount_minor <> 5900 or upper(r.currency) <> 'SAR' then
    raise exception 'INTENT-DB-001 trusted price mismatch';
  end if;

  if r.purpose <> 'subscription'
     or r.payment_metadata->>'plan_id' <> 'pro_monthly'
  then
    raise exception 'INTENT-DB-001 subscription metadata mismatch';
  end if;

  if (
    select provider_payment_id
    from public.payments
    where id = r.payment_id
  ) <> r.payment_id::text then
    raise exception 'INTENT-DB-001 provider given_id mismatch';
  end if;
end
$$;

-- INTENT-DB-002: retry with the same Idempotency-Key reuses one payment.
do $$
declare
  first_row record;
  second_row record;
begin
  select * into first_row
  from public.create_payment_intent(
    '54000000-0000-0000-0000-000000000001',
    'subscription',
    'basic_monthly',
    '54000000-0000-4000-8000-000000000102',
    'test'
  );

  select * into second_row
  from public.create_payment_intent(
    '54000000-0000-0000-0000-000000000001',
    'subscription',
    'basic_monthly',
    '54000000-0000-4000-8000-000000000102',
    'test'
  );

  if not second_row.reused or second_row.payment_id <> first_row.payment_id then
    raise exception 'INTENT-DB-002 idempotent retry failed';
  end if;

  if (
    select count(*)
    from public.payments
    where user_id = '54000000-0000-0000-0000-000000000001'
      and client_request_id = '54000000-0000-4000-8000-000000000102'
  ) <> 1 then
    raise exception 'INTENT-DB-002 duplicate payment created';
  end if;
end
$$;

-- INTENT-DB-003: same idempotency key cannot be reused for another product.
do $$
begin
  perform *
  from public.create_payment_intent(
    '54000000-0000-0000-0000-000000000001',
    'credit_topup',
    'topup_100k',
    '54000000-0000-4000-8000-000000000103',
    'test'
  );

  begin
    perform *
    from public.create_payment_intent(
      '54000000-0000-0000-0000-000000000001',
      'credit_topup',
      'topup_500k',
      '54000000-0000-4000-8000-000000000103',
      'test'
    );
    raise exception 'INTENT-DB-003 idempotency mismatch accepted';
  exception
    when others then
      if position('payment_intent_idempotency_mismatch' in sqlerrm) = 0 then
        raise;
      end if;
  end;
end
$$;

-- INTENT-DB-004: top-up price and capacity identity come from credit_packs.
do $$
declare
  r record;
begin
  select * into r
  from public.create_payment_intent(
    '54000000-0000-0000-0000-000000000001',
    'credit_topup',
    'topup_1m',
    '54000000-0000-4000-8000-000000000104',
    'test'
  );

  if r.amount_minor <> 4900
     or r.payment_metadata->>'pack_id' <> 'topup_1m'
  then
    raise exception 'INTENT-DB-004 topup trusted product mismatch';
  end if;
end
$$;

-- INTENT-DB-005: free plan cannot create a paid intent.
do $$
begin
  begin
    perform *
    from public.create_payment_intent(
      '54000000-0000-0000-0000-000000000001',
      'subscription',
      'free_monthly',
      '54000000-0000-4000-8000-000000000105',
      'test'
    );
    raise exception 'INTENT-DB-005 free paid intent accepted';
  exception
    when others then
      if position('paid_plan_not_found' in sqlerrm) = 0 then
        raise;
      end if;
  end;
end
$$;

-- INTENT-DB-006: unknown product cannot create a payment.
do $$
begin
  begin
    perform *
    from public.create_payment_intent(
      '54000000-0000-0000-0000-000000000001',
      'subscription',
      'does_not_exist',
      '54000000-0000-4000-8000-000000000106',
      'test'
    );
    raise exception 'INTENT-DB-006 unknown product accepted';
  exception
    when others then
      if position('paid_plan_not_found' in sqlerrm) = 0 then
        raise;
      end if;
  end;
end
$$;

-- INTENT-DB-007: authenticated clients cannot execute intent RPC directly.
do $$
begin
  if has_function_privilege(
    'authenticated',
    'public.create_payment_intent(uuid,text,text,uuid,text)',
    'EXECUTE'
  ) then
    raise exception 'INTENT-DB-007 authenticated can execute intent RPC';
  end if;
end
$$;

rollback;

select 'Payment Intent Creation & Callback Verification PostgreSQL V1: PASS' as result;
