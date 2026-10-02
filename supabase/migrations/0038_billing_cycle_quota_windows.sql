-- Billing-Cycle Aligned Character Quota Windows V1
--
-- Paid plans use the subscription's own billing anchor instead of the
-- calendar month. Annual plans still receive a monthly character allowance,
-- but each monthly window is anchored to the subscription anniversary day.
-- Free users keep calendar-month windows because no paid billing anchor exists.

create or replace function public.resolve_character_quota_window(
  p_user_id uuid
)
returns table (
  plan_id text,
  period_start date,
  included_characters bigint
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_subscription public.subscriptions%rowtype;
  v_plan public.billing_plans%rowtype;
  v_now timestamptz := clock_timestamp();
  v_elapsed_months integer := 0;
  v_candidate timestamptz;
begin
  if p_user_id is null then
    raise exception 'invalid_character_quota_identity'
      using errcode = 'P0001';
  end if;

  select s.*
  into v_subscription
  from public.subscriptions s
  join public.billing_plans bp on bp.id = s.plan_id
  where s.user_id = p_user_id
    and s.status = 'active'
    and bp.active = true
    and s.current_period_start is not null
    and s.current_period_end is not null
    and s.current_period_start <= v_now
    and s.current_period_end > v_now
  order by
    coalesce(nullif(bp.entitlements ->> 'monthly_characters', '')::bigint, 0) desc,
    s.current_period_end desc,
    s.updated_at desc
  limit 1;

  if found then
    select *
    into v_plan
    from public.billing_plans
    where id = v_subscription.plan_id
      and active = true;

    if not found then
      raise exception 'active_billing_plan_not_found'
        using errcode = 'P0001';
    end if;

    if v_plan.billing_interval = 'month' then
      return query
      select
        v_plan.id,
        v_subscription.current_period_start::date,
        coalesce(
          nullif(v_plan.entitlements ->> 'monthly_characters', '')::bigint,
          0
        );
      return;
    end if;

    if v_plan.billing_interval = 'year' then
      v_elapsed_months :=
        (
          extract(year from v_now)::integer * 12
          + extract(month from v_now)::integer
        )
        -
        (
          extract(year from v_subscription.current_period_start)::integer * 12
          + extract(month from v_subscription.current_period_start)::integer
        );

      v_elapsed_months := greatest(v_elapsed_months, 0);
      v_candidate :=
        v_subscription.current_period_start
        + make_interval(months => v_elapsed_months);

      if v_candidate > v_now then
        v_elapsed_months := greatest(v_elapsed_months - 1, 0);
        v_candidate :=
          v_subscription.current_period_start
          + make_interval(months => v_elapsed_months);
      end if;

      if v_candidate >= v_subscription.current_period_end then
        raise exception 'annual_quota_window_outside_subscription'
          using errcode = 'P0001';
      end if;

      return query
      select
        v_plan.id,
        v_candidate::date,
        coalesce(
          nullif(v_plan.entitlements ->> 'monthly_characters', '')::bigint,
          0
        );
      return;
    end if;

    raise exception 'unsupported_quota_billing_interval'
      using errcode = 'P0001';
  end if;

  return query
  select
    bp.id,
    date_trunc('month', v_now)::date,
    coalesce(
      nullif(bp.entitlements ->> 'monthly_characters', '')::bigint,
      0
    )
  from public.billing_plans bp
  where bp.id = 'free_monthly'
    and bp.active = true
  limit 1;
end;
$$;

revoke all on function public.resolve_character_quota_window(uuid)
from public, anon, authenticated;

grant execute on function public.resolve_character_quota_window(uuid)
to service_role;

-- Usage Quota Accounting & Billing Integrity V1

create table if not exists public.character_usage_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  operation_id uuid not null,
  action text not null,
  period_start date not null,
  characters bigint not null check (characters > 0),
  included_used bigint not null default 0 check (included_used >= 0),
  topup_used bigint not null default 0 check (topup_used >= 0),
  created_at timestamptz not null default now(),
  unique (user_id, operation_id, action)
);

create index if not exists character_usage_events_user_period_idx
  on public.character_usage_events(user_id, period_start, created_at desc);

alter table public.character_usage_events enable row level security;
revoke all on public.character_usage_events from anon, authenticated;

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
  v_period_start date;
  v_included bigint := 0;
  v_plan_id text;
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

  select plan_id, period_start, included_characters
  into v_plan_id, v_period_start, v_included
  from public.resolve_character_quota_window(p_user_id);

  if not found or v_period_start is null then
    raise exception 'character_quota_window_unavailable'
      using errcode = 'P0001';
  end if;

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
