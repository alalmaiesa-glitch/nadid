create policy "processing_jobs_deny_anon"
on public.processing_jobs
for all
to anon
using (false)
with check (false);

create policy "processing_jobs_deny_authenticated"
on public.processing_jobs
for all
to authenticated
using (false)
with check (false);

create policy "worker_heartbeats_deny_anon"
on public.worker_heartbeats
for all
to anon
using (false)
with check (false);

create policy "worker_heartbeats_deny_authenticated"
on public.worker_heartbeats
for all
to authenticated
using (false)
with check (false);
