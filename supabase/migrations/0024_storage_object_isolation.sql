-- Storage Object Isolation & Signed Access V1
-- Nadid uses a private bucket and server-issued signed upload URLs.
-- Browser roles must not directly enumerate/read/write/delete storage objects.

drop policy if exists "nadid_documents_deny_anon" on storage.objects;
drop policy if exists "nadid_documents_deny_authenticated" on storage.objects;

create policy "nadid_documents_deny_anon"
on storage.objects
for all
to anon
using (bucket_id <> 'nadid-documents')
with check (bucket_id <> 'nadid-documents');

create policy "nadid_documents_deny_authenticated"
on storage.objects
for all
to authenticated
using (bucket_id <> 'nadid-documents')
with check (bucket_id <> 'nadid-documents');
