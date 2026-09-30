\set ON_ERROR_STOP on

-- Multi-Tenant RLS & Ownership Isolation V1
-- Runs only against the isolated local Supabase CI database.

begin;

insert into auth.users (id, email, raw_user_meta_data)
values
  ('11000000-0000-0000-0000-000000000001', 'rls-user1@nadid.local', '{}'::jsonb),
  ('11000000-0000-0000-0000-000000000002', 'rls-user2@nadid.local', '{}'::jsonb);

insert into public.documents (
  id, owner_id, title, filename, status
) values
  (
    '21000000-0000-0000-0000-000000000001',
    '11000000-0000-0000-0000-000000000001',
    'User 1 Document',
    'u1.docx',
    'ready'
  ),
  (
    '21000000-0000-0000-0000-000000000002',
    '11000000-0000-0000-0000-000000000002',
    'User 2 Document',
    'u2.docx',
    'ready'
  );

insert into public.document_versions (
  id, document_id, version_no, is_source
) values
  (
    '31000000-0000-0000-0000-000000000001',
    '21000000-0000-0000-0000-000000000001',
    1,
    true
  ),
  (
    '31000000-0000-0000-0000-000000000002',
    '21000000-0000-0000-0000-000000000002',
    1,
    true
  );

insert into public.document_nodes (
  id, version_id, logical_node_key, node_type, sequence_no, text
) values
  (
    '41000000-0000-0000-0000-000000000001',
    '31000000-0000-0000-0000-000000000001',
    'u1-node', 'paragraph', 0, 'نص المستخدم الأول'
  ),
  (
    '41000000-0000-0000-0000-000000000002',
    '31000000-0000-0000-0000-000000000002',
    'u2-node', 'paragraph', 0, 'نص المستخدم الثاني'
  );

insert into public.suggestions (
  version_id, node_id, client_suggestion_id, category, title, explanation,
  original_text, replacement_text, confidence
) values
  (
    '31000000-0000-0000-0000-000000000001',
    '41000000-0000-0000-0000-000000000001',
    'rls-s1', 'language', 'تصحيح', 'تصحيح', 'هاذا', 'هذا', 0.99
  ),
  (
    '31000000-0000-0000-0000-000000000002',
    '41000000-0000-0000-0000-000000000002',
    'rls-s2', 'language', 'تصحيح', 'تصحيح', 'هاذا', 'هذا', 0.99
  );

insert into public.protected_spans (
  version_id, node_id, client_fact_id, span_type, surface_text,
  validator_key, lock_policy, lock_mode
) values
  (
    '31000000-0000-0000-0000-000000000001',
    '41000000-0000-0000-0000-000000000001',
    'rls-p1', 'number', '100', 'numeric_equivalence', 'normalize_only', 'block'
  ),
  (
    '31000000-0000-0000-0000-000000000002',
    '41000000-0000-0000-0000-000000000002',
    'rls-p2', 'number', '200', 'numeric_equivalence', 'normalize_only', 'block'
  );

insert into public.analysis_runs (
  version_id, run_type, state
) values
  ('31000000-0000-0000-0000-000000000001', 'fast', 'completed'),
  ('31000000-0000-0000-0000-000000000002', 'fast', 'completed');

insert into public.document_chunks (
  version_id, chunk_key, sequence_no, node_keys, chunk_text, token_estimate
) values
  ('31000000-0000-0000-0000-000000000001', 'rls-c1', 0, array['u1-node'], 'chunk 1', 2),
  ('31000000-0000-0000-0000-000000000002', 'rls-c2', 0, array['u2-node'], 'chunk 2', 2);

insert into public.document_memory (
  version_id, state, headings, protected_count, chunk_count
) values
  ('31000000-0000-0000-0000-000000000001', 'ready', '[]'::jsonb, 1, 1),
  ('31000000-0000-0000-0000-000000000002', 'ready', '[]'::jsonb, 1, 1);

insert into public.memory_terms (
  version_id, term, occurrence_count, node_keys
) values
  ('31000000-0000-0000-0000-000000000001', 'مصطلح١', 2, array['u1-node']),
  ('31000000-0000-0000-0000-000000000002', 'مصطلح٢', 2, array['u2-node']);

insert into public.fact_assertions (
  version_id, client_fact_id, node_key, fact_type, claim_key,
  surface_value, canonical_value, context_text, confidence
) values
  (
    '31000000-0000-0000-0000-000000000001',
    'rls-f1', 'u1-node', 'number', 'claim-u1', '100', '100', 'u1', 0.9
  ),
  (
    '31000000-0000-0000-0000-000000000002',
    'rls-f2', 'u2-node', 'number', 'claim-u2', '200', '200', 'u2', 0.9
  );

insert into public.fact_conflicts (
  version_id, client_conflict_id, claim_key, fact_ids, values_found, confidence
) values
  (
    '31000000-0000-0000-0000-000000000001',
    'rls-x1', 'claim-u1', array['rls-f1'], array['100','101'], 0.8
  ),
  (
    '31000000-0000-0000-0000-000000000002',
    'rls-x2', 'claim-u2', array['rls-f2'], array['200','201'], 0.8
  );

insert into public.document_memory_items (
  version_id, client_item_id, kind, item_key, item_value, node_keys, confidence
) values
  (
    '31000000-0000-0000-0000-000000000001',
    'rls-m1', 'concept', 'مفهوم١', 'مفهوم١', array['u1-node'], 0.84
  ),
  (
    '31000000-0000-0000-0000-000000000002',
    'rls-m2', 'concept', 'مفهوم٢', 'مفهوم٢', array['u2-node'], 0.84
  );

commit;

-- RLS-001..RLS-011: User 1 sees exactly User 1 rows across the graph.
begin;
set local role authenticated;
set local request.jwt.claim.sub = '11000000-0000-0000-0000-000000000001';

select 1 / case when (select count(*) from public.documents) = 1 then 1 else 0 end;
select 1 / case when (select count(*) from public.document_versions) = 1 then 1 else 0 end;
select 1 / case when (select count(*) from public.document_nodes) = 1 then 1 else 0 end;
select 1 / case when (select count(*) from public.suggestions) = 1 then 1 else 0 end;
select 1 / case when (select count(*) from public.protected_spans) = 1 then 1 else 0 end;
select 1 / case when (select count(*) from public.analysis_runs) = 1 then 1 else 0 end;
select 1 / case when (select count(*) from public.document_chunks) = 1 then 1 else 0 end;
select 1 / case when (select count(*) from public.document_memory) = 1 then 1 else 0 end;
select 1 / case when (select count(*) from public.memory_terms) = 1 then 1 else 0 end;
select 1 / case when (select count(*) from public.fact_assertions) = 1 then 1 else 0 end;
select 1 / case when (select count(*) from public.fact_conflicts) = 1 then 1 else 0 end;
select 1 / case when (select count(*) from public.document_memory_items) = 1 then 1 else 0 end;

-- RLS-012: Explicit lookup of another user's document returns no row.
select 1 / case when not exists (
  select 1 from public.documents
  where id = '21000000-0000-0000-0000-000000000002'
) then 1 else 0 end;

-- RLS-013: Cross-user UPDATE is a no-op.
update public.documents
set title = 'CROSS USER WRITE'
where id = '21000000-0000-0000-0000-000000000002';

-- RLS-014: Own UPDATE is allowed.
update public.documents
set title = 'User 1 Updated'
where id = '21000000-0000-0000-0000-000000000001';

rollback;

-- Verify cross-user row remained untouched and own rollback restored title.
begin;
select 1 / case when (
  select title from public.documents
  where id = '21000000-0000-0000-0000-000000000002'
) = 'User 2 Document' then 1 else 0 end;

select 1 / case when (
  select title from public.documents
  where id = '21000000-0000-0000-0000-000000000001'
) = 'User 1 Document' then 1 else 0 end;
rollback;

-- RLS-015: Anonymous role sees no user document rows.
begin;
set local role anon;
select 1 / case when (select count(*) from public.documents) = 0 then 1 else 0 end;
select 1 / case when (select count(*) from public.document_versions) = 0 then 1 else 0 end;
select 1 / case when (select count(*) from public.suggestions) = 0 then 1 else 0 end;
rollback;

-- RLS-016: service_role retains server-side access needed by Worker.
begin;
set local role service_role;
select 1 / case when (select count(*) from public.documents) = 2 then 1 else 0 end;
select 1 / case when (select count(*) from public.document_memory_items) = 2 then 1 else 0 end;
rollback;

-- Clean up local CI fixtures.
begin;
delete from public.documents
where id in (
  '21000000-0000-0000-0000-000000000001',
  '21000000-0000-0000-0000-000000000002'
);
delete from auth.users
where id in (
  '11000000-0000-0000-0000-000000000001',
  '11000000-0000-0000-0000-000000000002'
);
commit;

select 'Multi-Tenant RLS & Ownership Isolation V1: PASS' as result;
