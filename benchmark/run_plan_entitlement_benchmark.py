from __future__ import annotations
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
DEFAULT_CONFIG=ROOT/"plan_entitlements"/"v1.json"
MIG=REPO/"supabase"/"migrations"/"0030_plan_entitlement_enforcement.sql"
HELP=REPO/"lib"/"server"/"plan-entitlements.ts"
ROUTES={
"context":REPO/"app"/"api"/"documents"/"[id]"/"context"/"route.ts",
"deep":REPO/"app"/"api"/"documents"/"[id]"/"deep-review"/"route.ts",
"versions":REPO/"app"/"api"/"documents"/"[id]"/"versions"/"route.ts",
"export":REPO/"app"/"api"/"documents"/"[id]"/"export"/"route.ts",
}
def row(i,ok):
 return {"id":i,"passed":ok,"observed":{"ok":ok},"failures":[] if ok else ["entitlement_guard_missing"]}
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--config",type=Path,default=DEFAULT_CONFIG)
 p.add_argument("--report",type=Path)
 p.add_argument("--enforce",action="store_true")
 a=p.parse_args()
 m=MIG.read_text();h=HELP.read_text();r={k:v.read_text() for k,v in ROUTES.items()}
 checks=[
 ("ENT-001","get_effective_billing_plan" in m and "security definer" in m),
 ("ENT-002","free_monthly" in m and "current_period_end" in m),
 ("ENT-003","PLAN_ENTITLEMENT_REQUIRED" in h and "status: 403" in h),
 ("ENT-004",'"context_review"' in r["context"] and "enforcePlanEntitlement(" in r["context"]),
 ("ENT-005",'"deep_review"' in r["deep"] and r["deep"].count("enforcePlanEntitlement(")==1),
 ("ENT-006",'"export"' in r["versions"] and "enforcePlanEntitlement(" in r["versions"]),
 ("ENT-007",'"export"' in r["export"] and "enforcePlanEntitlement(" in r["export"]),
 ("ENT-008","to service_role" in m),
 ]
 cases=[row(i,ok) for i,ok in checks]
 failed=[c["id"] for c in cases if not c["passed"]]
 report={"schema_version":1,"benchmark":"plan_entitlement_enforcement_v1","cases":cases,
 "summary":{"passed":not failed,"passed_cases":len(cases)-len(failed),"total_cases":len(cases),"failed_cases":failed}}
 out=json.dumps(report,ensure_ascii=False,indent=2);print(out)
 if a.report:
  a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(out+"\n")
 return 1 if a.enforce and failed else 0
if __name__=="__main__":raise SystemExit(main())
