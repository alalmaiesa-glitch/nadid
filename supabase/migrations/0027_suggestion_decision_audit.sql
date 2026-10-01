-- Suggestion Decision Scope & Audit Trail V1
-- Decisions are scoped to document + version + deterministic suggestion id,
-- and the mutable suggestion status is paired with an append-only audit snapshot.

create table if not exists public.suggestion_decisions (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null
    references public.documents(id) on delete cascade,
  version_id uuid not null
    references public.document_versions(id) on delete cascade,
  suggestion_id uuid not null
    references public.suggestions(id) on delete cascade,
  client_suggestion_id text not null,
  owner_id uuid not null
    references auth.users(id) on delete cascade,
  decision text not null
    check (decision in ('accepted', 'rejected')),
  previous_status text not null,
  suggestion_snapshot jsonb not null,
  decided_at timestamptz not null default now()
);

create index if not exists suggestion_decisions_document_time_idx
  on public.suggestion_decisions(document_id, decided_at desc);

create index if not exists suggestion_decisions_version_idx
  on public.suggestion_decisions(version_id, decided_at desc);

alter table public.suggestion_decisions enable row level security;

drop policy if exists "suggestion_decisions_select_own"
on public.suggestion_decisions;

create policy "suggestion_decisions_select_own"
on public.suggestion_decisions
for select
to authenticated
using (
  exists (
    select 1
    from public.documents d
    where d.id = suggestion_decisions.document_id
      and d.owner_id = auth.uid()
  )
);

create or replace function public.record_suggestion_decision(
  p_document_id uuid,
  p_version_no integer,
  p_client_suggestion_id text,
  p_owner_id uuid,
  p_decision text
)
returns table (
  decision_id uuid,
  suggestion_id uuid,
  version_id uuid,
  status text
)
language plpgsql
security definer
set search_path = public
as $$
declare
  target_version_id uuid;
  latest_ready_version integer;
  target_suggestion public.suggestions%rowtype;
  created_decision_id uuid;
begin
  if p_decision not in ('accepted', 'rejected') then
    raise exception 'invalid_suggestion_decision'
      using errcode = 'P0001';
  end if;

  if p_version_no < 1 then
    raise exception 'invalid_suggestion_version'
      using errcode = 'P0001';
  end if;

  select v.id
  into target_version_id
  from public.document_versions v
  join public.documents d on d.id = v.document_id
  where d.id = p_document_id
    and d.owner_id = p_owner_id
    and v.version_no = p_version_no
    and v.status = 'ready';

  if target_version_id is null then
    raise exception 'suggestion_scope_not_found'
      using errcode = 'P0001';
  end if;

  select max(v.version_no)
  into latest_ready_version
  from public.document_versions v
  where v.document_id = p_document_id
    and v.status = 'ready';

  if latest_ready_version is distinct from p_version_no then
    raise exception 'suggestion_version_changed'
      using errcode = 'P0001';
  end if;

  select s.*
  into target_suggestion
  from public.suggestions s
  where s.version_id = target_version_id
    and s.client_suggestion_id = p_client_suggestion_id
  for update;

  if not found then
    raise exception 'suggestion_scope_not_found'
      using errcode = 'P0001';
  end if;

  update public.suggestions
  set status = p_decision
  where id = target_suggestion.id;

  insert into public.suggestion_decisions (
    document_id,
    version_id,
    suggestion_id,
    client_suggestion_id,
    owner_id,
    decision,
    previous_status,
    suggestion_snapshot
  ) values (
    p_document_id,
    target_version_id,
    target_suggestion.id,
    p_client_suggestion_id,
    p_owner_id,
    p_decision,
    target_suggestion.status,
    jsonb_build_object(
      'category', target_suggestion.category,
      'title', target_suggestion.title,
      'explanation', target_suggestion.explanation,
      'original_text', target_suggestion.original_text,
      'replacement_text', target_suggestion.replacement_text,
      'confidence', target_suggestion.confidence,
      'source_engine', target_suggestion.source_engine,
      'evidence', target_suggestion.evidence,
      'status_before', target_suggestion.status
    )
  )
  returning id into created_decision_id;

  return query
  select
    created_decision_id,
    target_suggestion.id,
    target_version_id,
    p_decision;
end;
$$;

revoke all on function public.record_suggestion_decision(
  uuid, integer, text, uuid, text
) from public, anon, authenticated;

grant execute on function public.record_suggestion_decision(
  uuid, integer, text, uuid, text
) to service_role;

revoke insert, update, delete
on public.suggestion_decisions
from anon, authenticated;
