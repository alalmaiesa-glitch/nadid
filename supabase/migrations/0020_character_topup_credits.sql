create table if not exists public.credit_packs (
  id text primary key,
  name text not null,
  characters bigint not null check (characters > 0),
  amount_minor bigint not null check (amount_minor > 0),
  currency text not null default 'SAR',
  active boolean not null default true,
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.character_usage_monthly (
  user_id uuid not null references auth.users(id) on delete cascade,
  period_start date not null,
  included_characters bigint not null default 0 check (included_characters >= 0),
  used_characters bigint not null default 0 check (used_characters >= 0),
  updated_at timestamptz not null default now(),
  primary key (user_id, period_start)
);

create table if not exists public.credit_topups (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  pack_id text not null references public.credit_packs(id),
  payment_id uuid null references public.payments(id) on delete set null,
  characters_total bigint not null check (characters_total > 0),
  characters_remaining bigint not null check (characters_remaining >= 0),
  status text not null default 'pending'
    check (status in ('pending','available','consumed','refunded','voided')),
  created_at timestamptz not null default now(),
  activated_at timestamptz null,
  updated_at timestamptz not null default now()
);

create index if not exists character_usage_monthly_user_period_idx
  on public.character_usage_monthly(user_id, period_start desc);
create index if not exists credit_topups_user_status_idx
  on public.credit_topups(user_id, status, created_at);
create index if not exists credit_topups_pack_id_idx
  on public.credit_topups(pack_id);
create index if not exists credit_topups_payment_id_idx
  on public.credit_topups(payment_id);

alter table public.credit_packs enable row level security;
alter table public.character_usage_monthly enable row level security;
alter table public.credit_topups enable row level security;

drop policy if exists credit_packs_select_active on public.credit_packs;
create policy credit_packs_select_active
on public.credit_packs for select
to anon, authenticated
using (active = true);

drop policy if exists character_usage_select_own on public.character_usage_monthly;
create policy character_usage_select_own
on public.character_usage_monthly for select
to authenticated
using (user_id = (select auth.uid()));

drop policy if exists credit_topups_select_own on public.credit_topups;
create policy credit_topups_select_own
on public.credit_topups for select
to authenticated
using (user_id = (select auth.uid()));

insert into public.credit_packs
  (id, name, characters, amount_minor, currency, active, sort_order)
values
  ('topup_100k', '100 ألف حرف', 100000, 900, 'SAR', true, 10),
  ('topup_500k', '500 ألف حرف', 500000, 2900, 'SAR', true, 20),
  ('topup_1m', 'مليون حرف', 1000000, 4900, 'SAR', true, 30)
on conflict (id) do update set
  name = excluded.name,
  characters = excluded.characters,
  amount_minor = excluded.amount_minor,
  currency = excluded.currency,
  active = excluded.active,
  sort_order = excluded.sort_order,
  updated_at = now();
