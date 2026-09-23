alter table public.document_versions
  add column if not exists parent_version_id uuid null
    references public.document_versions(id) on delete set null;

alter table public.document_versions
  add column if not exists storage_path text null;

alter table public.document_versions
  add column if not exists status text not null default 'ready';

alter table public.document_versions
  add column if not exists change_summary jsonb not null default '{}'::jsonb;

update public.document_versions v
set storage_path = d.storage_path
from public.documents d
where v.document_id = d.id
  and v.is_source = true
  and v.storage_path is null;
