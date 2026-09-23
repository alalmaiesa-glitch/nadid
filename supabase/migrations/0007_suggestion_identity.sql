drop index if exists public.suggestions_client_id_idx;

create unique index if not exists suggestions_client_id_unique_idx
  on public.suggestions(client_suggestion_id)
  where client_suggestion_id is not null;
