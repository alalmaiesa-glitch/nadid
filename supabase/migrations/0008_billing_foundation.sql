create table if not exists public.payments (
  id uuid primary key default gen_random_uuid(),
  user_id uuid null references auth.users(id) on delete set null,
  purpose text not null check (purpose in ('support', 'service', 'subscription')),
  provider text not null default 'moyasar',
  provider_payment_id text null,
  amount_minor bigint not null check (amount_minor > 0),
  currency text not null,
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
  name text not null,
  description text null,
  amount_minor bigint not null check (amount_minor > 0),
  currency text not null,
  billing_interval text not null
    check (billing_interval in ('one_time', 'month', 'year')),
  active boolean not null default true,
  entitlements jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  plan_id text not null references public.billing_plans(id),
  provider text not null default 'moyasar',
  provider_reference text null,
  payment_token text null,
  status text not null default 'active'
    check (status in ('active', 'past_due', 'cancelled', 'expired')),
  current_period_start timestamptz null,
  current_period_end timestamptz null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.payments enable row level security;
alter table public.billing_plans enable row level security;
alter table public.subscriptions enable row level security;

create policy "payments_select_own"
on public.payments for select
to authenticated
using (user_id = auth.uid());

create policy "plans_select_active"
on public.billing_plans for select
to authenticated
using (active = true);

create policy "subscriptions_select_own"
on public.subscriptions for select
to authenticated
using (user_id = auth.uid());
