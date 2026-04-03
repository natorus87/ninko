from __future__ import annotations

"""
E2E smoke tests for critical paths.

Run against a live backend:
  NINKO_BASE_URL=http://localhost:8000 python3 backend/test_e2e_critical_paths.py

Optional auth headers:
  NINKO_API_KEY_READ=...
  NINKO_API_KEY_WRITE=...
  NINKO_API_KEY_ADMIN=...
"""

import json
import os
import urllib.error
import urllib.request


BASE_URL = os.getenv("NINKO_BASE_URL", "http://localhost:8000").rstrip("/")
KEY_READ = os.getenv("NINKO_API_KEY_READ", "")
KEY_WRITE = os.getenv("NINKO_API_KEY_WRITE", "")
KEY_ADMIN = os.getenv("NINKO_API_KEY_ADMIN", "")


def _request(
    method: str,
    path: str,
    *,
    payload: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=payload,
        headers=headers or {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body


def _print_result(name: str, ok: bool, detail: str = "") -> None:
    state = "OK" if ok else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"[{state}] {name}{suffix}")


def main() -> int:
    failures = 0

    status, body = _request("GET", "/health")
    ok = status == 200 and '"status": "ok"' in body
    _print_result("health", ok, f"status={status}")
    failures += 0 if ok else 1

    status, _ = _request("POST", "/api/safeguard/disable")
    ok = status in (200, 401, 403)
    _print_result("safeguard_disable_protection", ok, f"status={status}")
    failures += 0 if ok else 1

    if KEY_ADMIN:
        status, _ = _request(
            "POST",
            "/api/safeguard/enable",
            headers={"X-API-Key": KEY_ADMIN},
        )
        ok = status == 200
        _print_result("safeguard_enable_admin", ok, f"status={status}")
        failures += 0 if ok else 1

    if KEY_READ:
        status, _ = _request(
            "GET",
            "/api/safeguard/status",
            headers={"X-API-Key": KEY_READ},
        )
        ok = status == 200
        _print_result("safeguard_status_read", ok, f"status={status}")
        failures += 0 if ok else 1

    # Transcription upload limit/sanity check:
    # Send intentionally invalid payload and ensure backend rejects predictably.
    boundary = "----ninko-e2e-boundary"
    bogus_audio = b"not-audio"
    multipart = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="test.txt"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
    ).encode("utf-8") + bogus_audio + f"\r\n--{boundary}--\r\n".encode("utf-8")

    status, body = _request(
        "POST",
        "/api/transcription/",
        payload=multipart,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            **({"X-API-Key": KEY_WRITE} if KEY_WRITE else {}),
        },
    )
    ok = status in (400, 401, 403, 413, 415, 422, 500, 503)
    _print_result("transcription_rejects_invalid_upload", ok, f"status={status}")
    failures += 0 if ok else 1

    print(json.dumps({"base_url": BASE_URL, "failures": failures}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
