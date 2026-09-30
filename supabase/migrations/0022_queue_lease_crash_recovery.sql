-- Queue Lease, Retry & Crash Recovery V1
-- Prevent final-attempt jobs from remaining stuck forever and allow active
-- workers to renew long-running leases so healthy work is not reclaimed.

create or replace function public.renew_processing_job_lease(
  p_job_id uuid,
  p_worker_id text
)
returns boolean
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  v_updated integer := 0;
begin
  update public.processing_jobs
  set
    locked_at = now(),
    updated_at = now()
  where id = p_job_id
    and status = 'processing'
    and locked_by = p_worker_id;

  get diagnostics v_updated = row_count;
  return v_updated = 1;
end;
$$;

revoke all on function public.renew_processing_job_lease(uuid, text) from public;
revoke all on function public.renew_processing_job_lease(uuid, text) from anon;
revoke all on function public.renew_processing_job_lease(uuid, text) from authenticated;
grant execute on function public.renew_processing_job_lease(uuid, text) to service_role;


create or replace function public.claim_processing_job(
  p_worker_id text
)
returns setof public.processing_jobs
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  v_job public.processing_jobs;
  v_exhausted record;
  v_lease_timeout interval := interval '15 minutes';
begin
  -- A worker may die after claiming the final allowed attempt. Such a row
  -- cannot be reclaimed because attempts is already max_attempts. Reap it
  -- explicitly so neither the job nor its document remains processing forever.
  for v_exhausted in
    update public.processing_jobs
    set
      status = 'failed',
      locked_at = null,
      locked_by = null,
      last_error = case
        when coalesce(last_error, '') = ''
          then 'worker_lease_expired_after_final_attempt'
        else left(
          last_error || '; worker_lease_expired_after_final_attempt',
          1000
        )
      end,
      updated_at = now()
    where status = 'processing'
      and attempts >= max_attempts
      and locked_at is not null
      and locked_at < now() - v_lease_timeout
    returning document_id, job_type
  loop
    update public.documents
    set
      status = case
        when v_exhausted.job_type = 'deep_review'
          then 'partial_ready'
        else 'failed'
      end,
      updated_at = now()
    where id = v_exhausted.document_id;
  end loop;

  select *
  into v_job
  from public.processing_jobs
  where attempts < max_attempts
    and (
      (status = 'queued' and available_at <= now())
      or
      (
        status = 'processing'
        and locked_at is not null
        and locked_at < now() - v_lease_timeout
      )
    )
  order by
    case when status = 'processing' then 0 else 1 end,
    created_at asc
  for update skip locked
  limit 1;

  if not found then
    return;
  end if;

  update public.processing_jobs
  set
    status = 'processing',
    attempts = attempts + 1,
    locked_at = now(),
    locked_by = p_worker_id,
    updated_at = now()
  where id = v_job.id
  returning * into v_job;

  return next v_job;
end;
$$;

revoke all on function public.claim_processing_job(text) from public;
revoke all on function public.claim_processing_job(text) from anon;
revoke all on function public.claim_processing_job(text) from authenticated;
grant execute on function public.claim_processing_job(text) to service_role;
