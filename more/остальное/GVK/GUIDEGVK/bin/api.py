#!/usr/bin/env python3
"""GVK api v2: атомарные операции с репозиторием по правилам протокола.

Отличия v2 (все — исправления найденных дефектов, см. CHANGELOG v5.2):
  * журнал событий шардирован по сессиям: чужие строки не теряются (S5, R9);
  * дописывание в общий файл — с перечитыванием содержимого, а не только sha;
  * один GET даёт и sha, и содержимое (было три);
  * guard и валидатор вызываются до записи, а не «по совести» (S3, C12.4);
  * `get` читает каталоги и файлы >1 МБ, а не падает и не отдаёт пустоту;
  * 422 «уже существует» отличается от 422 «неверный запрос»;
  * время и дата — из заголовка Date GitHub (C4), не из часов песочницы;
  * `slice` — минимальный срез состояния за 1–3 вызова (C6, E1).

  api.py now
  api.py list   --repo O/R --path GVK/claims
  api.py get    --repo O/R --path GVK/STATE.md [--ref main]
  api.py slice  --repo O/R
  api.py claim  --repo O/R --role DEV --path GVK/claims/007.md --file /tmp/c.md
  api.py put    --repo O/R --role DEV --path REPORT/frag/007.json --file /tmp/007.json --schema report
  api.py append --repo O/R --role TZFIX --path GVK/STAGES.md --file /tmp/line.md
  api.py event  --repo O/R --role DEV --owner gvk-qwen-7 --file /tmp/event.json
  api.py delete --repo O/R --role DEV --path GVK/claims/007.md
  api.py merge  --repo O/R --role CLOSER --number 12

Коды возврата: 0 успех, 1 отказ, 2 ошибка, 3 занято. Токен не печатается никогда.
"""
import argparse, base64, json, os, random, subprocess, sys, time, urllib.error, urllib.request

API = "https://api.github.com"
TOKEN_FILE = "/opt/.t"
HERE = os.path.dirname(os.path.abspath(__file__))
G = os.path.dirname(HERE)
GUARD = os.path.join(HERE, "guard.py")
VALIDATE = os.path.join(HERE, "validate.py")
SCHEMA_DIR = os.path.join(G, "schema")
TEMPLATE = os.path.join(G, "pep.template.json")


def token():
    t = os.environ.get("T") or (open(TOKEN_FILE).read().strip() if os.path.exists(TOKEN_FILE) else "")
    if not t:
        print("API ERROR: токен не найден"); sys.exit(2)
    return t


def call(method, url, body=None, tries=5, raw=False):
    """Один вызов с повторами по R2. Возвращает (status, json|text, headers)."""
    t = token()
    pause = 1.0
    for k in range(1, tries + 1):
        req = urllib.request.Request(url, method=method)
        req.add_header("Authorization", "Bearer " + t)
        req.add_header("Accept", "application/vnd.github.raw" if raw else "application/vnd.github+json")
        req.add_header("User-Agent", "gvk-protocol/5.2")
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, data, timeout=45) as r:
                text = r.read().decode("utf-8", "replace")
                hdr = dict(r.headers)
                if raw:
                    return r.status, text, hdr
                try:
                    return r.status, json.loads(text), hdr
                except json.JSONDecodeError:
                    return r.status, text, hdr
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            hdr = dict(e.headers)
            temporary = e.code in (429, 500, 502, 503, 504)
            if e.code == 403 and (hdr.get("Retry-After") or hdr.get("X-RateLimit-Remaining") == "0"):
                temporary = True                      # вторичный лимит GitHub — временный отказ
            if temporary and k < tries:
                ra = hdr.get("Retry-After")
                wait = float(ra) if ra and ra.isdigit() else pause * (1 + random.uniform(-0.3, 0.3))
                print(f"API RETRY {k}/{tries}: {e.code}, пауза {min(wait, 60):.1f} c")
                time.sleep(min(wait, 60)); pause *= 2; continue
            try:
                return e.code, json.loads(text), hdr
            except json.JSONDecodeError:
                return e.code, text, hdr
        except Exception as e:
            if k < tries:
                wait = pause * (1 + random.uniform(-0.3, 0.3))
                print(f"API RETRY {k}/{tries}: {type(e).__name__}, пауза {min(wait, 60):.1f} c")
                time.sleep(min(wait, 60)); pause *= 2; continue
            print(f"API ERROR: {type(e).__name__} после {tries} попыток"); sys.exit(2)
    print("API ERROR: попытки исчерпаны"); sys.exit(2)


def contents(repo, path, ref=None):
    return f"{API}/repos/{repo}/contents/{path}" + (f"?ref={ref}" if ref else "")


def gh_now():
    """Время GitHub в ISO-8601 UTC (C4). Часы песочницы источником не являются."""
    import email.utils, datetime
    st, _, hdr = call("HEAD", API + "/rate_limit")
    d = hdr.get("Date") or hdr.get("date") or ""
    try:
        dt = email.utils.parsedate_to_datetime(d).astimezone(datetime.timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), dt.strftime("%Y%m%d"), dt.strftime("%H%M%S")
    except Exception:
        print("API ERROR: заголовок Date не получен, время неизвестно"); sys.exit(2)


def fetch(repo, path, ref=None):
    """Один вызов: (status, sha, text). Большие файлы дочитываются raw-запросом."""
    st, body, _ = call("GET", contents(repo, path, ref))
    if st != 200 or not isinstance(body, dict):
        return st, None, None
    if body.get("encoding") == "base64" and body.get("content"):
        return st, body.get("sha"), base64.b64decode(body["content"]).decode("utf-8", "replace")
    st2, raw, _ = call("GET", contents(repo, path, ref), raw=True)   # >1 МБ: content пуст
    return st, body.get("sha"), raw if st2 == 200 else None


def readback(repo, path, expect=None, ref=None):
    st, _, got = fetch(repo, path, ref)
    if st != 200 or got is None:
        print(f"READBACK FAIL: {path} не читается ({st})"); return False
    if expect is not None and got.strip() != expect.strip():
        print(f"READBACK FAIL: {path} содержимое не совпало"); return False
    print(f"READBACK OK: {path}"); return True


def guard_check(a, path, file=None, intent="write", extra=()):
    """S3: проверка прав кодом до действия. Отказ guard — отказ записи."""
    if a.no_guard:
        print("GUARD SKIPPED: --no-guard (только бутстрап реестра или рычаг владельца)")
        return True
    if not a.role:
        print("API ERROR: для записи нужен --role (S3) или явный --no-guard"); return False
    pep = a.pep if os.path.exists(a.pep) else TEMPLATE
    if pep == TEMPLATE:
        print("GUARD: реестр проекта отсутствует, права взяты из шаблона протокола (бутстрап)")
    cmd = [sys.executable, GUARD, "--role", a.role, "--pep", pep, "--intent", intent]
    if path:
        cmd += ["--paths", path]
    if file:
        cmd += ["--content-file", file]
    if a.claim:
        cmd += ["--claim", a.claim]
    if a.branch and a.branch != "main":
        cmd += ["--branch", a.branch]
    else:
        cmd += ["--branch", a.branch or "main"]
    if a.owner_lever:
        cmd += ["--owner-lever"]
    cmd += list(extra)
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        print(f"GUARD DENY: действие не выполнять (код {r.returncode})")
        return False
    return True


def validate_check(a, file):
    if not a.schema:
        return True
    sch = a.schema if os.path.exists(a.schema) else os.path.join(SCHEMA_DIR, a.schema + ".schema.json")
    if not os.path.exists(sch):
        print(f"API ERROR: схема не найдена: {sch}"); return False
    r = subprocess.run([sys.executable, VALIDATE, "--schema", sch, "--file", file], capture_output=True, text=True)
    print(r.stdout.strip())
    return r.returncode == 0


def busy_or_bad(st, body):
    """422/409 при атомарном создании: занято или неверный запрос."""
    msg = (body.get("message", "") if isinstance(body, dict) else str(body)).lower()
    errors = json.dumps(body.get("errors", []), ensure_ascii=False).lower() if isinstance(body, dict) else ""
    if "already_exists" in errors or "already exists" in msg or st == 409:
        return 3
    if "sha" in errors and "wasn't supplied" in errors:
        return 3
    return 1


def put_payload(a, path, text, sha=None, message=None):
    payload = {"message": message or a.message, "branch": a.branch,
               "content": base64.b64encode(text.encode()).decode()}
    if sha:
        payload["sha"] = sha
    return payload


def do_write(a, path, text, atomic=False, schema=None, intent="write", message=None):
    if schema and not validate_check(a, a.file):
        print("API FAIL: контракт не сходится, запись запрещена (C12.4)"); return 1
    if not guard_check(a, path, a.file, intent):
        return 1
    sha = None
    if not atomic:
        st, sha, _ = fetch(a.repo, path, a.branch)
    payload = put_payload(a, path, text, sha, message)
    st, body, _ = call("PUT", contents(a.repo, path), payload)
    if st in (409, 422):
        code = busy_or_bad(st, body)
        if atomic:
            print(f"BUSY {st}: занято другим агентом" if code == 3 else f"API FAIL {st}: неверный запрос создания")
            return code
        st2, sha2, cur = fetch(a.repo, path, a.branch)      # одна повторная попытка (R7)
        if sha2:
            payload = put_payload(a, path, text, sha2, message)
            st, body, _ = call("PUT", contents(a.repo, path), payload)
    if st not in (200, 201):
        msg = body.get("message") if isinstance(body, dict) else str(body)[:120]
        print(f"API FAIL {st}: {msg}"); return 1
    print(f"WROTE {path} ({st})")
    return 0 if readback(a.repo, path, text, a.branch) else 1


def do_append(a, path, line, schema=None):
    """Дописывание в общий файл: при конфликте перечитывается СОДЕРЖИМОЕ, не только sha."""
    if schema and not validate_check(a, a.file):
        return 1
    if not guard_check(a, path, a.file, "update"):
        return 1
    for attempt in (1, 2, 3):
        st, sha, cur = fetch(a.repo, path, a.branch)
        base = cur or ""
        if line.strip() in base:
            print(f"APPEND SKIP: строка уже в {path}"); return 0
        text = base + ("" if not base or base.endswith("\n") else "\n") + line.rstrip() + "\n"
        payload = put_payload(a, path, text, sha)
        st, body, _ = call("PUT", contents(a.repo, path), payload)
        if st in (200, 201):
            st2, _, got = fetch(a.repo, path, a.branch)
            if got and line.strip() in got and all(l in got for l in base.splitlines() if l.strip()):
                print(f"APPENDED {path}: своё добавлено, чужое сохранено")
                return 0
            print("READBACK FAIL: после дописывания потеряны строки"); return 1
        if st not in (409, 422):
            msg = body.get("message") if isinstance(body, dict) else str(body)[:120]
            print(f"API FAIL {st}: {msg}"); return 1
        print(f"APPEND RETRY {attempt}: конфликт, перечитываю содержимое")
    print("API FAIL: три конфликта подряд, журнал не дописан"); return 1


def do_slice(a):
    """Минимальный срез C6 за 1–3 вызова: дерево + признаки плана."""
    st, tree, _ = call("GET", f"{API}/repos/{a.repo}/git/trees/{a.ref}?recursive=1")
    if st != 200 or not isinstance(tree, dict):
        print(f"API FAIL {st}: дерево не читается"); return 1
    paths = [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]
    def under(p):
        return sorted(x for x in paths if x.startswith(p))
    claims = under("GVK/claims/")
    fixes = under("GVK/fixes/")
    roles = under("GVK/roles/")
    frag = under("REPORT/frag/")
    findings = under("REPORT/finding/")
    reviews = under("REPORT/review/")
    tasks = [x for x in under("REPORT/test/") if "/T-" in x]
    results = [x for x in under("REPORT/test/") if "/R-" in x]
    tclaims = under("REPORT/test/claims/")
    out = {
        "repo": a.repo, "ref": a.ref, "truncated": bool(tree.get("truncated")),
        "final": "GVK/FINAL.md" in paths, "stop": "GVK/STOP.md" in paths,
        "stopfix": "GVK/stopfix.md" in paths, "access": "GVK/ACCESS.md" in paths,
        "pep": "GVK/PEP.json" in paths, "stages": "GVK/STAGES.md" in paths,
        "limits": "GVK/LIMITS.md" in paths, "plan": "GVK/PLAN.md" in paths,
        "dict_project": "GVK/DICT.md" in paths,
        "claims": [os.path.basename(x) for x in claims],
        "fixes": [os.path.basename(x) for x in fixes],
        "roles": [os.path.basename(x) for x in roles],
        "frag_reports": [os.path.basename(x) for x in frag],
        "findings": [os.path.basename(x) for x in findings],
        "reviews": [os.path.basename(x) for x in reviews],
        "test_plan": "REPORT/test/PLAN.json" in paths,
        "test_tasks": [os.path.basename(x) for x in tasks],
        "test_results": [os.path.basename(x) for x in results],
        "test_claims": [os.path.basename(x) for x in tclaims],
        "compliance": "REPORT/COMPLIANCE.json" in paths,
        "stack_report": "REPORT/stack.json" in paths,
        "tokens_sessions": len(under("REPORT/tokens/")),
        "skeleton_present": [x for x in paths if os.path.basename(x) in
                             ("pom.xml", "pyproject.toml", "requirements.txt", "go.mod", "Cargo.toml", "package.json")
                             or x.endswith((".csproj", ".sln"))],
        "files_total": len(paths),
    }
    if a.with_state:
        for p in ("GVK/STAGES.md", "GVK/STOP.md", "GVK/LIMITS.md"):
            if p in paths:
                st2, _, txt = fetch(a.repo, p, a.ref)
                if txt:
                    out[p] = txt.strip().splitlines()[-6:]
    st3, br, _ = call("GET", f"{API}/repos/{a.repo}/branches/gvk-plan")
    out["plan_branch"] = st3 == 200
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["now", "list", "get", "slice", "claim", "put", "append", "event", "delete", "merge"])
    ap.add_argument("--repo"); ap.add_argument("--path"); ap.add_argument("--file")
    ap.add_argument("--message", default="gvk"); ap.add_argument("--ref", default="main")
    ap.add_argument("--branch", default="main"); ap.add_argument("--role"); ap.add_argument("--owner")
    ap.add_argument("--pep", default="GVK/PEP.json"); ap.add_argument("--claim"); ap.add_argument("--schema")
    ap.add_argument("--no-guard", action="store_true"); ap.add_argument("--owner-lever", action="store_true")
    ap.add_argument("--legacy-events", action="store_true"); ap.add_argument("--with-state", action="store_true")
    ap.add_argument("--number", type=int); ap.add_argument("--merge-fragment"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if not a.repo:
        print("API ERROR: нужен --repo"); return 2

    if a.cmd == "now":
        iso, day, hms = gh_now()
        print(f"{iso} {day} {hms}")
        return 0

    if a.cmd == "slice":
        return do_slice(a)

    if a.cmd == "list":
        if not a.path:
            print("API ERROR: нужен --path"); return 2
        st, body, _ = call("GET", contents(a.repo, a.path, a.ref))
        if st != 200:
            print(f"API FAIL {st}: каталог не читается"); return 1
        if isinstance(body, dict):
            print(body.get("name", "")); return 0
        for it in body:
            print(it["name"] if not a.json else json.dumps(
                {"name": it["name"], "sha": it["sha"], "size": it.get("size")}, ensure_ascii=False))
        return 0

    if a.cmd == "get":
        if not a.path:
            print("API ERROR: нужен --path"); return 2
        st, body, _ = call("GET", contents(a.repo, a.path, a.ref))
        if st == 404:
            print("NOT FOUND"); return 1
        if st != 200:
            print(f"API FAIL {st}"); return 1
        if isinstance(body, list):
            for it in body:
                print(it["name"])
            return 0
        st2, _, txt = fetch(a.repo, a.path, a.ref)
        if txt is None:
            print("API FAIL: содержимое не прочитано"); return 1
        sys.stdout.write(txt)
        return 0

    if a.cmd == "merge":
        if not a.number:
            print("API ERROR: нужен --number (номер PR)"); return 2
        extra = ["--merge"]
        if a.merge_fragment:
            extra += ["--merge-fragment", a.merge_fragment]
        if not guard_check(a, None, None, "write", extra):
            return 1
        st, body, _ = call("PUT", f"{API}/repos/{a.repo}/pulls/{a.number}/merge", {"merge_method": "merge"})
        if st != 200:
            msg = body.get("message") if isinstance(body, dict) else str(body)[:120]
            print(f"API FAIL {st}: {msg}"); return 1
        print(f"MERGED PR {a.number}: {body.get('sha', '')[:7]}")
        return 0

    if not a.file or not os.path.exists(a.file):
        print("API ERROR: нужен существующий --file"); return 2
    text = open(a.file, encoding="utf-8").read()

    if a.cmd == "event":
        if not text.strip().startswith("{"):
            print("API ERROR: событие должно быть JSON"); return 2
        if not a.owner:
            print("API ERROR: нужен --owner (шард журнала принадлежит сессии)"); return 2
        iso, day, hms = gh_now()
        try:
            ev = json.loads(text)
        except json.JSONDecodeError as e:
            print(f"API ERROR: событие не парсится: {e}"); return 2
        ev.setdefault("at", iso)
        ev.setdefault("owner", a.owner)
        if a.role:
            ev.setdefault("role", a.role)
        tmp = a.file + ".norm"
        open(tmp, "w", encoding="utf-8").write(json.dumps(ev, ensure_ascii=False, separators=(",", ":")) + "\n")
        a.file = tmp
        line = open(tmp, encoding="utf-8").read()
        if a.legacy_events:
            path = a.path or f"REPORT/events/{day}.jsonl"
            return do_append(a, path, line, schema="event")
        path = a.path or f"REPORT/events/{day}/{a.owner}-{a.role or 'ROLE'}-{hms}.jsonl"
        st, sha, cur = fetch(a.repo, path, a.branch)
        if st == 200 and cur is not None:
            return do_append(a, path, line, schema="event")     # свой шард: чужих строк нет
        return do_write(a, path, line, atomic=True, schema="event", intent="create")

    if a.cmd == "append":
        if not a.path:
            print("API ERROR: нужен --path"); return 2
        return do_append(a, a.path, text, schema=a.schema)

    if a.cmd == "claim":
        if not a.path:
            print("API ERROR: нужен --path"); return 2
        return do_write(a, a.path, text, atomic=True, schema=a.schema, intent="create")

    if a.cmd == "put":
        if not a.path:
            print("API ERROR: нужен --path"); return 2
        return do_write(a, a.path, text, schema=a.schema, intent="update")

    if a.cmd == "delete":
        if not a.path:
            print("API ERROR: нужен --path"); return 2
        if not guard_check(a, a.path, None, "delete"):
            return 1
        for attempt in (1, 2):
            st, sha, _ = fetch(a.repo, a.path, a.branch)
            if not sha:
                print("ALREADY GONE"); return 0
            st, body, _ = call("DELETE", contents(a.repo, a.path),
                               {"message": a.message, "sha": sha, "branch": a.branch})
            if st == 404:
                print("ALREADY GONE"); return 0
            if st == 409 and attempt == 1:
                print("DELETE RETRY: sha устарел, перечитываю")
                continue
            if st != 200:
                msg = body.get("message") if isinstance(body, dict) else str(body)[:120]
                print(f"API FAIL {st}: {msg}"); return 1
            st2, _, _ = fetch(a.repo, a.path, a.branch)
            print("DELETED" if st2 == 404 else "DELETE FAIL: файл всё ещё читается")
            return 0 if st2 == 404 else 1
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"API ERROR: {type(e).__name__}: {e}"); sys.exit(2)
