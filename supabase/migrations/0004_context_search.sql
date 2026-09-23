create or replace function public.search_document_chunks(
  p_version_id uuid,
  p_query text,
  p_limit integer default 5
)
returns table (
  chunk_key text,
  sequence_no integer,
  node_keys text[],
  chunk_text text,
  token_estimate integer,
  rank real
)
language sql
stable
security invoker
set search_path = public
as $$
  select
    c.chunk_key,
    c.sequence_no,
    c.node_keys,
    c.chunk_text,
    c.token_estimate,
    ts_rank_cd(
      c.search_vector,
      websearch_to_tsquery('simple', p_query)
    )::real as rank
  from public.document_chunks c
  where c.version_id = p_version_id
    and length(trim(p_query)) > 0
    and c.search_vector @@ websearch_to_tsquery('simple', p_query)
  order by rank desc, c.sequence_no asc
  limit greatest(1, least(p_limit, 12));
$$;

grant execute on function public.search_document_chunks(uuid, text, integer)
to authenticated;
