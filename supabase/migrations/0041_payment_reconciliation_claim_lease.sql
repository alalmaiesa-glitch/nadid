-- Payment Reconciliation Claim Lease & Overlap Suppression V1

alter table public.payments
  add column if not exists reconciliation_claimed_until timestamptz null;

create index if not exists payments_reconciliation_claim_lease_idx
  on public.payments(
    provider,
    status,
    reconciliation_claimed_until,
    reconciliation_checked_at asc nulls first,
    updated_at asc,
    id
  )
  where provider_payment_id is not null;

drop function if exists public.claim_payment_reconciliation_batch(integer);

create or replace function public.claim_payment_reconciliation_batch(
  p_limit integer,
  p_lease_seconds integer
)
returns table (
  id uuid,
  provider_payment_id text,
  status text,
  updated_at timestamptz,
  reconciliation_checked_at timestamptz,
  reconciliation_claimed_until timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_limit integer;
  v_lease_seconds integer;
  v_now timestamptz := clock_timestamp();
begin
  v_limit := least(greatest(coalesce(p_limit, 25), 1), 100);
  v_lease_seconds := least(
    greatest(coalesce(p_lease_seconds, 900), 60),
    3600
  );

  return query
  with candidates as (
    select p.id
    from public.payments p
    where p.provider = 'moyasar'
      and p.status in ('pending', 'paid', 'partially_refunded')
      and p.provider_payment_id is not null
      and (
        p.reconciliation_claimed_until is null
        or p.reconciliation_claimed_until <= v_now
      )
    order by
      p.reconciliation_checked_at asc nulls first,
      p.updated_at asc,
      p.id
    for update skip locked
    limit v_limit
  )
  update public.payments p
  set reconciliation_checked_at = v_now,
      reconciliation_claimed_until =
        v_now + make_interval(secs => v_lease_seconds)
  from candidates c
  where p.id = c.id
  returning
    p.id,
    p.provider_payment_id,
    p.status,
    p.updated_at,
    p.reconciliation_checked_at,
    p.reconciliation_claimed_until;
end;
$$;

-- Backward-compatible V1 fairness signature. It cannot bypass the lease:
-- legacy callers are delegated to the leased implementation with 900 seconds.
create or replace function public.claim_payment_reconciliation_batch(
  p_limit integer default 25
)
returns table (
  id uuid,
  provider_payment_id text,
  status text,
  updated_at timestamptz,
  reconciliation_checked_at timestamptz
)
language sql
security definer
set search_path = public
as $$
  select
    c.id,
    c.provider_payment_id,
    c.status,
    c.updated_at,
    c.reconciliation_checked_at
  from public.claim_payment_reconciliation_batch(p_limit, 900) c;
$$;

revoke all on function public.claim_payment_reconciliation_batch(integer, integer)
from public, anon, authenticated;
revoke all on function public.claim_payment_reconciliation_batch(integer)
from public, anon, authenticated;

grant execute on function public.claim_payment_reconciliation_batch(integer, integer)
to service_role;
grant execute on function public.claim_payment_reconciliation_batch(integer)
to service_role;
