#!/usr/bin/env python3
"""GVK guard: программная проверка прав роли перед действием (SECURITY.md S3).
Код возврата: 0 разрешено, 1 запрещено, 2 ошибка проверки (считать запретом).
Ничего не меняет: только читает и печатает причины.
"""
import argparse, json, os, re, subprocess, sys

SECRET = re.compile(r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|Authorization: Bearer [A-Za-z0-9_\-\.]{20,}")
SNAPSHOT = {"status", "owner", "fragment", "lease_until", "commit"}


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
    return subprocess.run(a, capture_output=True, text=True).stdout


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def access_grants(path, role, frag):
    """Активные расширения прав из GVK/ACCESS.md (S7). Срок проверяется вызывающим по времени GitHub."""
    if not path or not os.path.exists(path):
        return []
    txt = open(path, encoding="utf-8").read()
    g = {}
    for line in txt.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            g[k.strip().lstrip("| ").strip()] = v.strip().strip("|").strip()
    who = g.get("grantee", "")
    if who and who not in (role, frag):
        return []
    if g.get("glob"):
        return [(g["glob"], g.get("mode", "ЗАПИСЬ"))]
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role"); ap.add_argument("--pep", default="GVK/PEP.json")
    ap.add_argument("--staged", action="store_true"); ap.add_argument("--paths", nargs="*")
    ap.add_argument("--merge", action="store_true"); ap.add_argument("--claim")
    ap.add_argument("--access", default="GVK/ACCESS.md")
    ap.add_argument("--pep-old"); ap.add_argument("--pep-new")
    a = ap.parse_args()
    bad = []

    if a.pep_old or a.pep_new:  # изменение реестра: каталог и права неприкосновенны (C10.17)
        if not (a.pep_old and a.pep_new):
            print("GUARD ERROR: нужны --pep-old и --pep-new"); return 2
        o, n = load(a.pep_old), load(a.pep_new)
        for k in set(o) | set(n):
            if k in ("roles", "pep_ver"):
                continue
            if o.get(k) != n.get(k) and k not in ("stage", "tz_path", "tz_sha", "limits"):
                bad.append(f"поле реестра изменено: {k}")
        for r, v in n.get("roles", {}).items():
            ov = o.get("roles", {}).get(r)
            if ov is None:
                continue
            for k in set(ov) | set(v):
                if k not in SNAPSHOT and ov.get(k) != v.get(k):
                    bad.append(f"каталог роли {r} изменён: {k}")
        print("GUARD OK: реестр" if not bad else "GUARD DENY: " + "; ".join(bad))
        return 1 if bad else 0

    if not a.role or not os.path.exists(a.pep):
        print("GUARD ERROR: нет роли или реестра"); return 2
    pep = load(a.pep)
    role = pep.get("roles", {}).get(a.role)
    if role is None:
        print(f"GUARD ERROR: роль {a.role} отсутствует в реестре"); return 2
    perm = role["permissions"]
    frag = None
    own = []
    if a.claim and os.path.exists(a.claim):
        for line in open(a.claim, encoding="utf-8"):
            if line.strip().startswith("packages"):
                own = [p.strip() for p in re.split(r"[:,]", line)[1:] if p.strip()]
            if line.strip().startswith("fragment"):
                frag = line.split(":", 1)[1].strip()
    tz = pep.get("tz_path", "docs/TZ.md")
    deny = [p for p in perm.get("deny", []) + pep.get("hard_deny", []) if not p.startswith("@")]
    allow = [tz if x == "@tz_path" else x for x in perm.get("write", [])]
    for g, mode in access_grants(a.access, a.role, frag):
        if mode.upper().startswith("ЗАПИС"):
            allow.append(g)

    if a.merge:
        if not perm.get("merge_main"):
            bad.append(f"роль {a.role} не имеет права слияния в main")
        print("GUARD OK: слияние" if not bad else "GUARD DENY: " + "; ".join(bad))
        return 1 if bad else 0

    paths = list(a.paths or [])
    if a.staged:
        paths += [p for p in sh("git", "diff", "--cached", "--name-only").splitlines() if p]
    if not paths:
        print("GUARD OK: нечего проверять"); return 0

    for p in paths:
        p = p.replace("\\", "/")
        if match(p, deny):
            bad.append(f"запрещённый путь: {p}"); continue
        if "@tz_path" in perm.get("deny", []) and p == tz:
            bad.append(f"ТЗ недоступно роли на запись: {p}"); continue
        if "@foreign_packages" in perm.get("deny", []) and own and p.startswith("src/"):
            if not any(p.replace("/", ".").find(o.replace(".", ".")) >= 0 or
                       p.startswith("src/main/java/" + o.replace(".", "/") + "/") or
                       p.startswith("src/test/java/" + o.replace(".", "/") + "/") for o in own):
                bad.append(f"чужой пакет: {p}"); continue
        if not match(p, allow):
            bad.append(f"вне прав записи роли {a.role}: {p}")

    diff = sh("git", "diff", "--cached") if a.staged else ""
    if not a.staged:
        for p in paths:
            if os.path.isfile(p):
                try:
                    diff += open(p, encoding="utf-8", errors="ignore").read()
                except OSError:
                    pass
    if SECRET.search(diff):
        bad.append("секрет в изменениях (S6): коммит запрещён")

    print("GUARD OK: " + ", ".join(paths[:8]) if not bad else "GUARD DENY: " + "; ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # ошибка проверки = запрет
        print(f"GUARD ERROR: {type(e).__name__}: {e}"); sys.exit(2)
