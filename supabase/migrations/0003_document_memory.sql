create table if not exists public.document_chunks (
  id uuid primary key default gen_random_uuid(),
  version_id uuid not null references public.document_versions(id) on delete cascade,
  chunk_key text not null,
  sequence_no integer not null,
  node_keys text[] not null default '{}',
  chunk_text text not null,
  token_estimate integer not null default 0,
  search_vector tsvector generated always as (
    to_tsvector('simple', coalesce(chunk_text, ''))
  ) stored,
  created_at timestamptz not null default now(),
  unique(version_id, chunk_key)
);

create index if not exists document_chunks_version_sequence_idx
  on public.document_chunks(version_id, sequence_no);

create index if not exists document_chunks_search_idx
  on public.document_chunks using gin(search_vector);

create table if not exists public.document_memory (
  version_id uuid primary key references public.document_versions(id) on delete cascade,
  state text not null default 'building',
  headings jsonb not null default '[]'::jsonb,
  protected_count integer not null default 0,
  chunk_count integer not null default 0,
  engine_manifest jsonb not null default '{}'::jsonb,
  built_at timestamptz null,
  updated_at timestamptz not null default now()
);

create table if not exists public.memory_terms (
  id uuid primary key default gen_random_uuid(),
  version_id uuid not null references public.document_versions(id) on delete cascade,
  term text not null,
  occurrence_count integer not null default 0,
  node_keys text[] not null default '{}',
  created_at timestamptz not null default now(),
  unique(version_id, term)
);

create index if not exists memory_terms_version_count_idx
  on public.memory_terms(version_id, occurrence_count desc);

create table if not exists public.fact_assertions (
  id uuid primary key default gen_random_uuid(),
  version_id uuid not null references public.document_versions(id) on delete cascade,
  client_fact_id text not null,
  node_key text not null,
  fact_type text not null,
  claim_key text not null,
  surface_value text not null,
  canonical_value text not null,
  context_text text not null default '',
  confidence numeric(5,4) not null default 0,
  authority text not null default 'extracted',
  created_at timestamptz not null default now(),
  unique(version_id, client_fact_id)
);

create index if not exists fact_assertions_version_claim_idx
  on public.fact_assertions(version_id, claim_key);

create table if not exists public.fact_conflicts (
  id uuid primary key default gen_random_uuid(),
  version_id uuid not null references public.document_versions(id) on delete cascade,
  client_conflict_id text not null,
  claim_key text not null,
  fact_ids text[] not null default '{}',
  values_found text[] not null default '{}',
  confidence numeric(5,4) not null default 0,
  status text not null default 'open',
  created_at timestamptz not null default now(),
  resolved_at timestamptz null,
  unique(version_id, client_conflict_id)
);

create index if not exists fact_conflicts_version_status_idx
  on public.fact_conflicts(version_id, status);

alter table public.document_chunks enable row level security;
alter table public.document_memory enable row level security;
alter table public.memory_terms enable row level security;
alter table public.fact_assertions enable row level security;
alter table public.fact_conflicts enable row level security;

create policy "chunks_select_own"
on public.document_chunks for select
to authenticated
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = document_chunks.version_id
      and d.owner_id = auth.uid()
  )
);

create policy "memory_select_own"
on public.document_memory for select
to authenticated
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = document_memory.version_id
      and d.owner_id = auth.uid()
  )
);

create policy "memory_terms_select_own"
on public.memory_terms for select
to authenticated
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = memory_terms.version_id
      and d.owner_id = auth.uid()
  )
);

create policy "facts_select_own"
on public.fact_assertions for select
to authenticated
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = fact_assertions.version_id
      and d.owner_id = auth.uid()
  )
);

create policy "conflicts_select_own"
on public.fact_conflicts for select
to authenticated
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = fact_conflicts.version_id
      and d.owner_id = auth.uid()
  )
);
