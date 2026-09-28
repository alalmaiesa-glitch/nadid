-- Nadid billing foundation activated for launch plans.
-- Payments are verified server-side; clients only receive read access to their own billing records.

create table if not exists public.payments (
  id uuid primary key default gen_random_uuid(),
  user_id uuid null references auth.users(id) on delete set null,
  purpose text not null check (purpose in ('service', 'subscription')),
  provider text not null default 'moyasar',
  provider_payment_id text null,
  amount_minor bigint not null check (amount_minor >= 0),
  currency text not null default 'SAR',
  status text not null default 'pending'
    check (status in ('pending', 'paid', 'failed', 'refunded', 'voided')),
  description text null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  paid_at timestamptz null,
  updated_at timestamptz not null default now()
);

create unique index if not exists payments_provider_payment_unique_idx
  on public.payments(provider, provider_payment_id)
  where provider_payment_id is not null;

create index if not exists payments_user_created_idx
  on public.payments(user_id, created_at desc);

create table if not exists public.billing_plans (
  id text primary key,
  tier text not null check (tier in ('free', 'basic', 'pro')),
  name text not null,
  description text null,
  amount_minor bigint not null check (amount_minor >= 0),
  currency text not null default 'SAR',
  billing_interval text not null check (billing_interval in ('month', 'year')),
  ads_enabled boolean not null default false,
  active boolean not null default true,
  entitlements jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  plan_id text not null references public.billing_plans(id),
  provider text not null default 'moyasar',
  provider_reference text null,
  status text not null default 'active'
    check (status in ('active', 'past_due', 'cancelled', 'expired')),
  current_period_start timestamptz null,
  current_period_end timestamptz null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists subscriptions_user_status_idx
  on public.subscriptions(user_id, status, current_period_end desc);

alter table public.payments enable row level security;
alter table public.billing_plans enable row level security;
alter table public.subscriptions enable row level security;

drop policy if exists payments_select_own on public.payments;
create policy payments_select_own
on public.payments for select
to authenticated
using (user_id = (select auth.uid()));

drop policy if exists plans_select_active on public.billing_plans;
create policy plans_select_active
on public.billing_plans for select
to anon, authenticated
using (active = true);

drop policy if exists subscriptions_select_own on public.subscriptions;
create policy subscriptions_select_own
on public.subscriptions for select
to authenticated
using (user_id = (select auth.uid()));

insert into public.billing_plans
  (id, tier, name, description, amount_minor, currency, billing_interval, ads_enabled, active, entitlements)
values
  (
    'free_monthly', 'free', 'مجاني', 'للتجربة والاستخدام الخفيف.', 0, 'SAR', 'month', true, true,
    '{"basic_review":true,"docx_upload":true,"original_preserved":true,"context_review":false,"deep_review":false,"fact_lock":false,"version_history":false}'::jsonb
  ),
  (
    'basic_monthly', 'basic', 'أساسي', 'للمراجعة المنتظمة للمستندات الطويلة.', 2900, 'SAR', 'month', false, true,
    '{"basic_review":true,"docx_upload":true,"original_preserved":true,"context_review":true,"consistency_review":true,"rewrite":true,"export":true,"deep_review":false,"fact_lock":false,"version_history":false}'::jsonb
  ),
  (
    'basic_yearly', 'basic', 'أساسي سنوي', 'الباقة الأساسية بفوترة سنوية.', 29000, 'SAR', 'year', false, true,
    '{"basic_review":true,"docx_upload":true,"original_preserved":true,"context_review":true,"consistency_review":true,"rewrite":true,"export":true,"deep_review":false,"fact_lock":false,"version_history":false}'::jsonb
  ),
  (
    'pro_monthly', 'pro', 'احترافي', 'للمراجعة العميقة والمستندات الحساسة.', 5900, 'SAR', 'month', false, true,
    '{"basic_review":true,"docx_upload":true,"original_preserved":true,"context_review":true,"consistency_review":true,"rewrite":true,"export":true,"deep_review":true,"fact_lock":true,"version_history":true}'::jsonb
  ),
  (
    'pro_yearly', 'pro', 'احترافي سنوي', 'الباقة الاحترافية بفوترة سنوية.', 59000, 'SAR', 'year', false, true,
    '{"basic_review":true,"docx_upload":true,"original_preserved":true,"context_review":true,"consistency_review":true,"rewrite":true,"export":true,"deep_review":true,"fact_lock":true,"version_history":true}'::jsonb
  )
on conflict (id) do update set
  tier = excluded.tier,
  name = excluded.name,
  description = excluded.description,
  amount_minor = excluded.amount_minor,
  currency = excluded.currency,
  billing_interval = excluded.billing_interval,
  ads_enabled = excluded.ads_enabled,
  active = excluded.active,
  entitlements = excluded.entitlements,
  updated_at = now();
