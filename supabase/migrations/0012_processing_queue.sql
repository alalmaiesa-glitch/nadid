create table if not exists public.processing_jobs (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade,
  job_type text not null default 'initial_review'
    check (job_type in ('initial_review')),
  status text not null default 'queued'
    check (status in ('queued', 'processing', 'complete', 'failed')),
  attempts integer not null default 0 check (attempts >= 0),
  max_attempts integer not null default 3 check (max_attempts >= 1),
  available_at timestamptz not null default now(),
  locked_at timestamptz null,
  locked_by text null,
  last_error text null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz null,
  unique(document_id, job_type)
);

create index if not exists processing_jobs_claim_idx
  on public.processing_jobs(status, available_at, created_at);

create index if not exists processing_jobs_owner_created_idx
  on public.processing_jobs(owner_id, created_at desc);

alter table public.processing_jobs enable row level security;

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
begin
  select *
  into v_job
  from public.processing_jobs
  where attempts < max_attempts
    and (
      (status = 'queued' and available_at <= now())
      or
      (
        status = 'processing'
        and locked_at < now() - interval '15 minutes'
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
