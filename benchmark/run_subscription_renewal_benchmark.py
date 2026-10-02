from __future__ import annotations
import argparse, json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
MIG=REPO/"supabase"/"migrations"/"0037_subscription_renewal_continuity.sql"
TEST=REPO/"supabase"/"tests"/"subscription_renewal_continuity.sql"
DOC=REPO/"docs"/"SUBSCRIPTION_RENEWAL_CONTINUITY.md"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--report",type=Path)
    p.add_argument("--enforce",action="store_true")
    a=p.parse_args()
    m=MIG.read_text(encoding="utf-8")
    t=TEST.read_text(encoding="utf-8")
    d=DOC.read_text(encoding="utf-8")
    checks=[
      ("RENEW-001","v_current.plan_id = p_plan_id" in m),
      ("RENEW-002","max(s.current_period_end)" in m and "v_chain_end" in m),
      ("RENEW-003","greatest(" in m and "v_payment.paid_at" in m),
      ("RENEW-004","payment_id = p_payment_id" in m and "reused" in m),
      ("RENEW-005","plan_id <> p_plan_id" in m and "status = 'cancelled'" in m),
      ("RENEW-006","RENEW-DB-001" in t and "RENEW-DB-006" in t),
      ("RENEW-007","early renewal discarded paid time" in t),
      ("RENEW-008","queued renewal chain overlapped" in t),
      ("RENEW-009","replay created extra subscription" in t),
      ("RENEW-010","تغيير الخطة" in d and "paid_at" in d),
    ]
    cases=[{"id":i,"passed":ok,"observed":{"ok":ok},"failures":[] if ok else ["renewal_continuity_guard_missing"]} for i,ok in checks]
    failed=[c["id"] for c in cases if not c["passed"]]
    report={"schema_version":1,"benchmark":"subscription_renewal_billing_cycle_continuity_v1","cases":cases,
    "summary":{"passed":not failed,"passed_cases":len(cases)-len(failed),"total_cases":len(cases),"failed_cases":failed}}
    out=json.dumps(report,ensure_ascii=False,indent=2);print(out)
    if a.report:
      a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(out+"\n",encoding="utf-8")
    return 1 if a.enforce and failed else 0

if __name__=="__main__": raise SystemExit(main())
