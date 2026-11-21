#!/usr/bin/env python3
"""GVK tokens: учёт расхода токенов сессии и сводка по проекту (ECONOMY E7–E10).

Честность важнее красоты: точные числа берутся только из счётчика платформы
(--exact-in/--exact-out). Всё остальное — оценка модели `gvk-bytes/1` и помечается
`source: estimate`. Выдавать оценку за точный расход запрещено (C10.19).

  tokens.py est     --files PROTOCOL.md GUIDEGVK/COMMON.md      # оценка входа
  tokens.py session --role DEV --owner gvk-qwen-7 --fragment 007 \
                    --read PROTOCOL.md GUIDEGVK/COMMON.md --wrote /tmp/007.json \
                    --calls 42 --model qwen3-coder --out /tmp/tokens.json
  tokens.py line    --file /tmp/tokens.json                     # строка для чата
  tokens.py rollup  --dir REPORT/tokens [--json]                # сводка проекта
"""
import argparse, json, os, sys, glob

CYR = (0x0400, 0x052F)
CYR_BPT = 4.4          # байт на токен для кириллицы (2 байта на знак, ~2.2 знака на токен)
OTH_BPT = 3.6          # байт на токен для латиницы, кода и пунктуации
ESTIMATOR = "gvk-bytes/1"


def est_text(text):
    cyr = oth = 0
    for ch in text:
        n = len(ch.encode("utf-8"))
        if CYR[0] <= ord(ch) <= CYR[1]:
            cyr += n
        else:
            oth += n
    return int(round(cyr / CYR_BPT + oth / OTH_BPT))


def est_files(paths):
    total, per = 0, {}
    for p in paths:
        if not os.path.isfile(p):
            per[p] = None
            continue
        t = est_text(open(p, encoding="utf-8", errors="ignore").read())
        per[p] = t
        total += t
    return total, per


def read_text(p):
    return open(p, encoding="utf-8", errors="ignore").read() if p and os.path.isfile(p) else ""


def session(a):
    reads = list(a.read or [])
    wrote = list(a.wrote or [])
    in_est, per_in = est_files(reads)
    in_est += est_text(read_text(a.chat_in))
    out_est, per_out = est_files(wrote)
    out_est += est_text(read_text(a.chat_out))
    exact_in = a.exact_in if a.exact_in is not None else None
    exact_out = a.exact_out if a.exact_out is not None else None
    ti = exact_in if exact_in is not None else in_est
    to = exact_out if exact_out is not None else out_est
    if exact_in is not None and exact_out is not None:
        source = "exact"
    elif exact_in is None and exact_out is None:
        source = "estimate"
    else:
        source = "mixed"
    rec = {
        "schema": "gvk/tokens/1", "schema_ver": "1",
        "at": a.at, "owner": a.owner, "role": a.role, "session_id": a.session_id or f"{a.owner}-{a.at}",
        "model": a.model or "unknown", "protocol_ver": a.protocol_ver or "",
        "source": source, "estimator": ESTIMATOR if source != "exact" else "",
        "in_tokens": ti, "out_tokens": to, "total_tokens": ti + to,
        "in_exact": exact_in, "out_exact": exact_out,
        "in_est": in_est, "out_est": out_est,
        "calls": a.calls or 0, "api_calls": a.api_calls or 0,
        "modules_read": reads, "artifacts_written": wrote,
        "bytes_read": sum(os.path.getsize(p) for p in reads if os.path.isfile(p)),
        "dict_saved_tokens": a.dict_saved or 0,
    }
    for k in ("fragment", "stage", "lever", "note", "tz_sha"):
        v = getattr(a, k, None)
        if v not in (None, ""):
            rec[k] = v
    txt = json.dumps(rec, ensure_ascii=False, indent=1) + "\n"
    if a.out:
        open(a.out, "w", encoding="utf-8").write(txt)
        print(f"TOKENS WROTE {a.out}: {rec['total_tokens']} ({source})")
    else:
        sys.stdout.write(txt)
    return 0


def line(a):
    d = json.load(open(a.file, encoding="utf-8"))
    n = d.get("total_tokens", 0)
    mark = "" if d.get("source") == "exact" else " (оценка)"
    print(f"расход токенов: {n}{mark}")
    return 0


def rollup(a):
    recs = []
    for p in sorted(glob.glob(os.path.join(a.dir, "**", "*.json"), recursive=True)):
        if os.path.basename(p) == "TOTAL.json":
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if d.get("schema") == "gvk/tokens/1":
            recs.append(d)
    by = {}
    for d in recs:
        for key in ("role", "model", "fragment", "stage"):
            k = f"{key}:{d.get(key, '—')}"
            e = by.setdefault(k, {"sessions": 0, "total": 0, "exact": 0, "calls": 0})
            e["sessions"] += 1
            e["total"] += d.get("total_tokens", 0)
            e["exact"] += 1 if d.get("source") == "exact" else 0
            e["calls"] += d.get("calls", 0)
    total = sum(d.get("total_tokens", 0) for d in recs)
    exact = sum(1 for d in recs if d.get("source") == "exact")
    saved = sum(d.get("dict_saved_tokens", 0) for d in recs)
    out = {"schema": "gvk/tokens_total/1", "schema_ver": "1", "at": a.at or "",
           "sessions": len(recs), "total_tokens": total, "exact_sessions": exact,
           "estimated_sessions": len(recs) - exact, "dict_saved_tokens": saved,
           "by": dict(sorted(by.items()))}
    if a.json:
        sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
        return 0
    print(f"сессий {len(recs)} | токенов {total} | точных {exact} | оценочных {len(recs) - exact} | словарная экономия {saved}")
    print("срез | сессий | токенов | точных | вызовов")
    for k, v in out["by"].items():
        if k.startswith("stage:") or k.startswith("fragment:"):
            continue
        print(f"{k} | {v['sessions']} | {v['total']} | {v['exact']} | {v['calls']}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["est", "session", "line", "rollup"])
    ap.add_argument("--files", nargs="*"); ap.add_argument("--read", nargs="*"); ap.add_argument("--wrote", nargs="*")
    ap.add_argument("--chat-in"); ap.add_argument("--chat-out")
    ap.add_argument("--exact-in", type=int); ap.add_argument("--exact-out", type=int)
    ap.add_argument("--role"); ap.add_argument("--owner"); ap.add_argument("--fragment"); ap.add_argument("--stage", type=int)
    ap.add_argument("--model"); ap.add_argument("--protocol-ver"); ap.add_argument("--session-id")
    ap.add_argument("--lever"); ap.add_argument("--note"); ap.add_argument("--tz-sha")
    ap.add_argument("--calls", type=int); ap.add_argument("--api-calls", type=int); ap.add_argument("--dict-saved", type=int)
    ap.add_argument("--at", default=""); ap.add_argument("--out"); ap.add_argument("--file"); ap.add_argument("--dir", default="REPORT/tokens")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.cmd == "est":
        if not a.files:
            print("TOKENS ERROR: нужен --files"); return 2
        total, per = est_files(a.files)
        for p, t in per.items():
            print(f"{t if t is not None else 'НЕТ ФАЙЛА'}\t{p}")
        print(f"ИТОГО (оценка {ESTIMATOR}): {total}")
        return 0
    if a.cmd == "session":
        if not a.role or not a.owner:
            print("TOKENS ERROR: нужны --role и --owner"); return 2
        return session(a)
    if a.cmd == "line":
        if not a.file:
            print("TOKENS ERROR: нужен --file"); return 2
        return line(a)
    return rollup(a)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"TOKENS ERROR: {type(e).__name__}: {e}"); sys.exit(2)
