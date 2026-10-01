-- Derived Version Lineage & Orphan-Safe Persistence V1
-- Run against the local Supabase database after all migrations.

begin;

do $$
declare
  doc_a uuid := '10000000-0000-0000-0000-000000000001';
  doc_b uuid := '10000000-0000-0000-0000-000000000002';
  a1 uuid := '20000000-0000-0000-0000-000000000001';
  a2 uuid := '20000000-0000-0000-0000-000000000002';
  b1 uuid := '30000000-0000-0000-0000-000000000001';
  rejected boolean;
begin
  insert into public.documents (
    id, title, filename, source_type, status
  ) values
    (doc_a, 'A', 'a.docx', 'docx', 'partial_ready'),
    (doc_b, 'B', 'b.docx', 'docx', 'partial_ready');

  insert into public.document_versions (
    id, document_id, version_no, is_source, status
  ) values
    (a1, doc_a, 1, true, 'ready'),
    (b1, doc_b, 1, true, 'ready');

  insert into public.document_versions (
    id, document_id, version_no, parent_version_id,
    is_source, status
  ) values (
    a2, doc_a, 2, a1, false, 'ready'
  );

  rejected := false;
  begin
    insert into public.document_versions (
      document_id, version_no, parent_version_id,
      is_source, status
    ) values (
      doc_a, 3, a1, false, 'ready'
    );
  exception when check_violation then
    rejected := true;
  end;
  if not rejected then
    raise exception 'lineage skipped-parent insert was accepted';
  end if;

  rejected := false;
  begin
    insert into public.document_versions (
      document_id, version_no, parent_version_id,
      is_source, status
    ) values (
      doc_a, 3, b1, false, 'ready'
    );
  exception when check_violation then
    rejected := true;
  end;
  if not rejected then
    raise exception 'cross-document parent was accepted';
  end if;

  rejected := false;
  begin
    insert into public.document_versions (
      document_id, version_no, parent_version_id,
      is_source, status
    ) values (
      doc_a, 3, null, false, 'ready'
    );
  exception when check_violation then
    rejected := true;
  end;
  if not rejected then
    raise exception 'derived version without parent was accepted';
  end if;

  rejected := false;
  begin
    insert into public.document_versions (
      document_id, version_no, parent_version_id,
      is_source, status
    ) values (
      doc_a, 2, null, true, 'ready'
    );
  exception
    when check_violation then
      rejected := true;
    when unique_violation then
      rejected := true;
  end;
  if not rejected then
    raise exception 'second source-shaped version was accepted';
  end if;
end;
$$;

rollback;
