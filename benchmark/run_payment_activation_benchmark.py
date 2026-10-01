from __future__ import annotations
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent
DEFAULT_CONFIG=ROOT/"payment_activation"/"v1.json"
MIG=REPO/"supabase"/"migrations"/"0032_payment_activation_integrity.sql"
DBT=REPO/"lib"/"database.types.ts"
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--config",type=Path,default=DEFAULT_CONFIG)
 p.add_argument("--report",type=Path)
 p.add_argument("--enforce",action="store_true")
 a=p.parse_args()
 m=MIG.read_text();d=DBT.read_text()
 checks=[
  ("PAY-001","credit_topup" in m and "payments_purpose_check" in m),
  ("PAY-002","subscriptions_payment_unique_idx" in m and "payment_id uuid" in m),
  ("PAY-003","credit_topups_payment_unique_idx" in m),
  ("PAY-004","v_payment.status <> 'paid'" in m and "v_payment.purpose <> 'subscription'" in m and "v_payment.paid_at is null" in m),
  ("PAY-005","v_payment.amount_minor <> v_plan.amount_minor" in m and "upper(v_payment.currency) <> upper(v_plan.currency)" in m),
  ("PAY-006","v_start := v_payment.paid_at" in m and "interval '1 month'" in m and "interval '1 year'" in m),
  ("PAY-007","where payment_id = p_payment_id" in m and "payment_already_used_for_different_plan" in m),
  ("PAY-008","set status = 'cancelled'" in m and "where user_id = v_payment.user_id" in m),
  ("PAY-009","v_plan.tier = 'free'" in m),
  ("PAY-010","v_payment.purpose <> 'credit_topup'" in m and "payment_already_used_for_different_pack" in m),
  ("PAY-011","v_payment.amount_minor <> v_pack.amount_minor" in m and "v_pack.characters" in m),
  ("PAY-012","to service_role" in m and "activate_subscription_from_payment" in d and "activate_topup_from_payment" in d),
 ]
 cases=[{"id":i,"passed":ok,"observed":{"ok":ok},"failures":[] if ok else ["payment_activation_guard_missing"]} for i,ok in checks]
 failed=[c["id"] for c in cases if not c["passed"]]
 report={"schema_version":1,"benchmark":"payment_subscription_activation_integrity_v1","cases":cases,
 "summary":{"passed":not failed,"passed_cases":len(cases)-len(failed),"total_cases":len(cases),"failed_cases":failed}}
 out=json.dumps(report,ensure_ascii=False,indent=2);print(out)
 if a.report:
  a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(out+"\n")
 return 1 if a.enforce and failed else 0
if __name__=="__main__":raise SystemExit(main())
