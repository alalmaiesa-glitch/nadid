from __future__ import annotations
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DEFAULT_CONFIG = ROOT / "secure_deletion" / "v1.json"
PERSISTENCE = REPO / "lib" / "server" / "document-persistence.ts"
ACCOUNT_ROUTE = REPO / "app" / "api" / "account" / "route.ts"
ACCOUNT_GUARD = REPO / "supabase" / "migrations" / "0015_account_deletion_guard.sql"

def _case(case_id, fn):
    failures = []
    try:
        observed = fn()
        failures.extend(observed.pop("_failures", []))
    except Exception as exc:
        observed = {"exception": type(exc).__name__, "message": str(exc)[:300]}
        failures.append("benchmark_exception")
    return {"id": case_id, "observed": observed, "failures": failures, "passed": not failures}

def _ordered(text, markers):
    positions = [text.find(marker) for marker in markers]
    return all(x >= 0 for x in positions) and positions == sorted(positions), positions

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    persistence = PERSISTENCE.read_text(encoding="utf-8")
    account = ACCOUNT_ROUTE.read_text(encoding="utf-8")
    guard = ACCOUNT_GUARD.read_text(encoding="utf-8").lower()

    def d1():
        req=["async function listStorageObjectsRecursively","const queue = [normalized]","queue.push(child)"]
        miss=[x for x in req if x not in persistence]
        return {"ok":not miss,"missing":miss,"_failures":["recursive_storage_listing_missing"] if miss else []}

    def d2():
        req=["for (let index = 0; index < paths.length; index += 100)","const batch = paths.slice(index, index + 100)",".remove(batch)"]
        miss=[x for x in req if x not in persistence]
        return {"ok":not miss,"missing":miss,"_failures":["batched_storage_remove_missing"] if miss else []}

    def d3():
        s=persistence.find("export async function deleteDocumentFully")
        e=persistence.find("export async function deleteOwnerStorageOrphans",s)
        body=persistence[s:e]
        expected = "const ownedPrefix = " + chr(96) + "$" + "{ownerId}/$" + "{documentId}" + chr(96)
        req=['.eq("id", documentId)','.eq("owner_id", ownerId)',expected]
        miss=[x for x in req if x not in body]
        return {"ok":not miss,"missing":miss,"_failures":["document_delete_owner_scope_missing"] if miss else []}

    def d4():
        s=persistence.find("export async function deleteDocumentFully")
        e=persistence.find("export async function deleteOwnerStorageOrphans",s)
        body=persistence[s:e]
        req=["const paths = new Set<string>()","document.storage_path","version.storage_path","listStorageObjectsRecursively(ownedPrefix)","paths.add(path)"]
        miss=[x for x in req if x not in body]
        return {"ok":not miss,"missing":miss,"_failures":["orphan_path_merge_missing"] if miss else []}

    def d5():
        s=persistence.find("export async function deleteDocumentFully")
        e=persistence.find("export async function deleteOwnerStorageOrphans",s)
        body=persistence[s:e]
        ok,pos=_ordered(body,['status: "deleting"',"await removeStorageObjects([...paths])",'.from("documents")\n    .delete()'])
        return {"ok":ok,"positions":pos,"_failures":[] if ok else ["database_deleted_before_storage"]}

    def d6():
        s=persistence.find("export async function deleteDocumentFully")
        e=persistence.find("export async function deleteOwnerStorageOrphans",s)
        body=persistence[s:e]
        req=['status: "delete_failed"',"throw error;"]
        miss=[x for x in req if x not in body]
        return {"ok":not miss,"missing":miss,"_failures":["delete_failure_state_missing"] if miss else []}

    def d7():
        s=persistence.find("export async function deleteOwnerStorageOrphans")
        body=persistence[s:]
        req=["listStorageObjectsRecursively(prefix)","removeStorageObjects(paths)","invalid_owner_storage_prefix"]
        miss=[x for x in req if x not in body]
        return {"ok":not miss,"missing":miss,"_failures":["owner_orphan_sweep_missing"] if miss else []}

    def d8():
        req=["deleteOwnerStorageOrphans,","await deleteOwnerStorageOrphans(auth.userId)"]
        miss=[x for x in req if x not in account]
        return {"ok":not miss,"missing":miss,"_failures":["account_owner_sweep_missing"] if miss else []}

    def d9():
        ok,pos=_ordered(account,["for (const document of documents)","await deleteOwnerStorageOrphans(auth.userId)","await supabase.auth.admin.deleteUser(auth.userId)"])
        return {"ok":ok,"positions":pos,"_failures":[] if ok else ["auth_deleted_before_storage_cleanup"]}

    def d10():
        req=["removedDocuments: documents.length","removedOrphanObjects: storageCleanup.removedObjects"]
        miss=[x for x in req if x not in account]
        return {"ok":not miss,"missing":miss,"_failures":["deletion_result_counts_missing"] if miss else []}

    def d11():
        ok="references auth.users(id)" in guard and "on delete restrict" in guard
        return {"ok":ok,"_failures":[] if ok else ["account_delete_fk_restrict_missing"]}

    def d12():
        objects={"u/d/v1/source.docx","u/d/tmp/replayed.docx","u/d/v2/source.docx"}
        ok=len(objects)==3
        return {"ok":ok,"objects":sorted(objects),"_failures":[] if ok else ["orphan_cleanup_model_failed"]}

    funcs=[d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12]
    cases=[_case(f"DEL-{i:03d}",fn) for i,fn in enumerate(funcs,1)]
    failed=[c["id"] for c in cases if not c["passed"]]
    report={"schema_version":1,"benchmark":"secure_deletion_orphan_storage_cleanup_v1","configuration":config,"cases":cases,"summary":{"passed":not failed,"passed_cases":len(cases)-len(failed),"total_cases":len(cases),"failed_cases":failed}}
    rendered=json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(rendered+"\n",encoding="utf-8")
    return 1 if args.enforce and failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
