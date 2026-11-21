#!/usr/bin/env python3
"""GVK dict: трёхуровневые словари сжатия и измеримая выгода (ECONOMY E3–E6).

Уровни: GLOBAL (все роли) → GROUP (группа ролей) → ROLE (одна роль) → PROJECT
(домен проекта, `GVK/DICT.md`). Коды самоадресные: `%<адрес словаря><номер>`,
поэтому чужой сжатый текст читается без знания роли автора.

  dict.py load    --role DEV [--pep GVK/PEP.json]        # активный словарь роли (нужен редко)
  dict.py load    --role DEV --codes %g3,%d1             # раскрыть только встреченные коды
  dict.py encode  --role DEV --in /tmp/007.json --out /tmp/007c.json
  dict.py decode  --in /tmp/007c.json
  dict.py audit   --corpus REPORT --corpus GVK           # выгода по факту корпуса
  dict.py propose --corpus REPORT --ns j                 # кандидаты в словарь проекта
  dict.py lint    --in /tmp/007c.json                    # коды известны, зоны соблюдены
"""
import argparse, glob, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
G = os.path.dirname(HERE)
DICT_DIR = os.path.join(G, "dict")
ZONES = {"remaining", "remarks", "symptom", "manual_notes", "why", "note", "detail", "proof", "evidence"}
FORBID_KEYS = {"schema", "schema_ver", "id", "fragment", "task", "status", "verdict", "severity",
               "event", "kind", "env", "level", "owner", "role", "branch", "at", "lease_until",
               "tz_sha", "last_green", "checked_sha", "base_sha", "fixed_sha", "sha", "path",
               "file", "line", "packages", "protocol_ver", "model", "finding_id", "change_id"}
NS = {"GLOBAL": "g", "GROUP-CODE": "k", "GROUP-TEST": "t", "GROUP-STATE": "s",
      "ROLE-FIRST": "f", "ROLE-DEV": "d", "ROLE-CLEANER": "c", "ROLE-REVIEWER": "r",
      "ROLE-PLANNER_TEST": "p", "ROLE-TESTER": "e", "ROLE-COMPLIANCE": "a", "ROLE-CLOSER": "l",
      "ROLE-TZFIX": "x", "ROLE-WISH": "w", "ROLE-OBSERVER": "o", "ROLE-TERMINATOR": "n",
      "ROLE-TERMINATOR2": "m", "ROLE-FIREFIGHTER": "i", "PROJECT": "j"}
CODE = re.compile(r"%[a-z][0-9a-z]{1,2}")
BLOCK = re.compile(r"<!--DICT:BEGIN-->(.*?)<!--DICT:END-->", re.S)

sys.path.insert(0, HERE)
from tokens import est_text  # noqa: E402  один оценщик на весь протокол


def parse_dict(path):
    out = {}
    if not os.path.isfile(path):
        return out
    for line in open(path, encoding="utf-8"):
        s = line.rstrip("\n")
        if not s or s.startswith(("#", "---", "<!--", "|", "id:", "file:", "desc:", "name:", "etymology:", "F:", "Q:", "N:", "O:", "T:")):
            continue
        parts = s.split(" ", 1)
        if len(parts) == 2 and CODE.fullmatch(parts[0]) and parts[1].strip():
            out[parts[0]] = parts[1].strip()
    return out


def dict_paths(names, dict_dir=DICT_DIR, project=None):
    paths = []
    for n in names:
        if n == "PROJECT":
            if project:
                paths.append(project)
        else:
            paths.append(os.path.join(dict_dir, n + ".dict.md"))
    return paths


def active(role, pep_path=None, dict_dir=DICT_DIR, project=None, names=None):
    if names is None:
        names = ["GLOBAL"]
        # реестр проекта не найден — берём поставленный шаблон: групповые и ролевой
        # словари должны работать и без него, иначе роль молча теряет свои коды
        if pep_path and not os.path.isfile(pep_path):
            pep_path = os.path.join(G, "pep.template.json")
        if pep_path and os.path.isfile(pep_path):
            pep = json.load(open(pep_path, encoding="utf-8"))
            names = pep.get("roles", {}).get(role, {}).get("dicts", ["GLOBAL"])
            if project and os.path.isfile(project):
                names = list(names) + ["PROJECT"]
    merged, clashes, missing = {}, [], []
    for n in names:
        for p in dict_paths([n], dict_dir, project):
            if not os.path.isfile(p):
                missing.append(p); continue
            for code, phrase in parse_dict(p).items():
                if code in merged and merged[code] != phrase:
                    clashes.append(f"{code}: {os.path.basename(p)} против другого словаря")
                merged[code] = phrase
    return merged, clashes, missing


def all_dicts(dict_dir=DICT_DIR, project=None):
    merged = {}
    for p in sorted(glob.glob(os.path.join(dict_dir, "*.dict.md"))) + ([project] if project else []):
        merged.update(parse_dict(p))
    return merged


def encode_text(text, mapping):
    items = sorted(mapping.items(), key=lambda kv: -len(kv[1]))
    saved = 0
    for code, phrase in items:
        if phrase in text:
            n = text.count(phrase)
            saved += n * (est_text(phrase) - est_text(code))
            text = text.replace(phrase, code)
    return text, saved


def walk_json(obj, mapping, key=None):
    saved = 0
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            out[k], s = walk_json(v, mapping, k)
            saved += s
        return out, saved
    if isinstance(obj, list):
        out = []
        for v in obj:
            r, s = walk_json(v, mapping, key)
            out.append(r); saved += s
        return out, saved
    if isinstance(obj, str) and key in ZONES and key not in FORBID_KEYS:
        return encode_text(obj, mapping)
    return obj, 0


def do_encode(a, mapping):
    raw = open(a.inp, encoding="utf-8").read()
    if a.inp.endswith(".json"):
        data = json.loads(raw)
        data, saved = walk_json(data, mapping)
        out = json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"
    elif a.inp.endswith(".jsonl"):
        lines, saved = [], 0
        for ln in raw.splitlines():
            if not ln.strip():
                continue
            d, s = walk_json(json.loads(ln), mapping)
            saved += s
            lines.append(json.dumps(d, ensure_ascii=False, separators=(",", ":")))
        out = "\n".join(lines) + "\n"
    else:
        saved = 0
        def repl(m):
            nonlocal saved
            t, s = encode_text(m.group(1), mapping)
            saved += s
            return "<!--DICT:BEGIN-->" + t + "<!--DICT:END-->"
        out = BLOCK.sub(repl, raw)
        if saved == 0:
            print("DICT: в md сжимать только внутри блока DICT:BEGIN/END — замен нет")
    if a.out:
        open(a.out, "w", encoding="utf-8").write(out)
    else:
        sys.stdout.write(out)
    print(f"DICT ENCODE: экономия ≈ {saved} токенов ({len(raw.encode())} → {len(out.encode())} байт)", file=sys.stderr)
    return 0


def do_decode(a, mapping):
    raw = open(a.inp, encoding="utf-8").read()
    inv = {c: p for c, p in mapping.items()}
    out = CODE.sub(lambda m: inv.get(m.group(0), m.group(0)), raw)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(out)
    else:
        sys.stdout.write(out)
    return 0


def corpus_strings(dirs):
    vals = []
    for d in dirs:
        for p in glob.glob(os.path.join(d, "**", "*"), recursive=True):
            if not os.path.isfile(p):
                continue
            if p.endswith((".json", ".jsonl")):
                try:
                    txt = open(p, encoding="utf-8").read()
                    objs = [json.loads(l) for l in txt.splitlines() if l.strip()] if p.endswith(".jsonl") else [json.loads(txt)]
                except Exception:
                    continue
                def rec(o, key=None):
                    if isinstance(o, dict):
                        for k, v in o.items():
                            rec(v, k)
                    elif isinstance(o, list):
                        for v in o:
                            rec(v, key)
                    elif isinstance(o, str) and key in ZONES:
                        vals.append(o)
                for o in objs:
                    rec(o)
            elif p.endswith(".md"):
                for m in BLOCK.finditer(open(p, encoding="utf-8").read()):
                    vals.append(m.group(1))
    return vals


def do_audit(a, mapping):
    if not a.corpus:
        print("DICT ERROR: audit требует --corpus <каталог> (можно несколько): без корпуса выгода не считается, "
              "а совет «убрать» был бы ложным. Список записей — dict.py load")
        return 2
    vals = corpus_strings(a.corpus)
    if not vals:
        print("DICT ERROR: в корпусе нет служебных строк (REPORT/GVK пусты или не содержат нужных полей): "
              "выгоду посчитать нельзя, словарь не трогай")
        return 2
    rows, total = [], 0
    for code, phrase in sorted(mapping.items()):
        freq = sum(v.count(phrase) for v in vals)
        gain = freq * (est_text(phrase) - est_text(code))
        overhead = est_text(code + " " + phrase)
        total += gain
        rows.append((code, freq, gain, overhead, phrase))
    print("код | повторов в корпусе | выгода токенов | цена строки словаря | фраза")
    for code, freq, gain, overhead, phrase in rows:
        flag = "" if gain - overhead > 0 else "  ← невыгодно, убрать"
        print(f"{code} | {freq} | {gain} | {overhead} | {phrase[:60]}{flag}")
    print(f"ИТОГО выгода ≈ {total} токенов на корпус; записей {len(mapping)}")
    print("Словарь живёт в инструменте, а не в контексте (E4): цена загрузки в контекст не платится.")
    return 0


def do_propose(a, mapping):
    vals = corpus_strings(a.corpus or [])
    known = set(mapping.values())
    cand = {}
    for v in vals:
        for part in re.split(r"[;\n]|(?<=\.)\s", v):
            s = part.strip()
            if not s or s in known:
                continue
            if est_text(s) < a.min_tokens:
                continue
            cand[s] = cand.get(s, 0) + 1
    rows = [(s, n, n * (est_text(s) - 3)) for s, n in cand.items() if n >= a.min_freq]
    rows.sort(key=lambda r: -r[2])
    used = {c for c in mapping if c.startswith("%" + a.ns)}
    idx = 1
    print("# кандидаты в словарь проекта (проверить глазами, затем дописать в GVK/DICT.md)")
    for s, n, gain in rows[: a.limit]:
        while f"%{a.ns}{idx}" in used:
            idx += 1
        print(f"%{a.ns}{idx} {s}    # повторов {n}, выгода ≈ {gain}")
        idx += 1
    if not rows:
        print("# кандидатов нет: короткие или редкие фразы сжатие не выигрывают")
    return 0


def do_lint(a, mapping):
    raw = open(a.inp, encoding="utf-8").read()
    known = all_dicts(a.dict_dir, a.project)
    bad = []
    for m in CODE.finditer(raw):
        if m.group(0) not in known:
            bad.append(f"неизвестный код {m.group(0)}")
    if a.inp.endswith((".json", ".jsonl")):
        objs = [json.loads(l) for l in raw.splitlines() if l.strip()] if a.inp.endswith(".jsonl") else [json.loads(raw)]
        def rec(o, key=None):
            if isinstance(o, dict):
                for k, v in o.items():
                    if CODE.search(k):
                        bad.append(f"код в ключе JSON: {k}")
                    rec(v, k)
            elif isinstance(o, list):
                for v in o:
                    rec(v, key)
            elif isinstance(o, str) and CODE.search(o):
                if key not in ZONES:
                    bad.append(f"код в поле вне разрешённых зон: {key}")
        for o in objs:
            rec(o)
    if bad:
        print("DICT LINT FAIL:\n  " + "\n  ".join(sorted(set(bad))[:20])); return 1
    print("DICT LINT OK")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["load", "encode", "decode", "audit", "propose", "lint"])
    ap.add_argument("--role"); ap.add_argument("--pep", default="GVK/PEP.json")
    ap.add_argument("--dict-dir", default=DICT_DIR); ap.add_argument("--project")
    ap.add_argument("--names", nargs="*")
    ap.add_argument("--codes", help="через запятую: раскрыть только эти коды (дешёвый вход)")
    ap.add_argument("--in", dest="inp"); ap.add_argument("--out")
    ap.add_argument("--corpus", action="append")
    ap.add_argument("--ns", default="j"); ap.add_argument("--min-tokens", type=int, default=6)
    ap.add_argument("--min-freq", type=int, default=3); ap.add_argument("--limit", type=int, default=20)
    a = ap.parse_args()

    if a.cmd == "load":
        if not a.role:
            print("DICT ERROR: нужен --role"); return 2
        m, clashes, missing = active(a.role, a.pep, a.dict_dir, a.project, a.names)
        if a.codes:
            want = [c.strip() for c in a.codes.split(",") if c.strip()]
            unknown = [c for c in want if c not in m]
            m = {c: v for c, v in m.items() if c in want}
            for c in unknown:
                print(f"# неизвестный код: {c}", file=sys.stderr)
        if clashes:
            print("DICT ERROR: коллизия кодов:\n  " + "\n  ".join(clashes)); return 2
        for p in missing:
            print(f"# словарь не поставлен: {p}", file=sys.stderr)
        for c, p in sorted(m.items()):
            print(f"{c} {p}")
        print(f"# записей {len(m)}, цена словаря ≈ {est_text(chr(10).join(f'{c} {p}' for c, p in m.items()))} токенов", file=sys.stderr)
        return 0
    if a.cmd in ("encode", "decode", "lint") and not a.inp:
        print("DICT ERROR: нужен --in"); return 2
    if a.cmd == "encode":
        m, clashes, _ = active(a.role or "", a.pep, a.dict_dir, a.project, a.names)
        if clashes:
            print("DICT ERROR: коллизия кодов"); return 2
        return do_encode(a, m)
    if a.cmd == "decode":
        return do_decode(a, all_dicts(a.dict_dir, a.project))
    if a.cmd == "lint":
        return do_lint(a, all_dicts(a.dict_dir, a.project))
    if a.cmd == "audit":
        return do_audit(a, all_dicts(a.dict_dir, a.project))
    return do_propose(a, all_dicts(a.dict_dir, a.project))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"DICT ERROR: {type(e).__name__}: {e}"); sys.exit(2)
