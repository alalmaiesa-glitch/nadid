create table if not exists public.worker_heartbeats (
  worker_id text primary key,
  last_seen timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb
);

alter table public.worker_heartbeats enable row level security;
