-- Derived Version Lineage & Orphan-Safe Persistence V1
-- Enforce one linear version chain per document at the database boundary.

create or replace function public.enforce_document_version_lineage()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  parent_document_id uuid;
  parent_version_no integer;
begin
  -- ON DELETE SET NULL on the self-parent FK must not block a full document
  -- cascade. Allow that transient update only after the owning document row
  -- has already been removed. Direct parent detachment remains invalid.
  if (
    tg_op = 'UPDATE'
    and old.parent_version_id is not null
    and new.parent_version_id is null
    and not exists (
      select 1
      from public.documents d
      where d.id = new.document_id
    )
  ) then
    return new;
  end if;

  if new.version_no = 1 or new.is_source then
    if (
      new.version_no <> 1
      or new.is_source is not true
      or new.parent_version_id is not null
    ) then
      raise exception 'version_lineage_invalid_source'
        using errcode = '23514';
    end if;

    return new;
  end if;

  if new.parent_version_id is null then
    raise exception 'version_lineage_parent_required'
      using errcode = '23514';
  end if;

  select v.document_id, v.version_no
  into parent_document_id, parent_version_no
  from public.document_versions v
  where v.id = new.parent_version_id;

  if not found then
    raise exception 'version_lineage_parent_missing'
      using errcode = '23503';
  end if;

  if parent_document_id <> new.document_id then
    raise exception 'version_lineage_cross_document_parent'
      using errcode = '23514';
  end if;

  if parent_version_no <> new.version_no - 1 then
    raise exception 'version_lineage_parent_not_previous'
      using errcode = '23514';
  end if;

  if new.is_source then
    raise exception 'version_lineage_derived_marked_source'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

drop trigger if exists document_versions_lineage_guard
on public.document_versions;

create trigger document_versions_lineage_guard
before insert or update of
  document_id,
  version_no,
  parent_version_id,
  is_source
on public.document_versions
for each row
execute function public.enforce_document_version_lineage();

-- Fail migration rather than silently blessing an already-branched history.
do $$
begin
  if exists (
    select 1
    from public.document_versions child
    left join public.document_versions parent
      on parent.id = child.parent_version_id
    where
      (
        child.version_no = 1
        and (
          child.is_source is not true
          or child.parent_version_id is not null
        )
      )
      or (
        child.version_no > 1
        and (
          child.is_source is true
          or child.parent_version_id is null
          or parent.id is null
          or parent.document_id <> child.document_id
          or parent.version_no <> child.version_no - 1
        )
      )
  ) then
    raise exception 'existing_document_version_lineage_invalid';
  end if;
end;
$$;
