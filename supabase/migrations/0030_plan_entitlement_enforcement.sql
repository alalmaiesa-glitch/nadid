-- Plan Entitlement Enforcement V1

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
      and (s.current_period_start is null or s.current_period_start <= clock_timestamp())
      and (s.current_period_end is null or s.current_period_end > clock_timestamp())
    order by monthly_characters desc, s.current_period_end desc nulls last, s.updated_at desc
    limit 1
  ),
  fallback as (
    select
      bp.id as plan_id,
      bp.tier,
      bp.entitlements
    from public.billing_plans bp
    where bp.id = 'free_monthly'
      and bp.active = true
    limit 1
  )
  select plan_id, tier, entitlements
  from active_paid
  union all
  select plan_id, tier, entitlements
  from fallback
  where not exists (select 1 from active_paid)
  limit 1;
$$;

revoke all on function public.get_effective_billing_plan(uuid)
from public, anon, authenticated;

grant execute on function public.get_effective_billing_plan(uuid)
to service_role;
