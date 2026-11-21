#!/usr/bin/env python3
"""GVK doctor: статический аудит поставки протокола. Владелец запускает после правки.

Ловит класс дефектов, который не виден в золотом случае: маршрут на несуществующий
модуль, роль, которой нечем писать её же артефакты, каркас стека вне прав FIRST,
схема с ключом, который валидатор не понимает, словарь с коллизией кодов,
рычаг без роли-исполнителя, битая ссылка на модуль.

  python3 bin/doctor.py [--root .] [--verbose]
Код возврата: 0 — чисто, 1 — есть замечания, 2 — ошибка аудита.
"""
import argparse, glob, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RES = []

# Что каждая роль обязана уметь записывать по своим инструкциям (FM2, CT3, файлы ролей).
MUST_WRITE = {
    "FIRST": ["GVK/PLAN.md", "GVK/PEP.json", "GVK/AUDIT.md", "GVK/STAGES.md", "GVK/LIMITS.md",
              "GVK/PORTS.md", "GVK/LINKS.md", "GVK/claims/000.md", "GVK/roles/FIRST.md",
              "REPORT/frag/000.json", "REPORT/stack.json", "REPORT/tokens/x.json", "README.md"],
    "DEV": ["GVK/claims/007.md", "GVK/STATE.md", "GVK/REQUESTS.md", "GVK/AUDIT.md",
            "REPORT/frag/007.json", "REPORT/ckpt/007.json", "REPORT/events/20261122/a-DEV-1.jsonl",
            "REPORT/tokens/20261122/a-DEV-1.json", "README.md", "THIRD-PARTY-NOTICES.md", "GVK/STOP.md"],
    "CLEANER": ["GVK/fixes/007.md", "REPORT/frag/007.json", "REPORT/finding/007-ab12cd34.json",
                "REPORT/ckpt/007.json", "REPORT/tokens/x.json", "THIRD-PARTY-NOTICES.md", "GVK/STOP.md"],
    "REVIEWER": ["GVK/roles/REVIEWER.md", "REPORT/review/007-ab12cd34.json",
                 "REPORT/finding/007-ab12cd34.json", "REPORT/tokens/x.json", "GVK/STOP.md"],
    "PLANNER_TEST": ["GVK/roles/PLANNER_TEST.md", "REPORT/test/PLAN.json", "REPORT/test/T-001.json",
                     "REPORT/tokens/x.json"],
    "TESTER": ["REPORT/test/claims/T-001.json", "REPORT/test/R-001.json", "tests/test_x.py",
               "src/test/java/XTest.java", "REPORT/finding/007-ab12cd34.json", "REPORT/tokens/x.json"],
    "COMPLIANCE": ["GVK/roles/COMPLIANCE.md", "REPORT/COMPLIANCE.json", "THIRD-PARTY-NOTICES.md",
                   "licenses/MIT.txt", "REPORT/tokens/x.json"],
    "CLOSER": ["GVK/FINAL.md", "REPORT/FINAL.json", "CHANGELOG.md", "README.md", "README_RU.md",
               "pom.xml", "pyproject.toml", "GVK/claims/007.md", "REPORT/tokens/x.json"],
    "TZFIX": ["GVK/stopfix.md", "GVK/STOP.md", "GVK/STAGES.md", "GVK/CHANGE-001.md", "GVK/PLAN.md",
              "docs/TZ.md", "REPORT/tokens/x.json"],
    "WISH": ["GVK/roles/WISH.md", "GVK/PLAN.md", "GVK/PORTS.md", "GVK/CHANGE-001.md", "docs/TZ.md",
             "REPORT/tokens/x.json"],
    "OBSERVER": ["REPORT/tokens/20261122/o-OBSERVER-1.json", "REPORT/events/20261122/o-OBSERVER-1.jsonl"],
    "TERMINATOR": ["GVK/roles/TERMINATOR.md", "GVK/STOP.md", "GVK/STAGES.md", "GVK/PLAN.md",
                   "GVK/claims/007.md", "GVK/releases/x.md", "docs/TZ.md", "REPORT/tokens/x.json"],
    "TERMINATOR2": ["GVK/roles/TERMINATOR2.md", "GVK/claims/007.md", "GVK/fixes/007.md",
                    "GVK/releases/x.md", "GVK/LIMITS.md", "GVK/STOP.md", "REPORT/tokens/x.json"],
    "FIREFIGHTER": ["GVK/PLAN.md", "GVK/AUDIT.md", "src/app/x.py", "REPORT/tokens/x.json"],
}
# Рычаги, которые меняют состояние вне обычных прав роли: проверяются отдельно.
LEVER_ONLY = {"TERMINATOR2": {"GVK/LIMITS.md", "GVK/ACCESS.md"}}


def ck(name, ok, detail=""):
    RES.append((name, bool(ok), detail))


def load_guard():
    import importlib.util
    spec = importlib.util.spec_from_file_location("gvkguard", os.path.join(HERE, "guard.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(HERE)))
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    G = os.path.join(root, "GUIDEGVK")
    pep = json.load(open(os.path.join(G, "pep.template.json"), encoding="utf-8"))
    guard = load_guard()
    sys.path.insert(0, HERE)
    from tokens import est_text

    # 1. манифест
    r = subprocess.run([sys.executable, os.path.join(HERE, "manifest.py"), "--root", root, "--check"],
                       capture_output=True, text=True)
    ck("манифест целостен", r.returncode == 0, r.stdout.strip()[:120])

    # 2. шапки md+
    bad_head, ids = [], {}
    for p in glob.glob(os.path.join(G, "**", "*.md"), recursive=True) + [os.path.join(root, "PROTOCOL.md")]:
        t = open(p, encoding="utf-8").read()
        name = os.path.basename(p)
        if not t.startswith("---\n"):
            bad_head.append(f"{name}: нет шапки"); continue
        head = t[4:t.index("\n---", 4)]
        f = dict(re.findall(r"^([a-zA-Z]+): (.*)$", head, re.M))
        for k in ("id", "file", "etymology", "desc", "name", "F", "Q"):
            if k not in f:
                bad_head.append(f"{name}: нет поля {k}")
        if f.get("file") != name:
            bad_head.append(f"{name}: file={f.get('file')}")
        if len(f.get("id", "")) > 17:
            bad_head.append(f"{name}: id длиннее 17")
        ids.setdefault(f.get("id"), []).append(name)
    ck("шапки md+ валидны", not bad_head, "; ".join(bad_head[:6]))
    dup = {k: v for k, v in ids.items() if len(v) > 1}
    ck("идентификаторы модулей уникальны", not dup, str(dup))

    # 3. ограждения
    fences, nested = [], []
    for p in glob.glob(os.path.join(root, "**", "*.md"), recursive=True):
        if os.path.basename(p).startswith("GVK_v5"):
            continue
        inside = False
        for ln in open(p, encoding="utf-8"):
            if re.match(r"^\s*`{3,}", ln):
                if inside and len(ln) - len(ln.lstrip("`")) > 3:
                    nested.append(os.path.basename(p))
                inside = not inside
        if inside:
            fences.append(os.path.basename(p))
    ck("тройные ограждения парные", not fences, ", ".join(fences))
    ck("вложенных ограждений нет", not nested, ", ".join(nested))

    # 4. маршрутизация
    miss = []
    for name, r in pep["roles"].items():
        for m in r.get("needs", []) + r.get("lazy", []):
            if not os.path.isfile(os.path.join(G, m)):
                miss.append(f"{name}: {m}")
        if not os.path.isfile(os.path.join(root, r["file"])):
            miss.append(f"{name}: файл роли {r['file']}")
        for d in r.get("dicts", []):
            if not os.path.isfile(os.path.join(G, "dict", d + ".dict.md")):
                miss.append(f"{name}: словарь {d}")
    ck("маршруты roles → модули и словари существуют", not miss, "; ".join(miss[:6]))
    ck("priority ссылается на существующие роли", all(x in pep["roles"] for x in pep["priority"]))
    lm = pep.get("lever_map", {})
    ck("lever_map ссылается на существующие роли", bool(lm) and all(v in pep["roles"] for v in lm.values()))
    lev = open(os.path.join(G, "LEVERS.md"), encoding="utf-8").read()
    table = lev[lev.index("| Команда | Роль |"):lev.index("L3. `продолжай`")]
    rows = [l for l in table.splitlines() if l.startswith("|")][2:]
    no_role = []
    for row in rows:
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", row.strip("|"))]
        if len(cells) < 2:
            continue
        cmd, role = cells[0], cells[1]
        key = cmd.split(" ")[0].replace("\\", "")
        if role not in pep["roles"]:
            no_role.append(f"{cmd}: роль {role}")
        elif not any(k.startswith(key) or key.startswith(k.split(" ")[0]) for k in lm):
            no_role.append(f"{cmd}: нет в lever_map")
    ck("каждый рычаг таблицы имеет роль и запись в lever_map", not no_role, "; ".join(no_role[:6]))

    # 5. права покрывают обязанности роли
    tz = pep.get("tz_path", "docs/TZ.md")
    gaps = []
    for role, paths in MUST_WRITE.items():
        pm = pep["roles"][role]["permissions"]
        skel, app, test, roots = guard.stack_lists(pep)
        deny = [x for x in pm.get("deny", []) + pep.get("hard_deny", []) if not x.startswith("@")]
        if "@skeleton" in pm.get("deny", []):
            deny += skel
        if "@protocol" in pm.get("deny", []) and pep.get("protocol_dir"):
            deny += [pep["protocol_dir"].rstrip("/") + "/**"]
        allow = [tz if x == "@tz_path" else x for x in pm.get("write", [])]
        create = [tz if x == "@tz_path" else x for x in pm.get("create_only", [])]
        for p in paths:
            if p in LEVER_ONLY.get(role, set()):
                continue
            if guard.match(p, deny) and not guard.match(p, create):
                gaps.append(f"{role}: {p} в deny")
            elif not guard.match(p, allow + create):
                gaps.append(f"{role}: {p} вне write")
    ck("права ролей покрывают их артефакты", not gaps, "; ".join(gaps[:8]))

    # 6. каркас каждого стека доступен FIRST и закрыт DEV
    skel_gaps = []
    for lang, files in pep["stack"]["skeleton_by_stack"].items():
        if lang == "common":
            continue
        p2 = json.loads(json.dumps(pep)); p2["stack"]["language"] = lang
        skel, _, _, _ = guard.stack_lists(p2)
        first = pep["roles"]["FIRST"]["permissions"]
        for f in skel:
            probe = f.replace("**", "x").replace("*", "x")
            if not guard.match(probe, first["write"]):
                skel_gaps.append(f"FIRST не пишет {f} ({lang})")
        dev = pep["roles"]["DEV"]["permissions"]
        if not guard.match(probe, [x for x in dev["deny"] if not x.startswith("@")] + skel):
            skel_gaps.append(f"DEV может писать каркас {lang}")
    ck("каркас любого стека: FIRST пишет, DEV закрыт", not skel_gaps, "; ".join(sorted(set(skel_gaps))[:8]))

    # 7. схемы и валидатор
    sch_bad = []
    for p in sorted(glob.glob(os.path.join(G, "schema", "*.json"))):
        r = subprocess.run([sys.executable, os.path.join(HERE, "validate.py"), "--schema", p,
                            "--file", p, "--strict-keywords"], capture_output=True, text=True)
        if "неподдерживаемые ключи" in r.stdout:
            sch_bad.append(os.path.basename(p) + ": " + r.stdout.split("неподдерживаемые ключи:")[-1].strip()[:60])
    ck("схемы не используют непонятных валидатору ключей", not sch_bad, "; ".join(sch_bad[:4]))
    ct = open(os.path.join(G, "CONTRACTS.md"), encoding="utf-8").read()
    ex_bad = []
    for i, block in enumerate(re.findall(r"```json\n(.*?)\n```", ct, re.S)):
        try:
            obj = json.loads(block)
        except json.JSONDecodeError as e:
            ex_bad.append(f"пример {i}: {e}"); continue
        key = (obj.get("schema") or "").split("/")[-2] if obj.get("schema") else ""
        sch = os.path.join(G, "schema", key + ".schema.json")
        if not key or not os.path.isfile(sch):
            ex_bad.append(f"пример {i}: нет схемы {key}"); continue
        f = os.path.join(root, f".doctor-ex{i}.json")
        open(f, "w", encoding="utf-8").write(block)
        r = subprocess.run([sys.executable, os.path.join(HERE, "validate.py"), "--schema", sch, "--file", f],
                           capture_output=True, text=True)
        os.remove(f)
        if r.returncode != 0:
            ex_bad.append(f"пример {i}: {r.stdout.strip()[:70]}")
    ck("примеры контрактов проходят свои схемы", not ex_bad, "; ".join(ex_bad[:4]))

    # 8. словари
    codes, dupc, weak = {}, [], []
    for p in sorted(glob.glob(os.path.join(G, "dict", "*.dict.md"))):
        for ln in open(p, encoding="utf-8"):
            if not ln.startswith("%"):
                continue
            code, _, phrase = ln.rstrip("\n").partition(" ")
            if code in codes:
                dupc.append(code)
            codes[code] = phrase
            if est_text(phrase) - est_text(code) < 5:
                weak.append(code)
    ck("коды словарей уникальны", not dupc, ", ".join(dupc))
    ck("записи словарей выгодны по длине", not weak, ", ".join(weak))
    dz = set(json.loads(json.dumps(pep.get("dicts", {}))).get("zones", []))
    import importlib.util
    spec = importlib.util.spec_from_file_location("gvkdict", os.path.join(HERE, "dict.py"))
    dm = importlib.util.module_from_spec(spec); spec.loader.exec_module(dm)
    ck("зоны сжатия в реестре и в инструменте совпадают", dz == set(dm.ZONES), str(dz ^ set(dm.ZONES)))

    # 9. ссылки на модули
    names = {os.path.basename(p) for p in glob.glob(os.path.join(G, "**", "*.md"), recursive=True)}
    names |= {"PROTOCOL.md", "GUIDE.md", "CHANGELOG.md", "SELFTEST.md", "MANIFEST.json", "README.md",
              "README_RU.md", "THIRD-PARTY-NOTICES.md", "TZ.md", "PLAN.md", "STATE.md", "STOP.md",
              "STAGES.md", "LIMITS.md", "ACCESS.md", "AUDIT.md", "PORTS.md", "LINKS.md", "REQUESTS.md",
              "FINAL.md", "DICT.md", "PEP.md", "SKEL_JAVA.md", "SKEL_PY.md", "SKEL_OTHER.md",
              "DESIGN.md", "TODO.md", "SPEC.md", "NOTES.md", "LICENSES.md", "LICENSE",
              "CLAIM.md", "RELEASE.md", "TZFIX.md", "WISH.md"}
    broken = []
    for p in glob.glob(os.path.join(G, "*.md")) + [os.path.join(root, "PROTOCOL.md")]:
        for ref in re.findall(r"`([A-Z][A-Z_0-9]*\.md)`", open(p, encoding="utf-8").read()):
            if ref not in names and not ref.startswith(("CHANGE-", "ROLE_")):
                broken.append(f"{os.path.basename(p)} → {ref}")
    ck("ссылки на модули разрешаются", not broken, "; ".join(sorted(set(broken))[:6]))

    # 10. оценка токенов в манифесте совпадает с оценщиком
    man = json.load(open(os.path.join(root, "MANIFEST.json"), encoding="utf-8"))
    drift = []
    for f, v in man["files"].items():
        if not f.endswith(".md"):
            continue
        p = os.path.join(root, f)
        if os.path.isfile(p) and abs(est_text(open(p, encoding="utf-8").read()) - v.get("tokens_est", 0)) > 2:
            drift.append(f)
    ck("оценки токенов в манифесте согласованы с оценщиком", not drift, ", ".join(drift[:5]))

    # 19. строка «Нужны модули» в файле роли совпадает с needs реестра
    pep_t = json.load(open(os.path.join(G, "pep.template.json"), encoding="utf-8"))
    mismatch = []
    for name, r in pep_t.get("roles", {}).items():
        rp = os.path.join(G, os.path.basename(r.get("file", "")))
        if not os.path.isfile(rp):
            mismatch.append(f"{name}: нет файла роли"); continue
        txt = open(rp, encoding="utf-8").read()
        m = re.search(r"Нужны модули:(.*?)(?:\.\s|Грузить)", txt, re.S)
        stated = set(re.findall(r"[A-Z_]+\.md", m.group(1))) if m else set()
        if stated != set(r.get("needs", [])):
            mismatch.append(f"{name}: строка {sorted(stated)} против needs {sorted(r.get('needs', []))}")
    ck("строка «Нужны модули» совпадает с needs реестра", not mismatch, "; ".join(mismatch[:3]))

    # 20. бюджет входа: pep.py budget укладывается в limits.budget_input_tokens
    limit = int((pep_t.get("limits", {}) or {}).get("budget_input_tokens", 0))
    tok = {f: v.get("tokens_est", 0) for f, v in man["files"].items()}
    over = []
    for name, r in pep_t.get("roles", {}).items():
        files = ["PROTOCOL.md", "GUIDEGVK/COMMON.md", "GUIDEGVK/" + os.path.basename(r.get("file", ""))]
        files += ["GUIDEGVK/" + m for m in r.get("needs", [])]
        base = sum(tok.get(f, 0) for f in files)
        if limit and base > limit:
            over.append(f"{name} {base}>{limit}")
    ck("вход ролей укладывается в бюджет G1", bool(limit) and not over, "; ".join(over[:3]) or "limits.budget_input_tokens не задан")

    # 21. нет битых и чужеродных символов в тексте поставки
    junk = re.compile("[\ufffd\u3000-\u303f\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")
    hits = []
    for p in sorted(glob.glob(os.path.join(root, "**", "*"), recursive=True)):
        if not os.path.isfile(p) or os.path.basename(p).startswith("GVK_v5"):
            continue
        if not p.endswith((".md", ".py", ".json")):
            continue
        for n, line in enumerate(open(p, encoding="utf-8", errors="replace"), 1):
            m = junk.search(line)
            if m:
                hits.append(f"{os.path.relpath(p, root)}:{n} {m.group()!r}")
    ck("нет битых и чужеродных символов", not hits, "; ".join(hits[:4]))

    # 22. процедура входа выполнима каждой ролью (рождение, захват, событие, учёт, снимок)
    entry_bad = []
    gp = os.path.join(HERE, "guard.py")
    pp = os.path.join(G, "pep.template.json")
    for role, r in pep["roles"].items():
        brs = r["permissions"].get("branches") or []
        br = (brs[0] if brs else "gvk/001").replace("{fragment}", "001").replace("<ROLE>", role)
        if "*" in br:
            br = "gvk/001"
        claim = (r.get("claim") or "").replace("{fragment}", "001").replace("{task}", "T-001")
        creates = [f"REPORT/events/20261122/a1-{role}-120000.jsonl",
                   f"REPORT/tokens/20261122/a1-{role}-120000.json"]
        if role != "OBSERVER":
            creates = ["GVK/births/20261122T1200-a1.md"] + creates + ([claim] if claim else [])
        groups = [("create", creates)]
        if role != "OBSERVER":
            groups.append(("update", ["GVK/PEP.json"]))
            if claim:
                groups.append(("delete", [claim]))
        for intent, paths in groups:
            if not paths:
                continue
            res = subprocess.run([sys.executable, gp, "--pep", pp, "--role", role, "--branch", br,
                                  "--intent", intent, "--paths"] + paths, capture_output=True, text=True)
            if res.returncode != 0:
                entry_bad.append(f"{role}/{intent}: {res.stdout.strip()[:90]}")
    ck("процедура входа выполнима каждой ролью", not entry_bad, "; ".join(entry_bad[:3]))

    ok = sum(1 for _, o, _ in RES if o)
    print(f"\nАУДИТ ПОСТАВКИ GVK — {ok}/{len(RES)} проверок\n")
    for n, o, d in RES:
        if o and not a.verbose:
            print(f"  OK   {n}")
        else:
            print(f"  {'OK  ' if o else 'ЗАМЕЧАНИЕ'} {n}" + (f" — {d}" if d else ""))
    return 0 if ok == len(RES) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"DOCTOR ERROR: {type(e).__name__}: {e}"); sys.exit(2)
