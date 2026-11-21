#!/usr/bin/env python3
"""GVK pep: реестр ролей без чтения реестра целиком (ECONOMY E2).

Реестр.machine полон, вход агента узок: агент печатает только свою карточку.
Полный `PEP.json` в контекст не грузить — это ~7k токенов вместо ~0.6k.

  pep.py card    --role DEV [--pep GVK/PEP.json]        # карточка роли + общий минимум
  pep.py init    --repo O/R --tz docs/TZ.md --stack python --kind code --out /tmp/PEP.json
  pep.py snap    --role DEV --owner gvk-qwen-7 --fragment 007 --state busy|free [--pep ...] --out ...
  pep.py check   [--pep GVK/PEP.json]                   # структура каталога и прав
  pep.py budget  [--pep ...] [--manifest ../MANIFEST.json]  # вход роли против limits.budget_input_tokens, код 1 при превышении
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
G = os.path.dirname(HERE)
TEMPLATE = os.path.join(G, "pep.template.json")
SNAPSHOT = ("status", "owner", "fragment", "lease_until", "commit")
SLICE_TOKENS = 1200  # срез состояния C6, принятый расчётный вес (ECONOMY E1)


def est_text(text):
    cyr = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
    return int(round(cyr / 4.4 + (len(text) - cyr) / 3.6))


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def dump(obj, out):
    txt = json.dumps(obj, ensure_ascii=False, indent=1) + "\n"
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"PEP WROTE {out} ({len(txt.encode())} байт)")
    else:
        sys.stdout.write(txt)


def resolved_stack(pep):
    st = pep.get("stack", {}) or {}
    lang = (st.get("language") or "auto").lower()
    by = st.get("skeleton_by_stack", {}) or {}
    code = (st.get("code_by_stack", {}) or {}).get(lang, {}) or {}
    return {
        "language": lang,
        "version": st.get("version", ""),
        "packaging": st.get("packaging", ""),
        "skeleton": sorted(set(list(by.get("common", [])) + list(by.get(lang, [])) + list(st.get("skeleton", [])))),
        "app_code": sorted(set(list(code.get("app", [])) + list(st.get("app_code", [])))),
        "test_code": sorted(set(list(code.get("test", [])) + list(st.get("test_code", [])))),
        "code_roots": code.get("roots") or st.get("code_roots") or [],
        "version_file": (st.get("version_file", {}) or {}).get(lang, ""),
    }


def card_obj(pep, role):
    r = pep.get("roles", {}).get(role)
    if r is None:
        return None
    return {
        "role": role, "ver": r.get("ver"), "file": r.get("file"),
        "needs": r.get("needs", []), "lazy": r.get("lazy", []), "dicts": r.get("dicts", []),
        "singleton": r.get("singleton"), "claim": r.get("claim", ""),
        "lease_h": r.get("lease_h"), "lease_renew": r.get("lease_renew", False),
        "lever": r.get("lever"), "deficit": r.get("deficit", ""),
        "permissions": r.get("permissions", {}),
        "snapshot": {k: r.get(k) for k in SNAPSHOT if r.get(k) is not None},
        "common": {
            "pep_ver": pep.get("pep_ver"), "protocol_ver": pep.get("protocol_ver"),
            "repo": pep.get("repo"), "repo_kind": pep.get("repo_kind", "code"),
            "protocol_dir": pep.get("protocol_dir", ""),
            "stage": pep.get("stage"), "tz_path": pep.get("tz_path"), "tz_sha": pep.get("tz_sha"),
            "limits": pep.get("limits", {}), "priority": pep.get("priority", []),
            "hard_deny": pep.get("hard_deny", []),
            "stack": resolved_stack(pep),
        },
    }
def card(pep, role):
    out = card_obj(pep, role)
    if out is None:
        print(f"PEP ERROR: роль {role} отсутствует в каталоге"); return 2
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    return 0


def check(pep):
    errs = []
    for k in ("schema", "pep_ver", "protocol_ver", "repo", "stage", "tz_path", "priority", "roles"):
        if k not in pep:
            errs.append(f"нет поля {k}")
    if pep.get("repo_kind") not in ("code", "doc"):
        errs.append("repo_kind должен быть code или doc")
    for name in pep.get("priority", []):
        if name not in pep.get("roles", {}):
            errs.append(f"priority ссылается на отсутствующую роль {name}")
    for name, r in pep.get("roles", {}).items():
        for k in ("file", "needs", "singleton", "lease_h", "permissions", "ver", "claim"):
            if k not in r:
                errs.append(f"{name}: нет поля {k}")
        pm = r.get("permissions", {})
        for k in ("read", "write", "deny", "merge_main", "tools", "branches"):
            if k not in pm:
                errs.append(f"{name}.permissions: нет {k}")
        for k in ("write", "deny", "read", "branches", "create_only"):
            v = pm.get(k, [])
            if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
                errs.append(f"{name}.permissions.{k} должен быть списком строк")
        if pm.get("merge_main") and name not in ("FIRST", "CLOSER"):
            errs.append(f"{name}: merge_main разрешён только FIRST и CLOSER (C10.6)")
        if r.get("singleton") and not r.get("claim") and name != "OBSERVER":
            errs.append(f"{name}: роль-одиночка без пути захвата")
        if name != "OBSERVER" and not r.get("singleton") and "{fragment}" not in r.get("claim", "") and "{task}" not in r.get("claim", ""):
            errs.append(f"{name}: масштабируемая роль без шаблона захвата")
    if errs:
        print("PEP CHECK FAIL:\n  " + "\n  ".join(errs[:30])); return 1
    print(f"PEP CHECK OK: {len(pep.get('roles', {}))} ролей, pep_ver {pep.get('pep_ver')}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["card", "init", "snap", "check", "budget"])
    ap.add_argument("--pep", default="GVK/PEP.json")
    ap.add_argument("--role"); ap.add_argument("--owner"); ap.add_argument("--fragment")
    ap.add_argument("--state", choices=["busy", "free"], default="busy")
    ap.add_argument("--lease-until", default=""); ap.add_argument("--commit", default="")
    ap.add_argument("--repo"); ap.add_argument("--tz", default="docs/TZ.md"); ap.add_argument("--tz-sha", default="")
    ap.add_argument("--stack", default="auto"); ap.add_argument("--kind", choices=["code", "doc"], default="code")
    ap.add_argument("--at", default=""); ap.add_argument("--protocol-ver", default="")
    ap.add_argument("--protocol-dir", default="")
    ap.add_argument("--out"); ap.add_argument("--manifest")
    a = ap.parse_args()

    if a.cmd == "init":
        if not a.repo:
            print("PEP ERROR: нужен --repo"); return 2
        p = load(TEMPLATE)
        p.update({"repo": a.repo, "created_at": a.at, "created_by": a.owner or "", "tz_path": a.tz,
                  "tz_sha": a.tz_sha, "repo_kind": a.kind, "protocol_dir": a.protocol_dir})
        if a.protocol_ver:
            p["protocol_ver"] = a.protocol_ver
        p["stack"]["language"] = a.stack
        for r in p["roles"].values():
            r.update({"status": "свободен", "owner": None, "fragment": None, "lease_until": None, "commit": None})
        dump(p, a.out)
        return 0

    if not os.path.exists(a.pep):
        print(f"PEP ERROR: реестр не читается: {a.pep}"); return 2
    pep = load(a.pep)

    if a.cmd == "card":
        if not a.role:
            print("PEP ERROR: нужен --role"); return 2
        return card(pep, a.role)
    if a.cmd == "check":
        return check(pep)
    if a.cmd == "snap":
        if not a.role or a.role not in pep.get("roles", {}):
            print("PEP ERROR: нужен существующий --role"); return 2
        r = pep["roles"][a.role]
        if a.state == "busy":
            r.update({"status": "занят", "owner": a.owner or r.get("owner"),
                      "fragment": a.fragment, "lease_until": a.lease_until or None,
                      "commit": a.commit or None})
        else:
            r.update({"status": "свободен", "owner": None, "fragment": None, "lease_until": None, "commit": None})
        dump(pep, a.out)
        return 0
    if a.cmd == "budget":
        man = load(a.manifest or os.path.join(os.path.dirname(G), "MANIFEST.json"))
        tok = {f: v.get("tokens_est", 0) for f, v in man.get("files", {}).items()}
        limit = int((pep.get("limits", {}) or {}).get("budget_input_tokens", 0)) or 0
        rows, over = [], []
        for name, r in pep.get("roles", {}).items():
            files = ["PROTOCOL.md", "GUIDEGVK/COMMON.md", "GUIDEGVK/" + os.path.basename(r.get("file", ""))]
            files += ["GUIDEGVK/" + m for m in r.get("needs", [])]
            card_txt = json.dumps(card_obj(pep, name), ensure_ascii=False, indent=1)
            base = sum(tok.get(f, 0) for f in files) + est_text(card_txt) + SLICE_TOKENS
            lazy = sum(tok.get("GUIDEGVK/" + m, 0) for m in r.get("lazy", []))
            rows.append((name, base, lazy))
            if limit and base > limit:
                over.append(f"{name} {base} > {limit}")
        print(f"срез состояния принят за {SLICE_TOKENS} токенов; предел входа {limit or 'не задан'}")
        print("роль | вход без lazy (оценка токенов) | все lazy худший случай")
        for name, base, lazy in sorted(rows, key=lambda x: -x[1]):
            mark = "  ПРЕВЫШЕНИЕ" if limit and base > limit else ""
            print(f"{name} | {base} | {base + lazy}{mark}")
        if over:
            print("PEP BUDGET FAIL: " + "; ".join(over)); return 1
        print("PEP BUDGET OK: все роли в пределах бюджета входа")
        return 0
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"PEP ERROR: {type(e).__name__}: {e}"); sys.exit(2)
