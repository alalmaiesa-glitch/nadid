\set ON_ERROR_STOP on

-- Local PostgreSQL Fault Injection V1
-- Uses fixed UUIDs inside the isolated CI database only.

begin;

insert into auth.users (id, email, raw_user_meta_data)
values (
  '10000000-0000-0000-0000-000000000001',
  'fault-injection@nadid.local',
  '{}'::jsonb
);

insert into public.documents (
  id, owner_id, title, filename, status
) values (
  '20000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000001',
  'Fault Injection',
  'fault.docx',
  'ready'
);

insert into public.document_versions (
  id, document_id, version_no, is_source
) values
(
  '30000000-0000-0000-0000-000000000001',
  '20000000-0000-0000-0000-000000000001',
  1,
  true
),
(
  '30000000-0000-0000-0000-000000000002',
  '20000000-0000-0000-0000-000000000001',
  2,
  false
);

-- DBF-001: Same deterministic suggestion id is allowed across versions.
insert into public.suggestions (
  version_id, client_suggestion_id, category, title, explanation,
  original_text, replacement_text, confidence
) values
(
  '30000000-0000-0000-0000-000000000001',
  'same-client-id',
  'language',
  'اختبار',
  'اختبار',
  'هاذا',
  'هذا',
  0.99
),
(
  '30000000-0000-0000-0000-000000000002',
  'same-client-id',
  'language',
  'اختبار',
  'اختبار',
  'هاذا',
  'هذا',
  0.99
);

do $$
begin
  if (
    select count(*)
    from public.suggestions
    where client_suggestion_id = 'same-client-id'
  ) <> 2 then
    raise exception 'DBF-001 failed: cross-version identity scope';
  end if;
end
$$;

-- DBF-002: Duplicate deterministic suggestion id in one version is rejected.
do $$
begin
  begin
    insert into public.suggestions (
      version_id, client_suggestion_id, category, title, explanation,
      original_text, replacement_text, confidence
    ) values (
      '30000000-0000-0000-0000-000000000001',
      'same-client-id',
      'language',
      'مكرر',
      'مكرر',
      'لاكن',
      'لكن',
      0.99
    );
    raise exception 'DBF-002 failed: duplicate unexpectedly accepted';
  exception
    when unique_violation then
      null;
  end;
end
$$;

-- Seed every deep artifact table for Version 1.
insert into public.document_chunks (
  version_id, chunk_key, sequence_no, node_keys, chunk_text, token_estimate
) values (
  '30000000-0000-0000-0000-000000000001',
  'chunk-1', 0, array['node-1'], 'نص تجريبي', 10
);

insert into public.document_memory (
  version_id, state, headings, protected_count, chunk_count
) values (
  '30000000-0000-0000-0000-000000000001',
  'building', '[]'::jsonb, 1, 1
);

insert into public.memory_terms (
  version_id, term, occurrence_count, node_keys
) values (
  '30000000-0000-0000-0000-000000000001',
  'المشروع', 2, array['node-1']
);

insert into public.fact_assertions (
  version_id, client_fact_id, node_key, fact_type, claim_key,
  surface_value, canonical_value, context_text, confidence
) values (
  '30000000-0000-0000-0000-000000000001',
  'fact-1', 'node-1', 'number', 'claim-1',
  '100', '100', 'القيمة 100', 0.92
);

insert into public.fact_conflicts (
  version_id, client_conflict_id, claim_key, fact_ids,
  values_found, confidence
) values (
  '30000000-0000-0000-0000-000000000001',
  'conflict-1', 'claim-1', array['fact-1'],
  array['100','200'], 0.80
);

insert into public.document_memory_items (
  version_id, client_item_id, kind, item_key, item_value,
  node_keys, confidence
) values (
  '30000000-0000-0000-0000-000000000001',
  'memory-1', 'concept', 'المشروع', 'المشروع',
  array['node-1'], 0.84
);

-- DBF-003: Partial version cleanup cascades through every deep artifact table.
delete from public.document_versions
where id = '30000000-0000-0000-0000-000000000001';

do $$
declare
  leftovers bigint;
begin
  select
    (select count(*) from public.document_chunks where version_id = '30000000-0000-0000-0000-000000000001') +
    (select count(*) from public.document_memory where version_id = '30000000-0000-0000-0000-000000000001') +
    (select count(*) from public.memory_terms where version_id = '30000000-0000-0000-0000-000000000001') +
    (select count(*) from public.fact_assertions where version_id = '30000000-0000-0000-0000-000000000001') +
    (select count(*) from public.fact_conflicts where version_id = '30000000-0000-0000-0000-000000000001') +
    (select count(*) from public.document_memory_items where version_id = '30000000-0000-0000-0000-000000000001') +
    (select count(*) from public.suggestions where version_id = '30000000-0000-0000-0000-000000000001')
  into leftovers;

  if leftovers <> 0 then
    raise exception 'DBF-003 failed: cascade left % rows', leftovers;
  end if;
end
$$;

commit;

-- DBF-004: A failed write transaction leaves no partial version or child rows.
begin;

insert into public.document_versions (
  id, document_id, version_no, is_source
) values (
  '30000000-0000-0000-0000-000000000003',
  '20000000-0000-0000-0000-000000000001',
  3,
  false
);

insert into public.document_chunks (
  version_id, chunk_key, sequence_no, node_keys, chunk_text, token_estimate
) values (
  '30000000-0000-0000-0000-000000000003',
  'transient-chunk', 0, array['node-x'], 'لن يبقى', 3
);

rollback;

do $$
begin
  if exists (
    select 1 from public.document_versions
    where id = '30000000-0000-0000-0000-000000000003'
  ) then
    raise exception 'DBF-004 failed: rolled-back version survived';
  end if;

  if exists (
    select 1 from public.document_chunks
    where version_id = '30000000-0000-0000-0000-000000000003'
  ) then
    raise exception 'DBF-004 failed: rolled-back child survived';
  end if;
end
$$;

-- DBF-005: Clear-then-rebuild retry produces exactly one deterministic row.
begin;

insert into public.document_chunks (
  version_id, chunk_key, sequence_no, node_keys, chunk_text, token_estimate
) values (
  '30000000-0000-0000-0000-000000000002',
  'retry-chunk', 0, array['node-r'], 'المحاولة الأولى', 4
);

delete from public.document_chunks
where version_id = '30000000-0000-0000-0000-000000000002';

insert into public.document_chunks (
  version_id, chunk_key, sequence_no, node_keys, chunk_text, token_estimate
) values (
  '30000000-0000-0000-0000-000000000002',
  'retry-chunk', 0, array['node-r'], 'المحاولة الثانية', 4
);

do $$
begin
  if (
    select count(*)
    from public.document_chunks
    where version_id = '30000000-0000-0000-0000-000000000002'
      and chunk_key = 'retry-chunk'
  ) <> 1 then
    raise exception 'DBF-005 failed: retry duplicated deterministic row';
  end if;
end
$$;

rollback;

-- Keep the local CI database clean.
begin;
delete from public.documents
where id = '20000000-0000-0000-0000-000000000001';
delete from auth.users
where id = '10000000-0000-0000-0000-000000000001';
commit;

select 'Local PostgreSQL Fault Injection V1: PASS' as result;
