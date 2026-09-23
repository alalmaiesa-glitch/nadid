create index if not exists analysis_runs_version_id_idx
  on public.analysis_runs(version_id);

create index if not exists document_nodes_parent_id_idx
  on public.document_nodes(parent_id)
  where parent_id is not null;

create index if not exists document_versions_parent_version_id_idx
  on public.document_versions(parent_version_id)
  where parent_version_id is not null;

create index if not exists protected_spans_node_id_idx
  on public.protected_spans(node_id)
  where node_id is not null;

create index if not exists suggestions_node_id_idx
  on public.suggestions(node_id)
  where node_id is not null;

alter policy "documents_select_own"
on public.documents
using (owner_id = (select auth.uid()));

alter policy "documents_insert_own"
on public.documents
with check (owner_id = (select auth.uid()));

alter policy "documents_update_own"
on public.documents
using (owner_id = (select auth.uid()))
with check (owner_id = (select auth.uid()));

alter policy "versions_select_own"
on public.document_versions
using (
  exists (
    select 1 from public.documents d
    where d.id = document_versions.document_id
      and d.owner_id = (select auth.uid())
  )
);

alter policy "nodes_select_own"
on public.document_nodes
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = document_nodes.version_id
      and d.owner_id = (select auth.uid())
  )
);

alter policy "suggestions_select_own"
on public.suggestions
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = suggestions.version_id
      and d.owner_id = (select auth.uid())
  )
);

alter policy "protected_spans_select_own"
on public.protected_spans
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = protected_spans.version_id
      and d.owner_id = (select auth.uid())
  )
);

alter policy "analysis_runs_select_own"
on public.analysis_runs
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = analysis_runs.version_id
      and d.owner_id = (select auth.uid())
  )
);

alter policy "chunks_select_own"
on public.document_chunks
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = document_chunks.version_id
      and d.owner_id = (select auth.uid())
  )
);

alter policy "memory_select_own"
on public.document_memory
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = document_memory.version_id
      and d.owner_id = (select auth.uid())
  )
);

alter policy "memory_terms_select_own"
on public.memory_terms
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = memory_terms.version_id
      and d.owner_id = (select auth.uid())
  )
);

alter policy "facts_select_own"
on public.fact_assertions
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = fact_assertions.version_id
      and d.owner_id = (select auth.uid())
  )
);

alter policy "conflicts_select_own"
on public.fact_conflicts
using (
  exists (
    select 1
    from public.document_versions v
    join public.documents d on d.id = v.document_id
    where v.id = fact_conflicts.version_id
      and d.owner_id = (select auth.uid())
  )
);
