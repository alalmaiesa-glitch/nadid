alter table public.documents
  add column if not exists upload_sha256 text null,
  add column if not exists upload_finalized_at timestamptz null;

alter table public.documents
  drop constraint if exists documents_upload_sha256_format;

alter table public.documents
  add constraint documents_upload_sha256_format
  check (
    upload_sha256 is null
    or upload_sha256 ~ '^[0-9a-f]{64}$'
  );

create index if not exists documents_upload_finalized_idx
  on public.documents(upload_finalized_at)
  where upload_finalized_at is not null;
