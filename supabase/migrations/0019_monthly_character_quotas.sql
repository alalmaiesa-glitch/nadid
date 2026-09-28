update public.billing_plans set entitlements =
  jsonb_set(coalesce(entitlements,'{}'::jsonb), '{monthly_characters}', to_jsonb(
    case id
      when 'free_monthly' then 50000
      when 'basic_monthly' then 500000
      when 'basic_yearly' then 500000
      when 'pro_monthly' then 2000000
      when 'pro_yearly' then 2000000
      else 0
    end
  ), true)
where id in ('free_monthly','basic_monthly','basic_yearly','pro_monthly','pro_yearly');
