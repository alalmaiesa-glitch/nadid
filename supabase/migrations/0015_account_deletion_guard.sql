alter table public.documents
  drop constraint if exists documents_owner_id_fkey;

alter table public.documents
  add constraint documents_owner_id_fkey
  foreign key (owner_id)
  references auth.users(id)
  on delete restrict;
