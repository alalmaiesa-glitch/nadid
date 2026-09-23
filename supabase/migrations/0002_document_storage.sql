insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'nadid-documents',
  'nadid-documents',
  false,
  104857600,
  array['application/vnd.openxmlformats-officedocument.wordprocessingml.document']
)
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;
