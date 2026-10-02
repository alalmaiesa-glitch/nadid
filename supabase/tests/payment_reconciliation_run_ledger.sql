\set ON_ERROR_STOP on

-- Payment Reconciliation Run Ledger & Stale-Scheduler Detection PostgreSQL V1

begin;

-- RECON-RUN-DB-001: start creates a durable running row.
do $$
declare
  v_id uuid;
begin
  v_id := public.start_payment_reconciliation_run();

  if not exists (
    select 1
    from public.payment_reconciliation_runs
    where id = v_id
      and status = 'running'
      and completed_at is null
  ) then
    raise exception 'RECON-RUN-DB-001 run row not created';
  end if;
end
$$;

-- RECON-RUN-DB-002: finish is one-way and persists summary metrics.
do $$
declare
  v_id uuid;
  v_ok boolean;
  v_second boolean;
begin
  v_id := public.start_payment_reconciliation_run();

  v_ok := public.finish_payment_reconciliation_run(
    v_id, 'succeeded', 5, 3, 2, 0, null
  );

  if not v_ok then
    raise exception 'RECON-RUN-DB-002 first finish failed';
  end if;

  if not exists (
    select 1
    from public.payment_reconciliation_runs
    where id = v_id
      and status = 'succeeded'
      and completed_at is not null
      and scanned = 5
      and reconciled = 3
      and ignored = 2
      and failed = 0
  ) then
    raise exception 'RECON-RUN-DB-002 summary not persisted';
  end if;

  v_second := public.finish_payment_reconciliation_run(
    v_id, 'partial_failure', 99, 0, 0, 99, 'should-not-overwrite'
  );

  if v_second then
    raise exception 'RECON-RUN-DB-002 completed run was finalized twice';
  end if;

  if exists (
    select 1
    from public.payment_reconciliation_runs
    where id = v_id
      and scanned = 99
  ) then
    raise exception 'RECON-RUN-DB-002 completed run was mutated';
  end if;
end
$$;

-- RECON-RUN-DB-003: a recent success reports healthy.
do $$
declare
  h record;
begin
  perform public.finish_payment_reconciliation_run(
    public.start_payment_reconciliation_run(),
    'succeeded', 0, 0, 0, 0, null
  );

  select * into h
  from public.get_payment_reconciliation_health(2160);

  if h.stale or h.last_success_at is null then
    raise exception 'RECON-RUN-DB-003 recent success reported stale';
  end if;
end
$$;

-- RECON-RUN-DB-004: an old unfinished run is explicitly detectable.
do $$
declare
  v_id uuid;
  h record;
begin
  insert into public.payment_reconciliation_runs (
    started_at, status
  )
  values (
    clock_timestamp() - interval '3 days',
    'running'
  )
  returning id into v_id;

  select * into h
  from public.get_payment_reconciliation_health(2160);

  if not h.stale_running then
    raise exception 'RECON-RUN-DB-004 stale running job was not detected';
  end if;
end
$$;

-- RECON-RUN-DB-005: partial failure records its error without counting as success.
do $$
declare
  v_id uuid;
begin
  v_id := public.start_payment_reconciliation_run();

  perform public.finish_payment_reconciliation_run(
    v_id,
    'partial_failure',
    4,
    2,
    1,
    1,
    'PAYMENT_RECONCILIATION_PARTIAL_FAILURE'
  );

  if not exists (
    select 1
    from public.payment_reconciliation_runs
    where id = v_id
      and status = 'partial_failure'
      and failed = 1
      and error_code = 'PAYMENT_RECONCILIATION_PARTIAL_FAILURE'
  ) then
    raise exception 'RECON-RUN-DB-005 partial failure was not audited';
  end if;
end
$$;

-- RECON-RUN-DB-006: browser roles cannot read or execute the run ledger.
do $$
begin
  if has_table_privilege(
    'authenticated',
    'public.payment_reconciliation_runs',
    'SELECT'
  ) then
    raise exception 'RECON-RUN-DB-006 authenticated can read reconciliation runs';
  end if;

  if has_function_privilege(
    'authenticated',
    'public.start_payment_reconciliation_run()',
    'EXECUTE'
  ) then
    raise exception 'RECON-RUN-DB-006 authenticated can start reconciliation runs';
  end if;

  if has_function_privilege(
    'authenticated',
    'public.get_payment_reconciliation_health(integer)',
    'EXECUTE'
  ) then
    raise exception 'RECON-RUN-DB-006 authenticated can inspect reconciliation health';
  end if;
end
$$;

rollback;

select 'Payment Reconciliation Run Ledger & Stale-Scheduler Detection PostgreSQL V1: PASS' as result;
