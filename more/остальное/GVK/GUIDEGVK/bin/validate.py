#!/usr/bin/env python3
"""GVK validate v2: проверка JSON/JSONL-артефакта по схеме до записи (COMMON C12.4).

Без внешних зависимостей. Подмножество JSON Schema draft-07:
type (в т.ч. список типов), required, properties, patternProperties,
additionalProperties (bool или схема), items, enum, const, minimum, maximum,
exclusiveMinimum, exclusiveMaximum, minLength, maxLength, pattern, minItems,
maxItems, uniqueItems, minProperties, maxProperties, allOf, anyOf, oneOf, not,
$ref (локальный и в соседний файл), format (date-time, date, uri), dependentRequired.

  validate.py --schema schema/report.schema.json --file REPORT/frag/007.json
  validate.py --schema schema/event.schema.json  --file REPORT/events/20261122/a-DEV.jsonl
Код возврата: 0 валидно, 1 невалидно, 2 ошибка проверки.
"""
import argparse, json, os, re, sys

TYPES = {"object": dict, "array": list, "string": str, "integer": int,
         "number": (int, float), "boolean": bool, "null": type(None)}
SUPPORTED = set("""type required properties patternProperties additionalProperties items enum const
minimum maximum exclusiveMinimum exclusiveMaximum minLength maxLength pattern minItems maxItems
uniqueItems minProperties maxProperties allOf anyOf oneOf not $ref format dependentRequired
title description $schema $id default examples definitions $comment readOnly writeOnly""".split())
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Validator:
    def __init__(self, root_schema, schema_dir):
        self.root = root_schema
        self.dir = schema_dir
        self.cache = {}

    def deref(self, sch):
        seen = 0
        while isinstance(sch, dict) and "$ref" in sch:
            ref = sch["$ref"]
            seen += 1
            if seen > 20:
                raise ValueError(f"циклический $ref: {ref}")
            file, _, frag = ref.partition("#")
            base = self.root
            if file:
                path = os.path.normpath(os.path.join(self.dir, file))
                if path not in self.cache:
                    self.cache[path] = json.load(open(path, encoding="utf-8"))
                base = self.cache[path]
            for part in [p for p in frag.split("/") if p]:
                part = part.replace("~1", "/").replace("~0", "~")
                base = base[part]
            sch = base
        return sch

    def check(self, val, sch, path, errs):
        sch = self.deref(sch)
        if not isinstance(sch, dict) or not sch:
            return
        if "const" in sch and val != sch["const"]:
            errs.append(f"{path}: ожидалось {sch['const']!r}, получено {val!r}")
        if "enum" in sch and val not in sch["enum"]:
            errs.append(f"{path}: {val!r} не из {sch['enum']}")
        t = sch.get("type")
        if t:
            ts = t if isinstance(t, list) else [t]
            for x in ts:
                if x not in TYPES:
                    raise ValueError(f"неизвестный тип в схеме: {x}")
            ok = any(isinstance(val, TYPES[x]) and not (x in ("integer", "number") and isinstance(val, bool))
                     for x in ts)
            if not ok:
                errs.append(f"{path}: ожидался тип {t}, получен {type(val).__name__}")
                return
        if isinstance(val, bool):
            pass
        elif isinstance(val, (int, float)):
            for k, cmp in (("minimum", lambda a, b: a < b), ("maximum", lambda a, b: a > b),
                           ("exclusiveMinimum", lambda a, b: a <= b), ("exclusiveMaximum", lambda a, b: a >= b)):
                if k in sch and cmp(val, sch[k]):
                    errs.append(f"{path}: {val} нарушает {k}={sch[k]}")
        if isinstance(val, str):
            if "minLength" in sch and len(val) < sch["minLength"]:
                errs.append(f"{path}: длина {len(val)} < minLength {sch['minLength']}")
            if "maxLength" in sch and len(val) > sch["maxLength"]:
                errs.append(f"{path}: длина {len(val)} > maxLength {sch['maxLength']}")
            if "pattern" in sch and not re.search(sch["pattern"], val):
                errs.append(f"{path}: {val!r} не подходит под pattern {sch['pattern']!r}")
            fmt = sch.get("format")
            if fmt == "date-time" and not DATE.match(val):
                errs.append(f"{path}: ожидалось ISO-8601 UTC (2026-11-22T10:00:00Z), получено {val!r}")
            elif fmt == "date" and not DAY.match(val):
                errs.append(f"{path}: ожидалась дата YYYY-MM-DD, получено {val!r}")
            elif fmt == "uri" and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:", val):
                errs.append(f"{path}: ожидался URI, получено {val!r}")
        if isinstance(val, dict):
            for r in sch.get("required", []):
                if r not in val:
                    errs.append(f"{path}: нет обязательного поля {r}")
            for r, deps in (sch.get("dependentRequired") or {}).items():
                if r in val:
                    for d in deps:
                        if d not in val:
                            errs.append(f"{path}: поле {r} требует поле {d}")
            props = sch.get("properties", {})
            pats = sch.get("patternProperties", {})
            add = sch.get("additionalProperties", True)
            if "minProperties" in sch and len(val) < sch["minProperties"]:
                errs.append(f"{path}: полей {len(val)} < minProperties {sch['minProperties']}")
            if "maxProperties" in sch and len(val) > sch["maxProperties"]:
                errs.append(f"{path}: полей {len(val)} > maxProperties {sch['maxProperties']}")
            for k, v in val.items():
                hit = False
                if k in props:
                    self.check(v, props[k], f"{path}.{k}", errs); hit = True
                for p, ps in pats.items():
                    if re.search(p, k):
                        self.check(v, ps, f"{path}.{k}", errs); hit = True
                if not hit:
                    if add is False:
                        errs.append(f"{path}: лишнее поле {k}")
                    elif isinstance(add, dict):
                        self.check(v, add, f"{path}.{k}", errs)
        if isinstance(val, list):
            if "minItems" in sch and len(val) < sch["minItems"]:
                errs.append(f"{path}: элементов {len(val)} < minItems {sch['minItems']}")
            if "maxItems" in sch and len(val) > sch["maxItems"]:
                errs.append(f"{path}: элементов {len(val)} > maxItems {sch['maxItems']}")
            if sch.get("uniqueItems"):
                seen = [json.dumps(x, sort_keys=True, ensure_ascii=False) for x in val]
                if len(set(seen)) != len(seen):
                    errs.append(f"{path}: элементы не уникальны (uniqueItems)")
            items = sch.get("items", {})
            if isinstance(items, list):
                for i, v in enumerate(val):
                    self.check(v, items[i] if i < len(items) else {}, f"{path}[{i}]", errs)
            else:
                for i, v in enumerate(val):
                    self.check(v, items, f"{path}[{i}]", errs)
        for sub in sch.get("allOf", []):
            self.check(val, sub, path, errs)
        if "anyOf" in sch:
            if not any(self.passes(val, s) for s in sch["anyOf"]):
                errs.append(f"{path}: не подходит ни под один вариант anyOf")
        if "oneOf" in sch:
            n = sum(1 for s in sch["oneOf"] if self.passes(val, s))
            if n != 1:
                errs.append(f"{path}: подходит под {n} вариантов oneOf, нужен ровно один")
        if "not" in sch and self.passes(val, sch["not"]):
            errs.append(f"{path}: подходит под запрещённую схему not")

    def passes(self, val, sch):
        sub = []
        self.check(val, sch, "$", sub)
        return not sub


def unknown_keywords(sch, acc):
    """Обход именно узлов схемы: имена свойств ключами схемы не являются."""
    if isinstance(sch, list):
        for v in sch:
            unknown_keywords(v, acc)
        return
    if not isinstance(sch, dict):
        return
    for k, v in sch.items():
        if k not in SUPPORTED and not k.startswith("x-"):
            acc.add(k)
        if k in ("properties", "patternProperties", "definitions", "$defs"):
            for sub in (v or {}).values():
                unknown_keywords(sub, acc)
        elif k in ("items", "additionalProperties", "not", "contains", "if", "then", "else"):
            unknown_keywords(v, acc)
        elif k in ("allOf", "anyOf", "oneOf"):
            for sub in v or []:
                unknown_keywords(sub, acc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--strict-keywords", action="store_true")
    a = ap.parse_args()
    sch = json.load(open(a.schema, encoding="utf-8"))
    txt = open(a.file, encoding="utf-8").read()
    v = Validator(sch, os.path.dirname(os.path.abspath(a.schema)))
    errs = []
    if a.file.endswith(".jsonl"):
        n = 0
        for i, line in enumerate(txt.splitlines(), 1):
            if not line.strip():
                continue
            n += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                errs.append(f"строка {i}: непарсируемый JSON: {e}"); continue
            v.check(obj, sch, f"строка {i}", errs)
        if n == 0:
            errs.append("журнал пуст: ни одной строки")
    else:
        try:
            data = json.loads(txt)
        except json.JSONDecodeError as e:
            print(f"VALIDATE FAIL: непарсируемый JSON: {e}"); return 1
        v.check(data, sch, "$", errs)
    if a.strict_keywords:
        acc = set()
        unknown_keywords(sch, acc)
        if acc:
            errs.append("схема использует неподдерживаемые ключи: " + ", ".join(sorted(acc)))
    if errs:
        print("VALIDATE FAIL:\n  " + "\n  ".join(errs[:20])); return 1
    print(f"VALIDATE OK: {a.file} по {sch.get('title', a.schema)}"); return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"VALIDATE ERROR: {type(e).__name__}: {e}"); sys.exit(2)
