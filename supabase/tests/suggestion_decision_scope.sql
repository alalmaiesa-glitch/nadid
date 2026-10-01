\set ON_ERROR_STOP on

-- Suggestion Decision Scope & Audit Trail V1

begin;

insert into auth.users (id, email, raw_user_meta_data)
values
  (
    '41000000-0000-0000-0000-000000000001',
    'decision-owner-a@nadid.local',
    '{}'::jsonb
  ),
  (
    '41000000-0000-0000-0000-000000000002',
    'decision-owner-b@nadid.local',
    '{}'::jsonb
  );

insert into public.documents (
  id, owner_id, title, filename, status
) values
  (
    '42000000-0000-0000-0000-000000000001',
    '41000000-0000-0000-0000-000000000001',
    'Decision A',
    'a.docx',
    'ready'
  ),
  (
    '42000000-0000-0000-0000-000000000002',
    '41000000-0000-0000-0000-000000000002',
    'Decision B',
    'b.docx',
    'ready'
  );

insert into public.document_versions (
  id, document_id, version_no, parent_version_id, is_source, status
) values
  (
    '43000000-0000-0000-0000-000000000001',
    '42000000-0000-0000-0000-000000000001',
    1, null, true, 'ready'
  ),
  (
    '43000000-0000-0000-0000-000000000002',
    '42000000-0000-0000-0000-000000000001',
    2,
    '43000000-0000-0000-0000-000000000001',
    false,
    'ready'
  ),
  (
    '43000000-0000-0000-0000-000000000003',
    '42000000-0000-0000-0000-000000000002',
    1, null, true, 'ready'
  );

insert into public.suggestions (
  id, version_id, client_suggestion_id, category, title, explanation,
  original_text, replacement_text, confidence, status, source_engine,
  evidence
) values
  (
    '44000000-0000-0000-0000-000000000001',
    '43000000-0000-0000-0000-000000000001',
    'same-client-id',
    'language', 'A v1', 'old version',
    'هاذا', 'هذا', 0.99, 'pending', 'test',
    '[{"source":"a-v1"}]'::jsonb
  ),
  (
    '44000000-0000-0000-0000-000000000002',
    '43000000-0000-0000-0000-000000000002',
    'same-client-id',
    'language', 'A v2', 'current version',
    'هاذا', 'هذا', 0.99, 'pending', 'test',
    '[{"source":"a-v2"}]'::jsonb
  ),
  (
    '44000000-0000-0000-0000-000000000003',
    '43000000-0000-0000-0000-000000000003',
    'same-client-id',
    'language', 'B v1', 'other owner',
    'هاذا', 'هذا', 0.99, 'pending', 'test',
    '[{"source":"b-v1"}]'::jsonb
  );

-- DEC-001: an old version cannot receive a new decision.
do $$
declare
  rejected boolean := false;
begin
  begin
    perform public.record_suggestion_decision(
      '42000000-0000-0000-0000-000000000001',
      1,
      'same-client-id',
      '41000000-0000-0000-0000-000000000001',
      'accepted'
    );
  exception when raise_exception then
    if sqlerrm = 'suggestion_version_changed' then
      rejected := true;
    else
      raise;
    end if;
  end;

  if not rejected then
    raise exception 'DEC-001 failed: old version decision was accepted';
  end if;
end
$$;

-- DEC-002: current scoped decision updates exactly one suggestion and writes audit.
select *
from public.record_suggestion_decision(
  '42000000-0000-0000-0000-000000000001',
  2,
  'same-client-id',
  '41000000-0000-0000-0000-000000000001',
  'accepted'
);

do $$
begin
  if (
    select status
    from public.suggestions
    where id = '44000000-0000-0000-0000-000000000002'
  ) <> 'accepted' then
    raise exception 'DEC-002 failed: target suggestion not accepted';
  end if;

  if (
    select status
    from public.suggestions
    where id = '44000000-0000-0000-0000-000000000001'
  ) <> 'pending' then
    raise exception 'DEC-002 failed: old-version suggestion was modified';
  end if;

  if (
    select status
    from public.suggestions
    where id = '44000000-0000-0000-0000-000000000003'
  ) <> 'pending' then
    raise exception 'DEC-002 failed: other-owner suggestion was modified';
  end if;

  if (
    select count(*)
    from public.suggestion_decisions
    where suggestion_id = '44000000-0000-0000-0000-000000000002'
      and decision = 'accepted'
      and suggestion_snapshot->>'original_text' = 'هاذا'
      and suggestion_snapshot->>'replacement_text' = 'هذا'
      and suggestion_snapshot->>'status_before' = 'pending'
  ) <> 1 then
    raise exception 'DEC-002 failed: audit snapshot missing';
  end if;
end
$$;

-- DEC-003: an owner cannot target another owner's document.
do $$
declare
  rejected boolean := false;
begin
  begin
    perform public.record_suggestion_decision(
      '42000000-0000-0000-0000-000000000001',
      2,
      'same-client-id',
      '41000000-0000-0000-0000-000000000002',
      'rejected'
    );
  exception when raise_exception then
    if sqlerrm = 'suggestion_scope_not_found' then
      rejected := true;
    else
      raise;
    end if;
  end;

  if not rejected then
    raise exception 'DEC-003 failed: cross-owner decision was accepted';
  end if;
end
$$;

-- DEC-004: authenticated clients cannot execute the privileged mutation RPC.
do $$
begin
  if has_function_privilege(
    'authenticated',
    'public.record_suggestion_decision(uuid,integer,text,uuid,text)',
    'EXECUTE'
  ) then
    raise exception 'DEC-004 failed: authenticated can execute decision RPC';
  end if;
end
$$;

rollback;

select 'Suggestion Decision Scope & Audit Trail PostgreSQL V1: PASS' as result;
