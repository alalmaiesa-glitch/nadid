create table if not exists public.document_memory_items (
  id uuid primary key default gen_random_uuid(),
  version_id uuid not null references public.document_versions(id) on delete cascade,
  client_item_id text not null,
  kind text not null
    check (
      kind in (
        'entity',
        'definition',
        'abbreviation',
        'decision',
        'reference',
        'concept',
        'obligation',
        'condition'
      )
    ),
  item_key text not null,
  item_value text not null,
  node_keys text[] not null default '{}',
  aliases text[] not null default '{}',
  confidence numeric(5,4) not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(version_id, client_item_id)
);

create index if not exists document_memory_items_version_kind_idx
  on public.document_memory_items(version_id, kind);

create index if not exists document_memory_items_version_key_idx
  on public.document_memory_items(version_id, item_key);

alter table public.document_memory_items enable row level security;

create policy "memory_items_select_own"
on public.document_memory_items for select
to authenticated
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = document_memory_items.version_id
      and d.owner_id = auth.uid()
  )
);
