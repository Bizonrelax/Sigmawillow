#!/usr/bin/env python3
"""GVK guard v2: программная проверка прав роли перед действием (SECURITY.md S3).

Код возврата: 0 разрешено, 1 запрещено, 2 ошибка проверки (считать запретом).
Ничего не меняет: только читает и печатает причины. Принцип: отказ при сомнении
(fail-closed). Молчаливое «нечего проверять» при ошибке инструмента запрещено.

  guard.py --role DEV --pep GVK/PEP.json --staged --claim GVK/claims/007.md --branch gvk/007
  guard.py --role DEV --pep GVK/PEP.json --paths src/app/calc/x.py --claim GVK/claims/007.md
      --paths проверяет намерение (пути), --content-file и --staged — ещё и содержимое
  guard.py --role DEV --pep GVK/PEP.json --paths GVK/STOP.md --intent create
  guard.py --role CLOSER --pep GVK/PEP.json --merge --branch main
  guard.py --role FIRST --pep GVK/PEP.json --merge --merge-fragment 000 --branch main
  guard.py --role DEV --pep GVK/PEP.json --content-file /tmp/007.json --paths REPORT/frag/007.json
  guard.py --pep-old /tmp/pep.old.json --pep-new GVK/PEP.json --role DEV
"""
import argparse, json, os, posixpath, re, subprocess, sys, urllib.request

SECRET = re.compile(
    r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|(?:Authorization:\s*(?:Bearer|Basic)|[Bb]earer)\s+[A-Za-z0-9_\-\.=+/]{20,}"
    r"|sk-[A-Za-z0-9_\-]{20,}|xox[baprs]-[A-Za-z0-9\-]{10,}"
    r"|AKIA[0-9A-Z]{16}")
SNAPSHOT = {"status", "owner", "fragment", "lease_until", "commit"}
CATALOG_FREE = {"stage", "tz_path", "tz_sha"}          # меняет только роль с правом пина
PIN_ROLES = {"FIRST", "WISH", "TZFIX", "TERMINATOR"}
MIGRATION_FREE = {"protocol_ver", "protocol_dir"}   # миграция протокола, P7.3
REPO_FREE = {"repo", "repo_kind", "created_at", "created_by"}
DEFAULT_CODE_ROOTS = ["src/", "app/", "lib/", "tests/", "test/", "cmd/", "internal/", "pkg/"]
CONTROL = re.compile(r"[\x00-\x1f]")


def rx(pat):
    out, i = "", 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out += "(?:.*/)?"; i += 3
        elif pat.startswith("**", i):
            out += ".*"; i += 2
        elif pat[i] == "*":
            out += "[^/]*"; i += 1
        elif pat[i] == "?":
            out += "[^/]"; i += 1
        else:
            out += re.escape(pat[i]); i += 1
    return re.compile("^" + out + "$")


def match(path, pats):
    return any(rx(p).match(path) for p in pats)


def sh(*a):
    """Команда инструмента. Ошибка инструмента — не «пусто», а исключение (fail-closed)."""
    r = subprocess.run(a, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(a[:3])} вернул {r.returncode}: {r.stderr.strip()[:160]}")
    return r.stdout


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def norm(p):
    """Нормализация пути: без обходов через '..', без абсолютных путей и служебных символов."""
    p = p.replace("\\", "/").strip()
    if not p or CONTROL.search(p):
        raise ValueError(f"пустой или служебный путь: {p!r}")
    if p.startswith("/") or re.match(r"^[A-Za-z]:", p):
        raise ValueError(f"абсолютный путь запрещён: {p}")
    n = posixpath.normpath(p)
    if n.startswith("../") or n == ".." or "/../" in "/" + n + "/":
        raise ValueError(f"обход каталога запрещён: {p}")
    if n.startswith(".git/") or n == ".git" or "/.git/" in "/" + n + "/":
        raise ValueError(f"служебный каталог git: {p}")
    return n


def fields(text):
    """Разбор md+/YAML/JSON-записи: 'key: value', '| key | value |', JSON-объект."""
    text = text.strip()
    if text.startswith("{"):
        try:
            return {k: v for k, v in json.loads(text).items()}
        except json.JSONDecodeError:
            pass
    def clean(x, key=False):
        s = x.strip().strip("|").strip()
        for m in ("`", '"', "\'"):
            if len(s) >= 2 and s.startswith(m) and s.endswith(m):
                s = s[1:-1].strip()
        if key:
            s = s.strip("*").strip()
        return s
    out = {}
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|"):
            raw = [c.strip() for c in s.strip("|").split("|")]
            cells = [clean(raw[0], key=True)] + [clean(c) for c in raw[1:]]
            if len(cells) >= 2 and cells[0] and not set(cells[0]) <= set("-: "):
                out.setdefault(cells[0].lower(), cells[1])
            continue
        if ":" in s and not s.startswith("#"):
            k, v = s.split(":", 1)
            k = clean(k.lstrip("- "), key=True).lower()
            if k and " " not in k:
                out.setdefault(k, clean(v))
    return out


def claim_info(path):
    if not path:
        return None, [], []
    if not os.path.exists(path):
        raise RuntimeError(f"захват не читается: {path}")
    g = fields(open(path, encoding="utf-8").read())
    frag = str(g.get("fragment") or g.get("target") or "").strip() or None
    def split(v):
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return [p.strip() for p in re.split(r"[,;]", str(v)) if p.strip()]
    own = split(g.get("packages") or g.get("package") or "")
    tests = split(g.get("tests") or g.get("test_globs") or "")
    return frag, own, tests


def stack_lists(pep):
    st = pep.get("stack", {}) or {}
    lang = (st.get("language") or "auto").lower()
    by = st.get("skeleton_by_stack", {}) or {}
    skel = list(st.get("skeleton", [])) + list(by.get(lang, [])) + list(by.get("common", []))
    code = st.get("code_by_stack", {}) or {}
    app = list(st.get("app_code", [])) + list((code.get(lang) or {}).get("app", []))
    test = list(st.get("test_code", [])) + list((code.get(lang) or {}).get("test", []))
    if lang not in code:                    # стек не выбран: код приложения любого стека
        app += [x for v in code.values() for x in (v or {}).get("app", [])]
        test += [x for v in code.values() for x in (v or {}).get("test", [])]
    lang_roots = list((code.get(lang) or {}).get("roots", []))
    if not lang_roots:                      # стек ещё не выбран: корни всех стеков
        lang_roots = [r for v in code.values() for r in (v or {}).get("roots", [])]
    roots = lang_roots + [r for r in st.get("code_roots", []) if r not in lang_roots]
    return skel, app, test, roots or DEFAULT_CODE_ROOTS


def now_utc(cli_now):
    """Время только из заголовка Date GitHub (C4). Нет времени — гранты не действуют."""
    if cli_now:
        return cli_now
    try:
        req = urllib.request.Request("https://api.github.com", method="HEAD")
        req.add_header("User-Agent", "gvk-guard/5.2")
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.headers.get("Date", "")
    except Exception:
        return ""


def parse_time(s):
    import email.utils, datetime
    if not s:
        return None
    s = s.strip()
    try:
        if s.endswith("Z") or "T" in s:
            return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return email.utils.parsedate_to_datetime(s)
    except Exception:
        return None


def access_text(a):
    """ACCESS.md берётся из origin/main, а не из рабочего каталога: локальная подделка не действует."""
    if a.access_file:
        return open(a.access_file, encoding="utf-8").read() if os.path.exists(a.access_file) else ""
    try:
        return sh("git", "show", f"{a.access_ref}:GVK/ACCESS.md")
    except Exception:
        return ""


def access_grants(a, role, frag):
    txt = access_text(a)
    if not txt.strip():
        return [], []
    g = fields(txt)
    notes = []
    who = (g.get("grantee") or "").strip()
    if not who:
        return [], ["ACCESS.md без grantee — грант не действует"]
    if who not in (role, frag):
        return [], []
    if (g.get("granted_by") or "").strip().lower() != "owner":
        return [], ["ACCESS.md без granted_by: owner — грант не действует"]
    if (g.get("confirmed") or "").strip().lower() not in ("true", "yes", "да"):
        return [], ["ACCESS.md без confirmed: true — рычаг не подтверждён"]
    exp = parse_time(g.get("expires_at", ""))
    cur = parse_time(now_utc(a.now))
    if exp is None:
        return [], ["ACCESS.md без expires_at — грант не действует"]
    if cur is None:
        return [], ["время GitHub недоступно — грант не применяется (fail-closed)"]
    if exp <= cur:
        return [], ["ACCESS.md истёк — грант не действует"]
    glob = g.get("glob")
    if not glob:
        return [], []
    mode = (g.get("mode") or "ЗАПИСЬ").upper()
    notes.append(f"грант {glob} ({mode}) до {g.get('expires_at')}")
    return [(glob, mode)], notes


def under_roots(path, roots):
    return any(path.startswith(r if r.endswith("/") else r + "/") for r in roots)


def owns(path, own, roots):
    """Владение пакетом: границы каталогов, не подстрока. Пакет понимается и как
    путь от корня репозитория (`app.calc` → app/calc), и как путь от корня кода
    (`com.foo` → src/main/java/com/foo). Обе записи приняты, обе по границам."""
    for root in roots:
        r = root if root.endswith("/") else root + "/"
        if not path.startswith(r):
            continue
        rel = path[len(r):]
        for o in own:
            base = o.replace(".", "/").strip("/")
            for cand in (rel, path):
                if cand == base or cand.startswith(base + "/") or posixpath.splitext(cand)[0] == base:
                    return True
    return False


def own_test(path, own, test_code):
    """Тест своего пакета: tests/test_calc.py при пакете app.calc (конвенция имени)."""
    if test_code and not match(path, test_code):
        return False
    stem = posixpath.splitext(posixpath.basename(path))[0].lower()
    for o in own:
        last = o.replace(".", "/").strip("/").split("/")[-1].lower()
        if last and last in stem:
            return True
    return False


def secret_scan(text, hits):
    if SECRET.search(text):
        hits.append("секрет в изменениях (S6): запись запрещена")
    tok = os.environ.get("T") or ""
    if not tok and os.path.exists("/opt/.t"):
        try:
            tok = open("/opt/.t", encoding="utf-8").read().strip()
        except OSError:
            tok = ""
    if len(tok) >= 12 and tok in text:
        hits.append("значение токена владельца в изменениях (S6): запись запрещена")


def check_pep_diff(a):
    bad = []
    if not (a.pep_old and a.pep_new):
        print("GUARD ERROR: нужны --pep-old и --pep-new"); return 2
    o, n = load(a.pep_old), load(a.pep_new)
    for k in sorted(set(o) | set(n)):
        if k in ("roles", "pep_ver"):
            continue
        if o.get(k) == n.get(k):
            continue
        if k in CATALOG_FREE:
            if a.role not in PIN_ROLES:
                bad.append(f"пин ТЗ меняет только роль с правом: {k} (роль {a.role})")
        elif k == "limits":
            if not (a.allow_limits or a.owner_lever):
                bad.append("потолки меняются только рычагом ПОТОЛОК (--allow-limits)")
        elif k == "stack":
            if a.role not in ("FIRST", "WISH", "CLOSER"):
                bad.append(f"стек реестра меняет FIRST/WISH/CLOSER, не {a.role}")
            elif a.role != "FIRST" and not a.allow_stack:
                bad.append("смена стека только рычагом СТЕК/ЖЕЛАНИЕ (--allow-stack, ST8)")
        elif k in MIGRATION_FREE:
            if a.role != "FIRST" and not a.allow_catalog:
                bad.append(f"версию протокола в реестре поднимает FIRST при миграции P7.3: {k} (роль {a.role})")
        elif k in REPO_FREE:
            if not (a.allow_catalog and a.role in ("FIRST", "WISH")):
                bad.append(f"адрес и тип репозитория меняет FIRST/WISH по рычагу: {k}")
        else:
            bad.append(f"поле реестра изменено: {k}")
    for r in sorted(set(o.get("roles", {})) | set(n.get("roles", {}))):
        ov, nv = o.get("roles", {}).get(r), n.get("roles", {}).get(r)
        if ov is None:
            if not a.allow_catalog:
                bad.append(f"роль {r} добавлена в каталог без рычага РОЛИ ОБНОВИ")
            continue
        if nv is None:
            bad.append(f"роль {r} удалена из каталога (P8)")
            continue
        for k in sorted(set(ov) | set(nv)):
            if ov.get(k) == nv.get(k):
                continue
            if k in SNAPSHOT:
                if a.role and r != a.role and not a.allow_mass_release:
                    bad.append(f"чужой снимок занятости: {r}.{k}")
            elif not a.allow_catalog:
                bad.append(f"каталог роли {r} изменён: {k}")
    print("GUARD OK: реестр" if not bad else "GUARD DENY: " + "; ".join(bad))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role"); ap.add_argument("--pep", default="GVK/PEP.json")
    ap.add_argument("--staged", action="store_true"); ap.add_argument("--paths", nargs="*")
    ap.add_argument("--content-file", action="append", default=[])
    ap.add_argument("--merge", action="store_true"); ap.add_argument("--merge-fragment")
    ap.add_argument("--claim"); ap.add_argument("--branch")
    ap.add_argument("--intent", choices=["create", "update", "delete", "write"], default="write")
    ap.add_argument("--access-file"); ap.add_argument("--access-ref", default="origin/main")
    ap.add_argument("--now")
    ap.add_argument("--pep-old"); ap.add_argument("--pep-new")
    ap.add_argument("--allow-catalog", action="store_true")
    ap.add_argument("--allow-limits", action="store_true")
    ap.add_argument("--allow-stack", action="store_true",
                    help="рычаг СТЕК/ЖЕЛАНИЕ: разрешает смену stack в реестре (ST8)")
    ap.add_argument("--allow-mass-release", action="store_true")
    ap.add_argument("--owner-lever", action="store_true",
                    help="рычаг владельца ДОСТУП: разрешает запись GVK/ACCESS.md и снятие потолков")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    bad, notes = [], []

    if a.pep_old or a.pep_new:
        return check_pep_diff(a)

    if not a.role or not os.path.exists(a.pep):
        print("GUARD ERROR: нет роли или реестра"); return 2
    pep = load(a.pep)
    role = pep.get("roles", {}).get(a.role)
    if role is None:
        print(f"GUARD ERROR: роль {a.role} отсутствует в реестре"); return 2
    perm = role.get("permissions")
    if not isinstance(perm, dict):
        print(f"GUARD ERROR: у роли {a.role} нет permissions"); return 2

    frag, own, test_globs = claim_info(a.claim)
    tz = pep.get("tz_path", "docs/TZ.md")
    skel, app_deny, test_code, roots = stack_lists(pep)
    proto = pep.get("protocol_dir", "")
    deny = [p for p in perm.get("deny", []) + pep.get("hard_deny", []) if not p.startswith("@")]
    if "@skeleton" in perm.get("deny", []):
        deny += skel
    if "@protocol" in perm.get("deny", []) and proto:
        deny += [proto.rstrip("/") + "/**"]
    app_deny = app_deny if "@app_code" in perm.get("deny", []) else []
    allow = [tz if x == "@tz_path" else x for x in perm.get("write", [])]
    create_only = [tz if x == "@tz_path" else x for x in perm.get("create_only", [])]
    grants, gnotes = access_grants(a, a.role, frag)
    notes += gnotes
    for g, mode in grants:
        if mode.startswith("ЗАПИС") or mode.startswith("WRITE"):
            allow.append(g)

    if a.branch:
        pats = perm.get("branches")
        if pats and not match(a.branch, pats):
            bad.append(f"ветка {a.branch} вне прав роли {a.role}")
    elif perm.get("branches"):
        bad.append(f"роль {a.role} ограничена ветками {perm['branches']}: нужен --branch")

    if a.merge:
        if not perm.get("merge_main"):
            bad.append(f"роль {a.role} не имеет права слияния в main")
        if a.role == "FIRST":
            f = (a.merge_fragment or frag or "").strip()
            if f not in ("000", "0"):
                bad.append("FIRST сливает только каркас 000 (C10.6): нужен --merge-fragment 000")
        if bad:
            print("GUARD DENY: " + "; ".join(bad)); return 1
        print("GUARD OK: слияние" + ("; " + "; ".join(notes) if notes else "")); return 0

    if not (a.paths or a.staged or a.content_file):
        print("GUARD ERROR: не задан режим проверки (--paths/--staged/--content-file)"); return 2

    paths = []
    for p in (a.paths or []):
        try:
            paths.append(norm(p))
        except ValueError as e:
            bad.append(str(e))
    if a.staged:
        paths += [norm(p) for p in sh("git", "diff", "--cached", "--name-only").splitlines() if p.strip()]
    if a.staged and not paths and not a.content_file:
        notes.append("индекс пуст")

    for p in paths:
        if a.owner_lever and p == "GVK/ACCESS.md":
            notes.append("ACCESS.md записан по рычагу владельца (L6): событие access_grant обязательно")
            continue
        if app_deny and match(p, app_deny) and not match(p, test_code):
            bad.append(f"код приложения недоступен роли на запись: {p}"); continue
        if match(p, deny):
            bad.append(f"запрещённый путь: {p}"); continue
        if "@tz_path" in perm.get("deny", []) and p == tz:
            bad.append(f"ТЗ недоступно роли на запись: {p}"); continue
        if "@foreign_packages" in perm.get("deny", []) and under_roots(p, roots):
            if test_globs and match(p, test_globs):
                pass                                   # тесты объявлены в захвате
            elif not own:
                bad.append(f"нет захвата с packages: владение не доказано для {p} (--claim)"); continue
            elif not owns(p, own, roots) and not own_test(p, own, test_code):
                bad.append(f"чужой пакет: {p}"); continue
        if match(p, create_only):
            if a.intent != "create":
                bad.append(f"путь только для атомарного создания: {p} (--intent create)")
            continue
        if not match(p, allow):
            bad.append(f"вне прав записи роли {a.role}: {p}")

    diff = sh("git", "diff", "--cached") if a.staged else ""
    for p in (a.paths or []):
        if a.intent == "delete":
            continue
        if os.path.isfile(p):
            diff += open(p, encoding="utf-8", errors="ignore").read()
        # отсутствующий файл — это проверка намерения, а не содержимого: не ошибка
    for f in a.content_file:
        if not os.path.isfile(f):
            bad.append(f"содержимое для проверки не читается: {f}"); continue
        diff += open(f, encoding="utf-8", errors="ignore").read()
    secret_scan(diff, bad)

    if a.json:
        print(json.dumps({"ok": not bad, "role": a.role, "paths": paths, "deny": bad, "notes": notes},
                         ensure_ascii=False))
    else:
        tail = ("; " + "; ".join(notes)) if notes else ""
        print(("GUARD OK: " + ", ".join(paths[:8]) + tail) if not bad else "GUARD DENY: " + "; ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:                      # ошибка проверки = запрет
        print(f"GUARD ERROR: {type(e).__name__}: {e}"); sys.exit(2)
