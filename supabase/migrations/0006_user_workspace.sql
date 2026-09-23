create index if not exists documents_owner_updated_idx
  on public.documents(owner_id, updated_at desc)
  where owner_id is not null;

create index if not exists document_versions_document_ready_idx
  on public.document_versions(document_id, version_no desc)
  where status = 'ready';

create index if not exists suggestions_client_id_idx
  on public.suggestions(client_suggestion_id)
  where client_suggestion_id is not null;
