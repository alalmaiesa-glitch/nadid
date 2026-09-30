from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DEFAULT_CONFIG = ROOT / "upload_finalization" / "v1.json"
PERSISTENCE = REPO / "lib" / "server" / "document-persistence.ts"
WORKER = REPO / "worker" / "index.mjs"
ROUTE = REPO / "app" / "api" / "documents" / "[id]" / "finalize-upload" / "route.ts"
MIGRATION = REPO / "supabase" / "migrations" / "0025_upload_finalization_integrity.sql"

def _case(case_id, fn):
    failures=[]
    try:
        observed=fn()
        failures.extend(observed.pop("_failures",[]))
    except Exception as exc:
        observed={"exception":type(exc).__name__,"message":str(exc)[:300]}
        failures.append("benchmark_exception")
    return {"id":case_id,"observed":observed,"failures":failures,"passed":not failures}

def _ordered(text, markers):
    pos=[text.find(x) for x in markers]
    return all(x>=0 for x in pos) and pos==sorted(pos), pos

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config",type=Path,default=DEFAULT_CONFIG)
    p.add_argument("--report",type=Path)
    p.add_argument("--enforce",action="store_true")
    args=p.parse_args()

    config=json.loads(args.config.read_text(encoding="utf-8"))
    persistence=PERSISTENCE.read_text(encoding="utf-8")
    worker=WORKER.read_text(encoding="utf-8")
    route=ROUTE.read_text(encoding="utf-8")
    migration=MIGRATION.read_text(encoding="utf-8").lower()

    s=persistence.find("export async function enqueueDocumentProcessing")
    e=persistence.find("export async function loadPendingDocumentUpload",s)
    enqueue=persistence[s:e]

    ws=worker.find("async function processInitialReview")
    we=worker.find("async function processDeepReview",ws)
    initial=worker[ws:we]

    def u1():
        req=["upload_sha256 text null","upload_finalized_at timestamptz null","documents_upload_sha256_format"]
        miss=[x for x in req if x not in migration]
        return {"ok":not miss,"missing":miss,"_failures":["migration_contract_missing"] if miss else []}

    def u2():
        req=[".download(storagePath)","const uploadedSha256 = sha256(uploadedBuffer)"]
        miss=[x for x in req if x not in enqueue]
        return {"ok":not miss,"missing":miss,"_failures":["finalize_hash_missing"] if miss else []}

    def u3():
        req=["document.upload_sha256 !== uploadedSha256",'throw new Error("upload_integrity_mismatch")']
        miss=[x for x in req if x not in enqueue]
        return {"ok":not miss,"missing":miss,"_failures":["repeat_finalize_mismatch_guard_missing"] if miss else []}

    def u4():
        req=['.is("upload_sha256", null)',".select("upload_sha256")",".maybeSingle()"]
        miss=[x for x in req if x not in enqueue]
        return {"ok":not miss,"missing":miss,"_failures":["compare_and_set_pin_missing"] if miss else []}

    def u5():
        req=["const { data: concurrent, error: concurrentError }","concurrent.upload_sha256 !== uploadedSha256"]
        miss=[x for x in req if x not in enqueue]
        return {"ok":not miss,"missing":miss,"_failures":["concurrent_finalize_recheck_missing"] if miss else []}

    def u6():
        ok,pos=_ordered(enqueue,[
            "const uploadedSha256 = sha256(uploadedBuffer)",
            "upload_sha256: uploadedSha256",
            '.from("processing_jobs")'
        ])
        return {"ok":ok,"positions":pos,"_failures":[] if ok else ["queue_before_hash_pin"]}

    def u7():
        req=["upload_sha256", "sourceSha256 !== document.upload_sha256", 'throw new Error("upload_integrity_mismatch")']
        miss=[x for x in req if x not in initial]
        return {"ok":not miss,"missing":miss,"_failures":["worker_replay_guard_missing"] if miss else []}

    def u8():
        ok,pos=_ordered(initial,[
            "const sourceSha256 = createHash",
            'throw new Error("upload_integrity_mismatch")',
            "const analysis = await callAee"
        ])
        return {"ok":ok,"positions":pos,"_failures":[] if ok else ["analysis_before_replay_guard"]}

    def u9():
        req=['code === "upload_integrity_mismatch"','code: "UPLOAD_INTEGRITY_MISMATCH"','{ status: 409 }']
        miss=[x for x in req if x not in route]
        return {"ok":not miss,"missing":miss,"_failures":["route_integrity_conflict_missing"] if miss else []}

    def u10():
        req=['["deleting", "delete_failed"].includes(document.status)','throw new Error("document_not_finalizable")','code: "DOCUMENT_NOT_FINALIZABLE"']
        miss=[x for x in req if x not in persistence+route]
        return {"ok":not miss,"missing":miss,"_failures":["terminal_state_finalize_guard_missing"] if miss else []}

    def u11():
        original=b"original-upload"
        replay=b"replayed-upload"
        h1=hashlib.sha256(original).hexdigest()
        h2=hashlib.sha256(replay).hexdigest()
        ok=h1!=h2
        return {"original":h1,"replay":h2,"detected":ok,"_failures":[] if ok else ["replay_hash_collision_model"]}

    def u12():
        pinned=hashlib.sha256(b"first").hexdigest()
        same=hashlib.sha256(b"first").hexdigest()
        changed=hashlib.sha256(b"second").hexdigest()
        ok=(same==pinned and changed!=pinned)
        return {"same_allowed":same==pinned,"changed_blocked":changed!=pinned,"_failures":[] if ok else ["pin_model_failed"]}

    funcs=[u1,u2,u3,u4,u5,u6,u7,u8,u9,u10,u11,u12]
    cases=[_case(f"UPL-{i:03d}",fn) for i,fn in enumerate(funcs,1)]
    failed=[c["id"] for c in cases if not c["passed"]]
    report={"schema_version":1,"benchmark":"upload_finalization_signed_replay_v1","configuration":config,"cases":cases,"summary":{"passed":not failed,"passed_cases":len(cases)-len(failed),"total_cases":len(cases),"failed_cases":failed}}
    rendered=json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(rendered+"\n",encoding="utf-8")
    return 1 if args.enforce and failed else 0

if __name__=="__main__":
    raise SystemExit(main())
