#!/usr/bin/env python3
"""Сборка MANIFEST.json протокола GVK. Владелец запускает после правки любого модуля.
Пример: python3 bin/manifest.py --root . --alv 5.1 --ppv 5.1 --tav 1.1
"""
import argparse, hashlib, json, os, time

SKIP = {"MANIFEST.json", ".git", "__pycache__"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--alv", default="5.1")
    ap.add_argument("--ppv", default="5.1")
    ap.add_argument("--tav", default="1.1")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    files = {}
    for dirpath, dirnames, names in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        for n in sorted(names):
            if n in SKIP:
                continue
            full = os.path.join(dirpath, n)
            rel = os.path.relpath(full, root).replace("\\", "/")
            data = open(full, "rb").read()
            files[rel] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    man = {
        "schema": "gvk/manifest/1",
        "version": f"GVK-PROTOCOL:ALV-{a.alv}_PPV-{a.ppv}_TAV-{a.tav}",
        "alv": a.alv, "ppv": a.ppv, "tav": a.tav,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "entry": "PROTOCOL.md",
        "budget_tokens": {"PROTOCOL.md": 4000, "GUIDEGVK/COMMON.md": 6000, "role": 4000, "state": 3000},
        "files": dict(sorted(files.items())),
    }
    out = os.path.join(root, "MANIFEST.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"MANIFEST: {len(files)} файлов, {sum(v['bytes'] for v in files.values())} байт → {out}")


if __name__ == "__main__":
    main()
