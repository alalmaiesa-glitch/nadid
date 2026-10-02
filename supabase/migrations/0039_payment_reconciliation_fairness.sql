-- Payment Reconciliation Fairness, Claiming & Starvation Safety V1

alter table public.payments
  add column if not exists reconciliation_checked_at timestamptz null;

create index if not exists payments_reconciliation_fairness_idx
  on public.payments(
    provider,
    status,
    reconciliation_checked_at asc nulls first,
    updated_at asc,
    id
  )
  where provider_payment_id is not null;

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
language plpgsql
security definer
set search_path = public
as $$
declare
  v_limit integer;
begin
  v_limit := least(greatest(coalesce(p_limit, 25), 1), 100);

  return query
  with candidates as (
    select p.id
    from public.payments p
    where p.provider = 'moyasar'
      and p.status in ('pending', 'paid', 'partially_refunded')
      and p.provider_payment_id is not null
    order by
      p.reconciliation_checked_at asc nulls first,
      p.updated_at asc,
      p.id
    for update skip locked
    limit v_limit
  )
  update public.payments p
  set reconciliation_checked_at = clock_timestamp()
  from candidates c
  where p.id = c.id
  returning
    p.id,
    p.provider_payment_id,
    p.status,
    p.updated_at,
    p.reconciliation_checked_at;
end;
$$;

revoke all on function public.claim_payment_reconciliation_batch(integer)
from public, anon, authenticated;

grant execute on function public.claim_payment_reconciliation_batch(integer)
to service_role;
