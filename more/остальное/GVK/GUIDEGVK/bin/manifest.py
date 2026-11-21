#!/usr/bin/env python3
"""Сборка и проверка MANIFEST.json протокола GVK. Владелец запускает после правки модуля.

  manifest.py --root . --alv 5.2 --ppv 5.2 --tav 1.2          # пересобрать
  manifest.py --root . --check                                # проверить целостность (G7)
В манифест пишется оценка токенов на модуль — по ней считается вход роли (E1).
"""
import argparse, hashlib, json, os, sys, time

SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".idea", ".vscode"}
SKIP_FILES = {"MANIFEST.json"}
SKIP_SUFFIX = (".pyc", ".pyo", ".log", ".zip", ".exe")


def est_tokens(data):
    """Оценка gvk-bytes/1 — та же, что в bin/tokens.py (кириллица 4.4 Б/токен, остальное 3.6)."""
    text = data.decode("utf-8", "replace")
    cyr = sum(len(c.encode()) for c in text if 0x0400 <= ord(c) <= 0x052F)
    return int(round(cyr / 4.4 + (len(data) - cyr) / 3.6))


def collect(root):
    files = {}
    for dirpath, dirnames, names in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for n in sorted(names):
            if n in SKIP_FILES or n.endswith(SKIP_SUFFIX) or n.startswith("GVK_v5") and n.endswith(".md"):
                continue
            full = os.path.join(dirpath, n)
            rel = os.path.relpath(full, root).replace("\\", "/")
            data = open(full, "rb").read()
            files[rel] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                          "tokens_est": est_tokens(data)}
    return dict(sorted(files.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--alv", default="5.2")
    ap.add_argument("--ppv", default="5.2")
    ap.add_argument("--tav", default="1.2")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    man_path = os.path.join(root, "MANIFEST.json")

    if a.check:
        if not os.path.exists(man_path):
            print("MANIFEST MISSING"); return 2
        man = json.load(open(man_path, encoding="utf-8"))
        files = collect(root)
        bad = []
        for f, v in man["files"].items():
            if f not in files:
                bad.append(f"{f}: нет файла")
            elif files[f]["sha256"] != v["sha256"]:
                bad.append(f"{f}: хэш не совпал")
        extra = [f for f in files if f not in man["files"]]
        if extra:
            bad += [f"{f}: нет в манифесте" for f in extra]
        print(f"VER {man['version']} | MANIFEST " + ("OK" if not bad else "MISMATCH: " + "; ".join(bad[:12])))
        return 0 if not bad else 1

    files = collect(root)
    man = {
        "schema": "gvk/manifest/2",
        "version": f"GVK-PROTOCOL:ALV-{a.alv}_PPV-{a.ppv}_TAV-{a.tav}",
        "alv": a.alv, "ppv": a.ppv, "tav": a.tav,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "entry": "PROTOCOL.md",
        "estimator": "gvk-bytes/1",
        "budget_tokens": {"PROTOCOL.md": 4000, "GUIDEGVK/COMMON.md": 7000, "role": 2500,
                          "needs": 7000, "state": 1500, "total_input": 20000},
        "files": files,
    }
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"MANIFEST: {len(files)} файлов, {sum(v['bytes'] for v in files.values())} байт, "
          f"≈{sum(v['tokens_est'] for v in files.values())} токенов всего → {man_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
