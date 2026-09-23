create extension if not exists pgcrypto;

create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid null references auth.users(id) on delete set null,
  title text not null,
  filename text not null,
  source_type text not null default 'docx',
  storage_path text null,
  status text not null default 'ready',
  word_count integer not null default 0,
  paragraph_count integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.document_versions (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  version_no integer not null,
  is_source boolean not null default false,
  source_sha256 text null,
  engine_manifest jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(document_id, version_no)
);

create table if not exists public.document_nodes (
  id uuid primary key default gen_random_uuid(),
  version_id uuid not null references public.document_versions(id) on delete cascade,
  logical_node_key text not null,
  parent_id uuid null references public.document_nodes(id) on delete cascade,
  node_type text not null,
  sequence_no integer not null,
  text text not null,
  normalized_text text null,
  content_hash text null,
  source_anchor jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists document_nodes_version_sequence_idx
  on public.document_nodes(version_id, sequence_no);

create table if not exists public.suggestions (
  id uuid primary key default gen_random_uuid(),
  version_id uuid not null references public.document_versions(id) on delete cascade,
  node_id uuid null references public.document_nodes(id) on delete cascade,
  client_suggestion_id text null,
  category text not null,
  title text not null,
  explanation text not null,
  original_text text not null,
  replacement_text text null,
  confidence numeric(5,4) not null default 0,
  status text not null default 'pending',
  source_engine text not null default 'fast_rules_v0.1',
  evidence jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists suggestions_version_status_idx
  on public.suggestions(version_id, status);

create table if not exists public.protected_spans (
  id uuid primary key default gen_random_uuid(),
  version_id uuid not null references public.document_versions(id) on delete cascade,
  node_id uuid null references public.document_nodes(id) on delete cascade,
  client_fact_id text null,
  span_type text not null,
  surface_text text not null,
  canonical_value jsonb not null default '{}'::jsonb,
  validator_key text not null,
  lock_policy text not null default 'normalize_only',
  lock_mode text not null default 'block',
  confidence numeric(5,4) not null default 1,
  created_at timestamptz not null default now()
);

create index if not exists protected_spans_version_idx
  on public.protected_spans(version_id);

create table if not exists public.analysis_runs (
  id uuid primary key default gen_random_uuid(),
  version_id uuid not null references public.document_versions(id) on delete cascade,
  run_type text not null,
  state text not null,
  engine_manifest jsonb not null default '{}'::jsonb,
  metrics jsonb not null default '{}'::jsonb,
  started_at timestamptz not null default now(),
  completed_at timestamptz null
);

alter table public.documents enable row level security;
alter table public.document_versions enable row level security;
alter table public.document_nodes enable row level security;
alter table public.suggestions enable row level security;
alter table public.protected_spans enable row level security;
alter table public.analysis_runs enable row level security;

create policy "documents_select_own"
on public.documents for select
to authenticated
using (owner_id = auth.uid());

create policy "documents_insert_own"
on public.documents for insert
to authenticated
with check (owner_id = auth.uid());

create policy "documents_update_own"
on public.documents for update
to authenticated
using (owner_id = auth.uid())
with check (owner_id = auth.uid());

create policy "versions_select_own"
on public.document_versions for select
to authenticated
using (
  exists (
    select 1 from public.documents d
    where d.id = document_versions.document_id
      and d.owner_id = auth.uid()
  )
);

create policy "nodes_select_own"
on public.document_nodes for select
to authenticated
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = document_nodes.version_id
      and d.owner_id = auth.uid()
  )
);

create policy "suggestions_select_own"
on public.suggestions for select
to authenticated
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = suggestions.version_id
      and d.owner_id = auth.uid()
  )
);

create policy "protected_spans_select_own"
on public.protected_spans for select
to authenticated
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = protected_spans.version_id
      and d.owner_id = auth.uid()
  )
);

create policy "analysis_runs_select_own"
on public.analysis_runs for select
to authenticated
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = analysis_runs.version_id
      and d.owner_id = auth.uid()
  )
);
