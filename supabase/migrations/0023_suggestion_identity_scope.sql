-- Partial-Write Recovery & Idempotent Worker Persistence V1
-- Suggestion identities are deterministic within a document version. They are
-- not globally unique across unrelated documents that share the same structure.

drop index if exists public.suggestions_client_id_unique_idx;

create unique index if not exists suggestions_version_client_id_unique_idx
  on public.suggestions(version_id, client_suggestion_id)
  where client_suggestion_id is not null;
