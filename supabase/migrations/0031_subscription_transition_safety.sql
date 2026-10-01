-- Subscription State & Entitlement Transition Safety V1
-- Paid access is granted only for an active subscription with a complete,
-- currently valid billing period. Missing/expired/cancelled/past_due rows
-- fall back to the free plan.

create or replace function public.get_effective_billing_plan(
  p_user_id uuid
)
returns table (
  plan_id text,
  tier text,
  entitlements jsonb
)
language sql
security definer
set search_path = public
as $$
  with active_paid as (
    select
      bp.id as plan_id,
      bp.tier,
      bp.entitlements,
      coalesce(
        nullif(bp.entitlements ->> 'monthly_characters', '')::bigint,
        0
      ) as monthly_characters,
      s.current_period_end,
      s.updated_at
    from public.subscriptions s
    join public.billing_plans bp on bp.id = s.plan_id
    where s.user_id = p_user_id
      and s.status = 'active'
      and bp.active = true
      and s.current_period_start is not null
      and s.current_period_end is not null
      and s.current_period_start <= clock_timestamp()
      and s.current_period_end > clock_timestamp()
      and s.current_period_end > s.current_period_start
    order by
      monthly_characters desc,
      s.current_period_end desc,
      s.updated_at desc
    limit 1
  ),
  fallback as (
    select bp.id as plan_id, bp.tier, bp.entitlements
    from public.billing_plans bp
    where bp.id = 'free_monthly'
      and bp.active = true
    limit 1
  )
  select plan_id, tier, entitlements from active_paid
  union all
  select plan_id, tier, entitlements from fallback
  where not exists (select 1 from active_paid)
  limit 1;
$$;

revoke all on function public.get_effective_billing_plan(uuid)
from public, anon, authenticated;

grant execute on function public.get_effective_billing_plan(uuid)
to service_role;

create or replace function public.consume_character_quota(
  p_user_id uuid,
  p_operation_id uuid,
  p_action text,
  p_characters bigint
)
returns table (
  allowed boolean,
  already_charged boolean,
  included_used bigint,
  topup_used bigint,
  remaining_included bigint,
  remaining_topup bigint
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_period_start date := date_trunc('month', clock_timestamp())::date;
  v_included bigint := 0;
  v_used bigint := 0;
  v_included_remaining bigint := 0;
  v_topup_remaining bigint := 0;
  v_need bigint := 0;
  v_take bigint := 0;
  v_event public.character_usage_events%rowtype;
  v_credit record;
begin
  if p_user_id is null
     or p_operation_id is null
     or coalesce(length(trim(p_action)), 0) = 0
     or p_characters < 1
  then
    raise exception 'invalid_character_quota_request'
      using errcode = 'P0001';
  end if;

  -- Serialize quota mutations per user across serverless instances.
  perform pg_advisory_xact_lock(
    hashtextextended(p_user_id::text, 29001)
  );

  select *
  into v_event
  from public.character_usage_events
  where user_id = p_user_id
    and operation_id = p_operation_id
    and action = p_action;

  if found then
    select
      greatest(included_characters - used_characters, 0)
    into v_included_remaining
    from public.character_usage_monthly
    where user_id = p_user_id
      and period_start = v_event.period_start;

    select coalesce(sum(characters_remaining), 0)
    into v_topup_remaining
    from public.credit_topups
    where user_id = p_user_id
      and status = 'available'
      and characters_remaining > 0;

    return query
    select
      true,
      true,
      v_event.included_used,
      v_event.topup_used,
      coalesce(v_included_remaining, 0),
      v_topup_remaining;
    return;
  end if;

  select coalesce(
    nullif(plan.entitlements ->> 'monthly_characters', '')::bigint,
    0
  )
  into v_included
  from public.get_effective_billing_plan(p_user_id) as plan;

  v_included := coalesce(v_included, 0);

  insert into public.character_usage_monthly (
    user_id,
    period_start,
    included_characters,
    used_characters,
    updated_at
  )
  values (
    p_user_id,
    v_period_start,
    v_included,
    0,
    clock_timestamp()
  )
  on conflict (user_id, period_start)
  do update set
    included_characters = excluded.included_characters,
    updated_at = clock_timestamp();

  select used_characters
  into v_used
  from public.character_usage_monthly
  where user_id = p_user_id
    and period_start = v_period_start
  for update;

  v_included_remaining := greatest(v_included - coalesce(v_used, 0), 0);

  select coalesce(sum(characters_remaining), 0)
  into v_topup_remaining
  from public.credit_topups
  where user_id = p_user_id
    and status = 'available'
    and characters_remaining > 0;

  if p_characters > v_included_remaining + v_topup_remaining then
    return query
    select
      false,
      false,
      0::bigint,
      0::bigint,
      v_included_remaining,
      v_topup_remaining;
    return;
  end if;

  v_take := least(p_characters, v_included_remaining);

  if v_take > 0 then
    update public.character_usage_monthly
    set used_characters = used_characters + v_take,
        updated_at = clock_timestamp()
    where user_id = p_user_id
      and period_start = v_period_start;
  end if;

  v_need := p_characters - v_take;

  if v_need > 0 then
    for v_credit in
      select id, characters_remaining
      from public.credit_topups
      where user_id = p_user_id
        and status = 'available'
        and characters_remaining > 0
      order by activated_at nulls last, created_at, id
      for update
    loop
      exit when v_need <= 0;

      update public.credit_topups
      set characters_remaining =
            characters_remaining - least(characters_remaining, v_need),
          status = case
            when characters_remaining - least(characters_remaining, v_need) = 0
            then 'consumed'
            else status
          end,
          updated_at = clock_timestamp()
      where id = v_credit.id;

      v_need := v_need - least(v_credit.characters_remaining, v_need);
    end loop;
  end if;

  insert into public.character_usage_events (
    user_id,
    operation_id,
    action,
    period_start,
    characters,
    included_used,
    topup_used
  )
  values (
    p_user_id,
    p_operation_id,
    p_action,
    v_period_start,
    p_characters,
    v_take,
    p_characters - v_take
  );

  select greatest(included_characters - used_characters, 0)
  into v_included_remaining
  from public.character_usage_monthly
  where user_id = p_user_id
    and period_start = v_period_start;

  select coalesce(sum(characters_remaining), 0)
  into v_topup_remaining
  from public.credit_topups
  where user_id = p_user_id
    and status = 'available'
    and characters_remaining > 0;

  return query
  select
    true,
    false,
    v_take,
    p_characters - v_take,
    coalesce(v_included_remaining, 0),
    v_topup_remaining;
end;
$$;

revoke all on function public.consume_character_quota(
  uuid, uuid, text, bigint
) from public, anon, authenticated;

grant execute on function public.consume_character_quota(
  uuid, uuid, text, bigint
) to service_role;
