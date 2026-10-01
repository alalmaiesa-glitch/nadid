\set ON_ERROR_STOP on

-- API Rate Limits & Abuse Quotas PostgreSQL V1

begin;

insert into auth.users (id, email, raw_user_meta_data)
values (
  '51000000-0000-0000-0000-000000000001',
  'rate-limit@nadid.local',
  '{}'::jsonb
);

-- RATE-DB-001: first two requests inside a 1-second window are allowed.
do $$
declare
  r record;
begin
  select * into r
  from public.consume_api_rate_limit(
    '51000000-0000-0000-0000-000000000001',
    'test_action',
    1,
    2
  );
  if not r.allowed or r.remaining <> 1 then
    raise exception 'RATE-DB-001 first request failed';
  end if;

  select * into r
  from public.consume_api_rate_limit(
    '51000000-0000-0000-0000-000000000001',
    'test_action',
    1,
    2
  );
  if not r.allowed or r.remaining <> 0 then
    raise exception 'RATE-DB-001 second request failed';
  end if;
end
$$;

-- RATE-DB-002: third request is rejected with a retry interval.
do $$
declare
  r record;
begin
  select * into r
  from public.consume_api_rate_limit(
    '51000000-0000-0000-0000-000000000001',
    'test_action',
    1,
    2
  );

  if r.allowed or r.retry_after_seconds < 1 then
    raise exception 'RATE-DB-002 limit was not enforced';
  end if;
end
$$;

-- RATE-DB-003: one row per user/action, not one row per request.
do $$
begin
  if (
    select count(*)
    from public.api_rate_windows
    where user_id = '51000000-0000-0000-0000-000000000001'
      and action = 'test_action'
  ) <> 1 then
    raise exception 'RATE-DB-003 rate window row growth detected';
  end if;
end
$$;

-- RATE-DB-004: authenticated clients cannot call the privileged counter RPC.
do $$
begin
  if has_function_privilege(
    'authenticated',
    'public.consume_api_rate_limit(uuid,text,integer,integer)',
    'EXECUTE'
  ) then
    raise exception 'RATE-DB-004 authenticated can execute limiter RPC';
  end if;
end
$$;

-- RATE-DB-005: the fixed window resets after expiry.
select pg_sleep(1.1);

do $$
declare
  r record;
begin
  select * into r
  from public.consume_api_rate_limit(
    '51000000-0000-0000-0000-000000000001',
    'test_action',
    1,
    2
  );

  if not r.allowed or r.remaining <> 1 then
    raise exception 'RATE-DB-005 expired window did not reset';
  end if;

  if (
    select request_count
    from public.api_rate_windows
    where user_id = '51000000-0000-0000-0000-000000000001'
      and action = 'test_action'
  ) <> 1 then
    raise exception 'RATE-DB-005 counter did not reset to one';
  end if;
end
$$;

rollback;

select 'API Rate Limits & Abuse Quotas PostgreSQL V1: PASS' as result;
