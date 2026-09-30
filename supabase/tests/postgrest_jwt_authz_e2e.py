from __future__ import annotations

import base64
import hashlib
import hmac
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request


DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
U1 = "12000000-0000-0000-0000-000000000001"
U2 = "12000000-0000-0000-0000-000000000002"
D1 = "22000000-0000-0000-0000-000000000001"
D2 = "22000000-0000-0000-0000-000000000002"
D3 = "22000000-0000-0000-0000-000000000003"


def _run(*args: str, input_text: str | None = None) -> str:
    completed = subprocess.run(
        list(args),
        input=input_text,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout


def _psql(sql: str) -> str:
    return _run(
        "psql",
        DB_URL,
        "-v",
        "ON_ERROR_STOP=1",
        "-At",
        "-c",
        sql,
    ).strip()


def _local_env() -> dict[str, str]:
    raw = _run("supabase", "status", "-o", "env")
    output: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        output[key.strip()] = value.strip().strip('"').strip("'")
    return output


def _first(env: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = env.get(name)
        if value:
            return value
    return None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _jwt(secret: str, sub: str, email: str) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "aud": "authenticated",
        "exp": now + 3600,
        "iat": now,
        "sub": sub,
        "email": email,
        "role": "authenticated",
    }
    head = _b64url(
        json.dumps(header, separators=(",", ":")).encode("utf-8")
    )
    body = _b64url(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{head}.{body}".encode("ascii")
    signature = hmac.new(
        secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{head}.{body}.{_b64url(signature)}"


def _request(
    method: str,
    url: str,
    *,
    apikey: str,
    token: str | None = None,
    body: dict | None = None,
    prefer: str | None = None,
) -> tuple[int, object]:
    headers = {
        "apikey": apikey,
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if prefer:
        headers["Prefer"] = prefer

    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    env = _local_env()
    api_url = _first(
        env,
        "API_URL",
        "SUPABASE_URL",
        "PROJECT_URL",
    ) or "http://127.0.0.1:54321"
    public_key = _first(
        env,
        "PUBLISHABLE_KEY",
        "ANON_KEY",
        "SUPABASE_ANON_KEY",
    )
    jwt_secret = _first(
        env,
        "JWT_SECRET",
        "SUPABASE_JWT_SECRET",
    )
    secret_key = _first(
        env,
        "SECRET_KEY",
        "SUPABASE_SECRET_KEY",
    )
    service_role_key = _first(
        env,
        "SERVICE_ROLE_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
    )

    missing = []
    if not public_key:
        missing.append("public_key")
    if not jwt_secret:
        missing.append("jwt_secret")
    if missing:
        raise RuntimeError(
            "Missing local Supabase credentials: "
            + ", ".join(missing)
            + "; available keys="
            + ",".join(sorted(env))
        )

    _psql(
        f"""
        insert into auth.users (id, email, raw_user_meta_data)
        values
          ('{U1}', 'api-u1@nadid.local', '{{}}'::jsonb),
          ('{U2}', 'api-u2@nadid.local', '{{}}'::jsonb);

        insert into public.documents (
          id, owner_id, title, filename, status
        ) values
          ('{D1}', '{U1}', 'API User 1', 'api-u1.docx', 'ready'),
          ('{D2}', '{U2}', 'API User 2', 'api-u2.docx', 'ready');
        """
    )

    token1 = _jwt(jwt_secret, U1, "api-u1@nadid.local")
    rest = api_url.rstrip("/") + "/rest/v1"

    try:
        # API-001: authenticated user sees only own document.
        status, body = _request(
            "GET",
            rest + "/documents?select=id,title&order=id",
            apikey=public_key,
            token=token1,
        )
        _expect(status == 200, f"API-001 status={status} body={body}")
        _expect(
            isinstance(body, list)
            and [row["id"] for row in body] == [D1],
            f"API-001 ownership leak body={body}",
        )

        # API-002: explicit cross-user lookup remains invisible.
        status, body = _request(
            "GET",
            rest + "/documents?id=eq." + D2 + "&select=id,title",
            apikey=public_key,
            token=token1,
        )
        _expect(status == 200, f"API-002 status={status} body={body}")
        _expect(body == [], f"API-002 leaked cross-user row: {body}")

        # API-003: cross-user PATCH is a no-op.
        status, body = _request(
            "PATCH",
            rest + "/documents?id=eq." + D2,
            apikey=public_key,
            token=token1,
            body={"title": "CROSS USER API WRITE"},
            prefer="return=representation",
        )
        _expect(status == 200, f"API-003 status={status} body={body}")
        _expect(body == [], f"API-003 cross-user write returned rows: {body}")
        title2 = _psql(
            f"select title from public.documents where id = '{D2}';"
        )
        _expect(title2 == "API User 2", f"API-003 changed user2 title={title2}")

        # API-004: own PATCH succeeds.
        status, body = _request(
            "PATCH",
            rest + "/documents?id=eq." + D1,
            apikey=public_key,
            token=token1,
            body={"title": "API User 1 Updated"},
            prefer="return=representation",
        )
        _expect(status == 200, f"API-004 status={status} body={body}")
        _expect(
            isinstance(body, list)
            and len(body) == 1
            and body[0]["id"] == D1,
            f"API-004 own update missing: {body}",
        )

        # API-005: own document INSERT succeeds.
        status, body = _request(
            "POST",
            rest + "/documents",
            apikey=public_key,
            token=token1,
            body={
                "id": D3,
                "owner_id": U1,
                "title": "API User 1 New",
                "filename": "api-u1-new.docx",
                "status": "ready",
            },
            prefer="return=representation",
        )
        _expect(status == 201, f"API-005 status={status} body={body}")
        _expect(
            isinstance(body, list)
            and len(body) == 1
            and body[0]["id"] == D3,
            f"API-005 own insert missing: {body}",
        )

        # API-006: User 1 cannot create a document owned by User 2.
        status, body = _request(
            "POST",
            rest + "/documents",
            apikey=public_key,
            token=token1,
            body={
                "owner_id": U2,
                "title": "Forbidden",
                "filename": "forbidden.docx",
                "status": "ready",
            },
            prefer="return=representation",
        )
        _expect(
            status in {401, 403},
            f"API-006 expected authz failure, got {status} body={body}",
        )

        # API-007: no DELETE policy => own delete cannot remove the row.
        status, body = _request(
            "DELETE",
            rest + "/documents?id=eq." + D1,
            apikey=public_key,
            token=token1,
            prefer="return=representation",
        )
        _expect(status == 200, f"API-007 status={status} body={body}")
        _expect(body == [], f"API-007 unexpected delete rows={body}")
        survives = _psql(
            f"select count(*) from public.documents where id = '{D1}';"
        )
        _expect(survives == "1", "API-007 own document was deleted")

        # API-008: anonymous browser context sees no user documents.
        status, body = _request(
            "GET",
            rest + "/documents?select=id",
            apikey=public_key,
        )
        _expect(status == 200, f"API-008 status={status} body={body}")
        _expect(body == [], f"API-008 anonymous leak: {body}")

        # API-009: browser user cannot write Worker-owned child table.
        status, body = _request(
            "POST",
            rest + "/document_versions",
            apikey=public_key,
            token=token1,
            body={
                "document_id": D1,
                "version_no": 99,
                "is_source": False,
            },
            prefer="return=representation",
        )
        _expect(
            status in {401, 403},
            f"API-009 expected child-write denial, got {status} body={body}",
        )

        # API-010: server credential retains administrative visibility.
        if secret_key:
            admin_apikey = secret_key
            admin_token = None
        elif service_role_key:
            admin_apikey = service_role_key
            admin_token = service_role_key
        else:
            raise RuntimeError(
                "No local server credential; available keys="
                + ",".join(sorted(env))
            )

        status, body = _request(
            "GET",
            rest + "/documents?select=id&order=id",
            apikey=admin_apikey,
            token=admin_token,
        )
        _expect(status == 200, f"API-010 status={status} body={body}")
        ids = {row["id"] for row in body} if isinstance(body, list) else set()
        _expect(
            {D1, D2, D3}.issubset(ids),
            f"API-010 server access incomplete ids={sorted(ids)}",
        )

        print("PostgREST/JWT End-to-End Authorization V1: 10/10 PASS")
    finally:
        _psql(
            f"""
            delete from public.documents
            where id in ('{D1}', '{D2}', '{D3}');
            delete from auth.users
            where id in ('{U1}', '{U2}');
            """
        )


if __name__ == "__main__":
    main()
