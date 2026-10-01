from __future__ import annotations
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
DEFAULT_CONFIG=ROOT/"subscription_transition"/"v1.json"
MIG=REPO/"supabase"/"migrations"/"0031_subscription_transition_safety.sql"

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--config",type=Path,default=DEFAULT_CONFIG)
 p.add_argument("--report",type=Path)
 p.add_argument("--enforce",action="store_true")
 a=p.parse_args()
 m=MIG.read_text()
 checks=[
  ("SUB-001","s.status = 'active'" in m),
  ("SUB-002","s.current_period_start is not null" in m),
  ("SUB-003","s.current_period_end is not null" in m),
  ("SUB-004","s.current_period_start <= clock_timestamp()" in m and "s.current_period_end > clock_timestamp()" in m),
  ("SUB-005","s.current_period_end > s.current_period_start" in m),
  ("SUB-006","where bp.id = 'free_monthly'" in m and "not exists (select 1 from active_paid)" in m),
  ("SUB-007","from public.get_effective_billing_plan(p_user_id) as plan" in m),
  ("SUB-008","revoke all on function public.get_effective_billing_plan(uuid)" in m and "to service_role" in m),
 ]
 cases=[{"id":i,"passed":ok,"observed":{"ok":ok},"failures":[] if ok else ["subscription_transition_guard_missing"]} for i,ok in checks]
 failed=[c["id"] for c in cases if not c["passed"]]
 report={"schema_version":1,"benchmark":"subscription_state_entitlement_transition_safety_v1","cases":cases,
 "summary":{"passed":not failed,"passed_cases":len(cases)-len(failed),"total_cases":len(cases),"failed_cases":failed}}
 out=json.dumps(report,ensure_ascii=False,indent=2);print(out)
 if a.report:
  a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(out+"\n")
 return 1 if a.enforce and failed else 0
if __name__=="__main__":raise SystemExit(main())
