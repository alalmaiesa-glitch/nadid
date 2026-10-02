-- Payment Reconciliation Run Ledger & Stale-Scheduler Detection V1

create table if not exists public.payment_reconciliation_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default clock_timestamp(),
  completed_at timestamptz null,
  status text not null default 'running'
    check (status in ('running', 'succeeded', 'partial_failure', 'lookup_failure')),
  scanned integer not null default 0 check (scanned >= 0),
  reconciled integer not null default 0 check (reconciled >= 0),
  ignored integer not null default 0 check (ignored >= 0),
  failed integer not null default 0 check (failed >= 0),
  error_code text null,
  created_at timestamptz not null default clock_timestamp()
);

create index if not exists payment_reconciliation_runs_started_idx
  on public.payment_reconciliation_runs(started_at desc);

create index if not exists payment_reconciliation_runs_success_idx
  on public.payment_reconciliation_runs(completed_at desc)
  where status = 'succeeded';

alter table public.payment_reconciliation_runs enable row level security;

revoke all on table public.payment_reconciliation_runs
from public, anon, authenticated;

create or replace function public.start_payment_reconciliation_run()
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  v_id uuid;
begin
  insert into public.payment_reconciliation_runs default values
  returning id into v_id;

  return v_id;
end;
$$;

create or replace function public.finish_payment_reconciliation_run(
  p_run_id uuid,
  p_status text,
  p_scanned integer,
  p_reconciled integer,
  p_ignored integer,
  p_failed integer,
  p_error_code text default null
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_run_id is null
     or p_status not in ('succeeded', 'partial_failure', 'lookup_failure')
     or coalesce(p_scanned, -1) < 0
     or coalesce(p_reconciled, -1) < 0
     or coalesce(p_ignored, -1) < 0
     or coalesce(p_failed, -1) < 0
  then
    raise exception 'invalid_reconciliation_run_finish'
      using errcode = 'P0001';
  end if;

  update public.payment_reconciliation_runs
  set status = p_status,
      completed_at = clock_timestamp(),
      scanned = p_scanned,
      reconciled = p_reconciled,
      ignored = p_ignored,
      failed = p_failed,
      error_code = nullif(trim(coalesce(p_error_code, '')), '')
  where id = p_run_id
    and status = 'running'
    and completed_at is null;

  return found;
end;
$$;

create or replace function public.get_payment_reconciliation_health(
  p_max_age_minutes integer default 2160
)
returns table (
  last_started_at timestamptz,
  last_completed_at timestamptz,
  last_success_at timestamptz,
  oldest_running_at timestamptz,
  stale boolean,
  stale_running boolean
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_max_age integer;
  v_now timestamptz := clock_timestamp();
begin
  v_max_age := least(greatest(coalesce(p_max_age_minutes, 2160), 60), 10080);

  return query
  select
    (select max(r.started_at) from public.payment_reconciliation_runs r),
    (select max(r.completed_at) from public.payment_reconciliation_runs r),
    (
      select max(r.completed_at)
      from public.payment_reconciliation_runs r
      where r.status = 'succeeded'
    ),
    (
      select min(r.started_at)
      from public.payment_reconciliation_runs r
      where r.status = 'running'
        and r.completed_at is null
    ),
    (
      coalesce(
        (
          select max(r.completed_at)
          from public.payment_reconciliation_runs r
          where r.status = 'succeeded'
        ),
        '-infinity'::timestamptz
      ) < v_now - make_interval(mins => v_max_age)
    ),
    exists (
      select 1
      from public.payment_reconciliation_runs r
      where r.status = 'running'
        and r.completed_at is null
        and r.started_at < v_now - make_interval(mins => v_max_age)
    );
end;
$$;

revoke all on function public.start_payment_reconciliation_run()
from public, anon, authenticated;
revoke all on function public.finish_payment_reconciliation_run(
  uuid, text, integer, integer, integer, integer, text
) from public, anon, authenticated;
revoke all on function public.get_payment_reconciliation_health(integer)
from public, anon, authenticated;

grant execute on function public.start_payment_reconciliation_run()
to service_role;
grant execute on function public.finish_payment_reconciliation_run(
  uuid, text, integer, integer, integer, integer, text
) to service_role;
grant execute on function public.get_payment_reconciliation_health(integer)
to service_role;
