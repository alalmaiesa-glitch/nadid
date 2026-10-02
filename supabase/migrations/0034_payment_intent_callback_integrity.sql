-- Payment Intent Creation & Callback Verification V1

alter table public.payments
  add column if not exists client_request_id uuid null;

create unique index if not exists payments_user_request_unique_idx
  on public.payments(user_id, client_request_id)
  where user_id is not null and client_request_id is not null;

create or replace function public.create_payment_intent(
  p_user_id uuid,
  p_product_kind text,
  p_product_id text,
  p_request_id uuid
)
returns table (
  payment_id uuid,
  reused boolean,
  purpose text,
  amount_minor bigint,
  currency text,
  payment_metadata jsonb
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_existing public.payments%rowtype;
  v_payment_id uuid;
  v_purpose text;
  v_amount bigint;
  v_currency text;
  v_metadata jsonb;
  v_plan public.billing_plans%rowtype;
  v_pack public.credit_packs%rowtype;
begin
  if p_user_id is null
     or p_request_id is null
     or coalesce(length(trim(p_product_kind)), 0) = 0
     or coalesce(length(trim(p_product_id)), 0) = 0
  then
    raise exception 'invalid_payment_intent_request'
      using errcode = 'P0001';
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended(p_user_id::text || ':' || p_request_id::text, 34001)
  );

  select * into v_existing
  from public.payments
  where user_id = p_user_id
    and client_request_id = p_request_id
  limit 1;

  if found then
    if (
      p_product_kind = 'subscription'
      and (
        v_existing.purpose <> 'subscription'
        or v_existing.metadata->>'plan_id' <> p_product_id
      )
    ) or (
      p_product_kind = 'credit_topup'
      and (
        v_existing.purpose <> 'credit_topup'
        or v_existing.metadata->>'pack_id' <> p_product_id
      )
    ) then
      raise exception 'payment_intent_idempotency_mismatch'
        using errcode = 'P0001';
    end if;

    return query
    select
      v_existing.id,
      true,
      v_existing.purpose,
      v_existing.amount_minor,
      v_existing.currency,
      v_existing.metadata;
    return;
  end if;

  if p_product_kind = 'subscription' then
    select * into v_plan
    from public.billing_plans
    where id = p_product_id
      and active = true
      and tier <> 'free'
      and amount_minor > 0;

    if not found then
      raise exception 'paid_plan_not_found'
        using errcode = 'P0001';
    end if;

    v_purpose := 'subscription';
    v_amount := v_plan.amount_minor;
    v_currency := upper(v_plan.currency);
    v_metadata := jsonb_build_object(
      'plan_id', v_plan.id,
      'product_kind', 'subscription'
    );

  elsif p_product_kind = 'credit_topup' then
    select * into v_pack
    from public.credit_packs
    where id = p_product_id
      and active = true
      and amount_minor > 0;

    if not found then
      raise exception 'credit_pack_not_found'
        using errcode = 'P0001';
    end if;

    v_purpose := 'credit_topup';
    v_amount := v_pack.amount_minor;
    v_currency := upper(v_pack.currency);
    v_metadata := jsonb_build_object(
      'pack_id', v_pack.id,
      'product_kind', 'credit_topup'
    );
  else
    raise exception 'unsupported_payment_product_kind'
      using errcode = 'P0001';
  end if;

  v_payment_id := gen_random_uuid();
  v_metadata := v_metadata || jsonb_build_object(
    'nadid_payment_id', v_payment_id::text
  );

  insert into public.payments (
    id,
    user_id,
    purpose,
    provider,
    provider_payment_id,
    client_request_id,
    amount_minor,
    currency,
    status,
    description,
    metadata,
    created_at,
    updated_at
  )
  values (
    v_payment_id,
    p_user_id,
    v_purpose,
    'moyasar',
    v_payment_id::text,
    p_request_id,
    v_amount,
    v_currency,
    'pending',
    case
      when v_purpose = 'subscription'
        then 'Nadid subscription: ' || p_product_id
      else 'Nadid credit top-up: ' || p_product_id
    end,
    v_metadata,
    clock_timestamp(),
    clock_timestamp()
  );

  return query
  select
    v_payment_id,
    false,
    v_purpose,
    v_amount,
    v_currency,
    v_metadata;
end;
$$;

revoke all on function public.create_payment_intent(uuid, text, text, uuid)
from public, anon, authenticated;

grant execute on function public.create_payment_intent(uuid, text, text, uuid)
to service_role;
