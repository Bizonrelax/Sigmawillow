#!/usr/bin/env python3
"""GVK validate: проверка JSON-артефакта по схеме до записи (COMMON C12.4).
Работает без внешних зависимостей; подмножество JSON Schema draft-07:
type, required, properties, items, enum, const, minimum, additionalProperties.
Пример: python3 bin/validate.py --schema schema/report.schema.json --file REPORT/frag/007.json
Код возврата: 0 валидно, 1 невалидно, 2 ошибка проверки.
"""
import argparse, json, sys

TYPES = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool, "null": type(None)}


def check(val, sch, path, errs):
    if not isinstance(sch, dict) or not sch:
        return
    if "const" in sch and val != sch["const"]:
        errs.append(f"{path}: ожидалось {sch['const']!r}, получено {val!r}")
    if "enum" in sch and val not in sch["enum"]:
        errs.append(f"{path}: {val!r} не из {sch['enum']}")
    t = sch.get("type")
    if t:
        ts = t if isinstance(t, list) else [t]
        ok = any(isinstance(val, TYPES[x]) and not (x == "integer" and isinstance(val, bool)) for x in ts)
        if not ok:
            errs.append(f"{path}: ожидался тип {t}"); return
    if isinstance(val, dict):
        for r in sch.get("required", []):
            if r not in val:
                errs.append(f"{path}: нет обязательного поля {r}")
        props = sch.get("properties", {})
        for k, v in val.items():
            if k in props:
                check(v, props[k], f"{path}.{k}", errs)
            elif sch.get("additionalProperties") is False:
                errs.append(f"{path}: лишнее поле {k}")
    if isinstance(val, list):
        for i, v in enumerate(val):
            check(v, sch.get("items", {}), f"{path}[{i}]", errs)
    if "minItems" in sch and isinstance(val, list) and len(val) < sch["minItems"]:
        errs.append(f"{path}: элементов {len(val)} < {sch['minItems']}")
    if "minimum" in sch and isinstance(val, (int, float)) and val < sch["minimum"]:
        errs.append(f"{path}: {val} < {sch['minimum']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", required=True)
    ap.add_argument("--file", required=True)
    a = ap.parse_args()
    sch = json.load(open(a.schema, encoding="utf-8"))
    txt = open(a.file, encoding="utf-8").read()
    try:
        data = json.loads(txt)
    except json.JSONDecodeError as e:
        print(f"VALIDATE FAIL: непарсируемый JSON: {e}"); return 1
    errs = []
    if a.file.endswith(".jsonl"):
        for n, line in enumerate(txt.splitlines(), 1):
            if line.strip():
                check(json.loads(line), sch, f"строка {n}", errs)
    else:
        check(data, sch, "$", errs)
    if errs:
        print("VALIDATE FAIL:\n  " + "\n  ".join(errs[:20])); return 1
    print(f"VALIDATE OK: {a.file} по {sch.get('title', a.schema)}"); return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"VALIDATE ERROR: {type(e).__name__}: {e}"); sys.exit(2)
