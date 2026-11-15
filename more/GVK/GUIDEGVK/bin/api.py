#!/usr/bin/env python3
"""GVK api: атомарные операции с содержимым репозитория по правилам протокола.
Повторы с экспоненциальной задержкой и джиттером (R2), обратное чтение (C12.5),
маскирование токена. Без внешних зависимостей.

  python3 bin/api.py list   --repo O/R --path GVK/claims
  python3 bin/api.py get    --repo O/R --path GVK/STATE.md [--ref main]
  python3 bin/api.py claim  --repo O/R --path GVK/claims/007.md --file /tmp/c.md --message "claim 007"
  python3 bin/api.py put    --repo O/R --path GVK/STATE.md --file /tmp/s.md --message "state"
  python3 bin/api.py delete --repo O/R --path GVK/claims/007.md
  python3 bin/api.py event  --repo O/R --file /tmp/event.json

Коды возврата: 0 успех, 1 отказ, 2 ошибка, 3 занято (422/409 при атомарном создании).
Токен берётся из /opt/.t и никогда не печатается.
"""
import argparse, base64, json, os, random, sys, time, urllib.error, urllib.request

API = "https://api.github.com"
TOKEN_FILE = "/opt/.t"


def token():
    t = os.environ.get("T") or (open(TOKEN_FILE).read().strip() if os.path.exists(TOKEN_FILE) else "")
    if not t:
        print("API ERROR: токен не найден"); sys.exit(2)
    return t


def call(method, url, body=None, tries=5):
    """Один вызов с повторами по R2. Возвращает (status, json|text, headers)."""
    t = token()
    pause = 1.0
    for k in range(1, tries + 1):
        req = urllib.request.Request(url, method=method)
        req.add_header("Authorization", "Bearer " + t)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "gvk-protocol/5.0")
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, data, timeout=45) as r:
                raw = r.read().decode("utf-8", "replace")
                try:
                    return r.status, json.loads(raw), dict(r.headers)
                except json.JSONDecodeError:
                    return r.status, raw, dict(r.headers)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            if e.code in (429, 500, 502, 503, 504) and k < tries:
                ra = e.headers.get("Retry-After")
                wait = float(ra) if ra and ra.isdigit() else pause * (1 + random.uniform(-0.3, 0.3))
                print(f"API RETRY {k}/{tries}: {e.code}, пауза {min(wait,60):.1f} c")
                time.sleep(min(wait, 60)); pause *= 2; continue
            try:
                return e.code, json.loads(raw), dict(e.headers)
            except json.JSONDecodeError:
                return e.code, raw, dict(e.headers)
        except Exception as e:
            if k < tries:
                wait = pause * (1 + random.uniform(-0.3, 0.3))
                print(f"API RETRY {k}/{tries}: {type(e).__name__}, пауза {min(wait,60):.1f} c")
                time.sleep(min(wait, 60)); pause *= 2; continue
            print(f"API ERROR: {type(e).__name__} после {tries} попыток"); sys.exit(2)
    print("API ERROR: попытки исчерпаны"); sys.exit(2)


def contents(repo, path, ref=None):
    return f"{API}/repos/{repo}/contents/{path}" + (f"?ref={ref}" if ref else "")


def sha_of(repo, path):
    st, body, _ = call("GET", contents(repo, path))
    if st == 200 and isinstance(body, dict):
        return body.get("sha")
    return None


def readback(repo, path, expect=None):
    st, body, _ = call("GET", contents(repo, path))
    if st != 200:
        print(f"READBACK FAIL: {path} не читается ({st})"); return False
    if expect is not None and isinstance(body, dict):
        got = base64.b64decode(body.get("content", "")).decode("utf-8", "replace")
        if got.strip() != expect.strip():
            print(f"READBACK FAIL: {path} содержимое не совпало"); return False
    print(f"READBACK OK: {path}"); return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "get", "claim", "put", "delete", "event"])
    ap.add_argument("--repo", required=True); ap.add_argument("--path")
    ap.add_argument("--file"); ap.add_argument("--message", default="gvk")
    ap.add_argument("--ref"); ap.add_argument("--branch", default="main")
    a = ap.parse_args()
    if not a.path and a.cmd != "event":
        print("API ERROR: нужен --path"); return 2

    if a.cmd == "list":
        st, body, _ = call("GET", contents(a.repo, a.path, a.ref))
        if st != 200:
            print(f"API FAIL {st}: каталог не читается"); return 1
        for it in body:
            print(it["name"])
        return 0

    if a.cmd == "get":
        st, body, _ = call("GET", contents(a.repo, a.path, a.ref))
        if st == 404:
            print("NOT FOUND"); return 1
        if st != 200:
            print(f"API FAIL {st}"); return 1
        print(base64.b64decode(body["content"]).decode("utf-8", "replace"))
        return 0

    if a.cmd in ("claim", "put", "event"):
        if not a.file or not os.path.exists(a.file):
            print("API ERROR: нужен существующий --file"); return 2
        text = open(a.file, encoding="utf-8").read()
        path = a.path
        if a.cmd == "event":
            if not text.strip().startswith("{"):
                print("API ERROR: событие должно быть JSON"); return 2
            day = time.strftime("%Y%m%d", time.gmtime())
            path = a.path or f"REPORT/events/{day}.jsonl"
            old = ""
            sh = sha_of(a.repo, path)
            if sh:
                st, body, _ = call("GET", contents(a.repo, path))
                old = base64.b64decode(body["content"]).decode("utf-8", "replace")
            text = old + text.rstrip() + "\n"
        payload = {"message": a.message, "branch": a.branch,
                   "content": base64.b64encode(text.encode()).decode()}
        if a.cmd != "claim":
            sh = sha_of(a.repo, path)
            if sh:
                payload["sha"] = sh
        st, body, _ = call("PUT", contents(a.repo, path), payload)
        if st in (422, 409):
            if a.cmd == "claim":
                print(f"BUSY {st}: занято другим агентом"); return 3
            sh = sha_of(a.repo, path)                      # одна повторная попытка по R7
            if sh:
                payload["sha"] = sh
                st, body, _ = call("PUT", contents(a.repo, path), payload)
        if st not in (200, 201):
            msg = body.get("message") if isinstance(body, dict) else str(body)[:120]
            print(f"API FAIL {st}: {msg}"); return 1
        print(f"WROTE {path} ({st})")
        return 0 if readback(a.repo, path, text) else 1

    if a.cmd == "delete":
        sh = sha_of(a.repo, a.path)
        if not sh:
            print("ALREADY GONE"); return 0
        st, body, _ = call("DELETE", contents(a.repo, a.path),
                           {"message": a.message, "sha": sh, "branch": a.branch})
        if st in (404, 409):
            print("ALREADY GONE"); return 0
        if st != 200:
            print(f"API FAIL {st}"); return 1
        st2, _, _ = call("GET", contents(a.repo, a.path))
        print("DELETED" if st2 == 404 else "DELETE FAIL: файл всё ещё читается")
        return 0 if st2 == 404 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"API ERROR: {type(e).__name__}: {e}"); sys.exit(2)
