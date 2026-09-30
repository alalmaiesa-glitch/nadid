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
BUCKET = "nadid-documents"
U1 = "13000000-0000-0000-0000-000000000001"
U2 = "13000000-0000-0000-0000-000000000002"
D1 = "23000000-0000-0000-0000-000000000001"
D2 = "23000000-0000-0000-0000-000000000002"
P1 = f"{U1}/{D1}/v1/source.docx"
P2 = f"{U2}/{D2}/v1/source.docx"
DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document"
)


def _run(*args: str) -> str:
    completed = subprocess.run(
        list(args),
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


def _env() -> dict[str, str]:
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
    signing = f"{head}.{body}".encode("ascii")
    signature = hmac.new(
        secret.encode("utf-8"),
        signing,
        hashlib.sha256,
    ).digest()
    return f"{head}.{body}.{_b64url(signature)}"


def _request(
    method: str,
    url: str,
    *,
    apikey: str | None = None,
    token: str | None = None,
    body: bytes | dict | None = None,
    content_type: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    headers: dict[str, str] = {}
    if apikey:
        headers["apikey"] = apikey
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)

    data: bytes | None
    if isinstance(body, dict):
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = content_type or "application/json"
    else:
        data = body
        if body is not None and content_type:
            headers["Content-Type"] = content_type

    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


def _json(raw: bytes):
    return json.loads(raw.decode("utf-8")) if raw else None


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _object_url(api_url: str, path: str) -> str:
    quoted = urllib.parse.quote(path, safe="/")
    return f"{api_url.rstrip('/')}/storage/v1/object/{BUCKET}/{quoted}"


def _signed_url(api_url: str, raw: str) -> str:
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if raw.startswith("/storage/v1/"):
        return api_url.rstrip("/") + raw
    if raw.startswith("/object/"):
        return api_url.rstrip("/") + "/storage/v1" + raw
    return api_url.rstrip("/") + "/storage/v1/" + raw.lstrip("/")


def main() -> None:
    env = _env()
    api_url = _first(env, "API_URL", "SUPABASE_URL", "PROJECT_URL") or (
        "http://127.0.0.1:54321"
    )
    public_key = _first(
        env,
        "PUBLISHABLE_KEY",
        "ANON_KEY",
        "SUPABASE_ANON_KEY",
    )
    jwt_secret = _first(env, "JWT_SECRET", "SUPABASE_JWT_SECRET")
    secret_key = _first(env, "SECRET_KEY", "SUPABASE_SECRET_KEY")
    service_role_key = _first(
        env,
        "SERVICE_ROLE_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
    )

    if not public_key or not jwt_secret:
        raise RuntimeError("Local Supabase public key/JWT secret missing.")

    if secret_key:
        admin_apikey = secret_key
        admin_token = None
    elif service_role_key:
        admin_apikey = service_role_key
        admin_token = service_role_key
    else:
        raise RuntimeError("Local Supabase server credential missing.")

    _psql(
        f"""
        insert into auth.users (id, email, raw_user_meta_data)
        values
          ('{U1}', 'storage-u1@nadid.local', '{{}}'::jsonb),
          ('{U2}', 'storage-u2@nadid.local', '{{}}'::jsonb);

        insert into public.documents (
          id, owner_id, title, filename, storage_path, status
        ) values
          ('{D1}', '{U1}', 'Storage User 1', 'u1.docx', '{P1}', 'uploading'),
          ('{D2}', '{U2}', 'Storage User 2', 'u2.docx', '{P2}', 'uploading');
        """
    )

    token1 = _jwt(jwt_secret, U1, "storage-u1@nadid.local")
    token2 = _jwt(jwt_secret, U2, "storage-u2@nadid.local")
    payload1 = b"nadid-storage-user-1"
    payload2 = b"nadid-storage-user-2"

    try:
        # STO-001/002: server credential may create private objects.
        for path, payload in ((P1, payload1), (P2, payload2)):
            status, raw, _ = _request(
                "POST",
                _object_url(api_url, path),
                apikey=admin_apikey,
                token=admin_token,
                body=payload,
                content_type=DOCX_MIME,
                extra_headers={"x-upsert": "true"},
            )
            _expect(
                status in {200, 201},
                f"server upload failed path={path} status={status} body={raw!r}",
            )

        # STO-003: anonymous direct object read is denied.
        status, _, _ = _request(
            "GET",
            _object_url(api_url, P1),
            apikey=public_key,
        )
        _expect(
            status in {400, 401, 403, 404},
            f"anon direct read unexpectedly allowed status={status}",
        )

        # STO-004: authenticated user cannot directly read own object.
        status, _, _ = _request(
            "GET",
            _object_url(api_url, P1),
            apikey=public_key,
            token=token1,
        )
        _expect(
            status in {400, 401, 403, 404},
            f"authenticated direct read unexpectedly allowed status={status}",
        )

        # STO-005: authenticated user cannot directly read another user's object.
        status, _, _ = _request(
            "GET",
            _object_url(api_url, P2),
            apikey=public_key,
            token=token1,
        )
        _expect(
            status in {400, 401, 403, 404},
            f"cross-user direct read unexpectedly allowed status={status}",
        )

        # STO-006: authenticated user cannot overwrite another user's object.
        status, _, _ = _request(
            "POST",
            _object_url(api_url, P2),
            apikey=public_key,
            token=token1,
            body=b"cross-user-overwrite",
            content_type=DOCX_MIME,
            extra_headers={"x-upsert": "true"},
        )
        _expect(
            status in {400, 401, 403, 404},
            f"cross-user overwrite unexpectedly allowed status={status}",
        )

        # STO-007: server direct read remains available to trusted backend/worker.
        status, raw, _ = _request(
            "GET",
            _object_url(api_url, P1),
            apikey=admin_apikey,
            token=admin_token,
        )
        _expect(status == 200, f"server read failed status={status} body={raw!r}")
        _expect(raw == payload1, f"server read payload mismatch: {raw!r}")

        # STO-008: server can mint a short-lived signed download for one object.
        sign_endpoint = (
            f"{api_url.rstrip('/')}/storage/v1/object/sign/"
            f"{BUCKET}/{urllib.parse.quote(P1, safe='/')}"
        )
        status, raw, _ = _request(
            "POST",
            sign_endpoint,
            apikey=admin_apikey,
            token=admin_token,
            body={"expiresIn": 60},
        )
        _expect(status == 200, f"sign failed status={status} body={raw!r}")
        signed_body = _json(raw)
        signed_raw = (
            signed_body.get("signedURL")
            or signed_body.get("signedUrl")
            or signed_body.get("signed_url")
        )
        _expect(bool(signed_raw), f"signed URL missing response={signed_body}")
        signed = _signed_url(api_url, signed_raw)

        # STO-009: signed URL works without a browser session.
        status, raw, _ = _request("GET", signed)
        _expect(status == 200, f"signed read failed status={status} body={raw!r}")
        _expect(raw == payload1, "signed read returned wrong object bytes")

        # STO-010: changing object path while keeping signature must fail.
        tampered = signed.replace(
            urllib.parse.quote(P1, safe="/"),
            urllib.parse.quote(P2, safe="/"),
        ).replace(P1, P2)
        _expect(tampered != signed, "signed URL path could not be tampered for test")
        status, raw, _ = _request("GET", tampered)
        _expect(
            status in {400, 401, 403, 404},
            f"tampered signed URL unexpectedly succeeded status={status} body={raw!r}",
        )

        # STO-011: second user's direct browser token also stays denied.
        status, _, _ = _request(
            "GET",
            _object_url(api_url, P2),
            apikey=public_key,
            token=token2,
        )
        _expect(
            status in {400, 401, 403, 404},
            f"user2 direct read unexpectedly allowed status={status}",
        )

        # STO-012: private bucket never exposes public object endpoint.
        public_url = (
            f"{api_url.rstrip('/')}/storage/v1/object/public/"
            f"{BUCKET}/{urllib.parse.quote(P1, safe='/')}"
        )
        status, _, _ = _request("GET", public_url)
        _expect(
            status in {400, 401, 403, 404},
            f"private bucket public endpoint leaked object status={status}",
        )

        print("Storage Object Isolation & Signed Access V1: 12/12 PASS")
    finally:
        for path in (P1, P2):
            _request(
                "DELETE",
                _object_url(api_url, path),
                apikey=admin_apikey,
                token=admin_token,
            )
        _psql(
            f"""
            delete from public.documents
            where id in ('{D1}', '{D2}');
            delete from auth.users
            where id in ('{U1}', '{U2}');
            """
        )


if __name__ == "__main__":
    main()
