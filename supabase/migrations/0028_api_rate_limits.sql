-- API Rate Limits & Abuse Quotas V1
-- One rolling fixed window row per user/action. Atomic UPSERT keeps the
-- limiter consistent across multiple serverless instances without row growth.

create table if not exists public.api_rate_windows (
  user_id uuid not null references auth.users(id) on delete cascade,
  action text not null,
  window_started_at timestamptz not null,
  request_count integer not null default 0 check (request_count >= 0),
  updated_at timestamptz not null default now(),
  primary key (user_id, action)
);

alter table public.api_rate_windows enable row level security;

revoke all on public.api_rate_windows from anon, authenticated;

create or replace function public.consume_api_rate_limit(
  p_user_id uuid,
  p_action text,
  p_window_seconds integer,
  p_limit integer
)
returns table (
  allowed boolean,
  remaining integer,
  retry_after_seconds integer
)
language plpgsql
security definer
set search_path = public
as $$
declare
  now_ts timestamptz := clock_timestamp();
  current_count integer;
  current_start timestamptz;
  elapsed_seconds integer;
begin
  if p_user_id is null
    or coalesce(length(trim(p_action)), 0) = 0
    or p_window_seconds < 1
    or p_limit < 1
  then
    raise exception 'invalid_rate_limit_policy'
      using errcode = 'P0001';
  end if;

  insert into public.api_rate_windows (
    user_id,
    action,
    window_started_at,
    request_count,
    updated_at
  )
  values (
    p_user_id,
    p_action,
    now_ts,
    1,
    now_ts
  )
  on conflict (user_id, action)
  do update set
    window_started_at = case
      when extract(
        epoch from (now_ts - api_rate_windows.window_started_at)
      ) >= p_window_seconds
      then now_ts
      else api_rate_windows.window_started_at
    end,
    request_count = case
      when extract(
        epoch from (now_ts - api_rate_windows.window_started_at)
      ) >= p_window_seconds
      then 1
      else api_rate_windows.request_count + 1
    end,
    updated_at = now_ts
  returning
    api_rate_windows.request_count,
    api_rate_windows.window_started_at
  into current_count, current_start;

  elapsed_seconds := greatest(
    0,
    floor(extract(epoch from (now_ts - current_start)))::integer
  );

  return query
  select
    current_count <= p_limit,
    greatest(p_limit - current_count, 0),
    case
      when current_count <= p_limit then 0
      else greatest(p_window_seconds - elapsed_seconds, 1)
    end;
end;
$$;

revoke all on function public.consume_api_rate_limit(
  uuid, text, integer, integer
) from public, anon, authenticated;

grant execute on function public.consume_api_rate_limit(
  uuid, text, integer, integer
) to service_role;
