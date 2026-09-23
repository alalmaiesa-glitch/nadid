create index if not exists documents_owner_created_idx
  on public.documents(owner_id, created_at desc)
  where owner_id is not null;
