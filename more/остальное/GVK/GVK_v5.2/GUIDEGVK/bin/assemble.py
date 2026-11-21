#!/usr/bin/env python3
"""GVK assemble: сборка протокола в один самодостаточный md-файл.

Нужно для передачи протокола человеку или нейросети на оценку. Для боевой работы
агентов монолит не используется: он сводит на нет контекстную экономию (G1).

  python3 bin/assemble.py --out ../GVK_v5.1_FULL.md          # всё
  python3 bin/assemble.py --core --out ../GVK_v5.1_CORE.md   # только правила и роли

Содержимое модулей не переписывается: шапка md+ переносится в блок yaml,
заголовки опускаются на два уровня, тела вставляются как есть. Вложенных
тройных ограждений не создаётся.
"""
import argparse, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
G = os.path.dirname(HERE)                     # GUIDEGVK/
ROOT = os.path.dirname(G)                     # корень протокола

CORE = ["PROTOCOL.md", "GUIDEGVK/COMMON.md", "GUIDEGVK/BOOT.md", "GUIDEGVK/PEP.md", "GUIDEGVK/SECURITY.md",
        "GUIDEGVK/FORMATS.md", "GUIDEGVK/FILEMAP.md", "GUIDEGVK/STAGES.md", "GUIDEGVK/STOPFLOW.md",
        "GUIDEGVK/WORK.md", "GUIDEGVK/STACK.md", "GUIDEGVK/LEVERS.md", "GUIDEGVK/ECONOMY.md", "GUIDEGVK/MAP.md"]
ROLES = ["ROLE_FIRST", "ROLE_DEV", "ROLE_REVIEWER", "ROLE_CLEANER", "ROLE_PLANNER_TEST", "ROLE_TESTER",
         "ROLE_COMPLIANCE", "ROLE_CLOSER", "ROLE_TZFIX", "ROLE_WISH", "ROLE_OBSERVER",
         "ROLE_TERMINATOR", "ROLE_TERMINATOR2", "ROLE_FIREFIGHTER"]
CONTOURS = ["GUIDEGVK/QUALITY.md", "GUIDEGVK/RESILIENCE.md", "GUIDEGVK/CONTRACTS.md",
            "GUIDEGVK/SKELETON.md", "GUIDEGVK/SKEL_JAVA.md", "GUIDEGVK/SKEL_PY.md",
            "GUIDEGVK/SKEL_OTHER.md", "GUIDEGVK/README_SPEC.md", "GUIDEGVK/LICENSES.md"]
DATA = (["GUIDEGVK/pep.template.json"]
        + ["GUIDEGVK/schema/" + n for n in sorted(os.listdir(os.path.join(G, "schema"))) if n.endswith(".json")]
        + ["GUIDEGVK/dict/" + n for n in sorted(os.listdir(os.path.join(G, "dict"))) if n.endswith(".md")]
        + ["MANIFEST.json"])
TOOLS = ["GUIDEGVK/bin/" + n for n in ("guard.py", "validate.py", "api.py", "pep.py", "dict.py", "tokens.py",
                                       "doctor.py", "selftest.py", "manifest.py", "assemble.py")]
DOCS = ["CHANGELOG.md", "SELFTEST.md", "GUIDE.md"]
GROUPS = [("A. Ядро и общие правила", CORE),
          ("B. Роли — по одному файлу на роль", ["GUIDEGVK/" + r + ".md" for r in ROLES]),
          ("C. Контуры качества, отказов и перенесённые правила", CONTOURS),
          ("D. Данные: реестр, схемы, манифест", DATA),
          ("E. Инструменты", TOOLS),
          ("F. Документы для человека", DOCS)]


def read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def split_header(text):
    if text.startswith("---\n"):
        end = text.index("\n---", 4)
        return text[4:end].strip(), text[end + 4:].lstrip("\n")
    return None, text


def demote(body):
    """Опустить заголовки на два уровня, не трогая содержимое блоков кода."""
    out, fence = [], False
    for line in body.split("\n"):
        if re.match(r"^`{3,}", line):
            fence = not fence
            out.append(line); continue
        if not fence and re.match(r"^#{1,4} ", line):
            line = "##" + line
        out.append(line)
    return "\n".join(out)


def md_section(n, rel):
    raw = read(rel)
    header, body = split_header(raw)
    s = f"\n\n---\n\n## {n}. `{rel}`\n\n"
    if header:
        s += "Шапка md+ (в репозитории это YAML-шапка файла):\n\n```yaml\n" + header + "\n```\n\n"
    s += demote(body).rstrip() + "\n"
    return s


def code_section(n, rel):
    lang = {".json": "json", ".py": "python"}.get(os.path.splitext(rel)[1], "text")
    return f"\n\n---\n\n## {n}. `{rel}`\n\n```{lang}\n" + read(rel).rstrip() + "\n```\n"


def preamble(core_only, files):
    pep = json.loads(read("GUIDEGVK/pep.template.json"))
    man = json.loads(read("MANIFEST.json"))
    ver = man["version"].replace("GVK-PROTOCOL:", "")
    alv, ppv, tav = man["alv"], man["ppv"], man["tav"]
    tok = sum(man["files"].get(f, {}).get("tokens_est", 0) for f in files)
    total = sum(os.path.getsize(os.path.join(ROOT, f)) for f in files)
    v4 = None
    p = (f"# ПРОТОКОЛ GVK v{alv} — {'ПОЛНАЯ СБОРКА' if not core_only else 'СБОРКА ПРАВИЛ И РОЛЕЙ'} ОДНИМ ФАЙЛОМ\n\n"
         f"Собрано: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. Версия: `{man['version']}`. "
         f"Файлов в сборке: {len(files)}, объём исходников: {total} байт, оценка входа при чтении целиком: ≈{tok} токенов.\n\n"
         "**Назначение этого файла.** Оценка протокола человеком или нейросетью. В репозитории протокол модульный: "
         "шлюз `PROTOCOL.md`, общее ядро, по одному файлу на роль, схемы, словари и инструменты. Агент грузит только шлюз, "
         "ядро, свой файл роли, модули из `needs` и карточку роли — читать эту сборку целиком агенту запрещено (G1, E1). "
         f"Монолит существует для оценки: {tok} токенов против 13–30k входа одной роли.\n\n"
         "**Как читать.** Раздел 0 — карта сборки и маршрутизация ролей. Далее группы A–F: ядро, роли, контуры, данные, "
         "инструменты, документы для человека. Нумерация пунктов внутри модулей стабильна: C — общее ядро, W — рабочий цикл, "
         "S — безопасность, F — форматы, L — рычаги, P — реестр ролей, G — шлюз, E — экономия и учёт токенов, "
         "K/D/A — каркас, README, лицензии. Ссылки между модулями разрешаются по имени файла.\n\n"
         "**Что оценивать в первую очередь.** Атомарность захватов и отсутствие гонок (ROLE_DEV 5, ROLE_CLEANER 3, S5), "
         "порядок развилки и отличие релиза от закрытия (C7, C10.22), права ролей и их программную проверку "
         "(S1–S3, `guard.py`: нормализация путей, владение пакетом, ветки, срок гранта, отказ при сомнении), "
         "привязку проверки к ревизии ТЗ (C8), защиту от циклов (C10.1–C10.4, L5), контракты и валидацию (CT, `schema/`), "
         "словари и честность учёта расхода (E3–E10, `dict.py`, `tokens.py`), критерии приёмки (Q7, ROLE_CLOSER), "
         "границы честности отчётов (G6, W13, C10.11, C10.19).\n\n"
         f"**Проверено.** Золотой случай: `bin/selftest.py` — механика протокола на локальном стенде без сети. "
         f"Статический аудит поставки: `bin/doctor.py`. Числа и список найденных дефектов — в `SELFTEST.md` и `CHANGELOG.md`. "
         f"Версия контрактов инструментов: TAV-{tav}.\n\n")
    if core_only:
        p += "Этот вариант — только правила и роли (группы A–C). Схемы, инструменты, руководство владельца и отчёты в него не включены.\n\n"
    p += "## 0. Карта сборки\n\n| № | Файл | Байт |\n| --- | --- | --- |\n"
    n = 0
    for title, group in GROUPS:
        if core_only and title[0] in "DEF":
            continue
        for rel in group:
            n += 1
            p += f"| {n} | `{rel}` | {os.path.getsize(os.path.join(ROOT, rel))} |\n"
    p += "\n### 0.1. Маршрутизация ролей: что грузит агент\n\n| Роль | Файл роли | Обязательные модули (`needs`) | По факту (`lazy`) |\n| --- | --- | --- | --- |\n"
    for r, v in pep["roles"].items():
        p += f"| {r} | `{os.path.basename(v['file'])}` | {', '.join(v['needs']) or '—'} | {', '.join(v.get('lazy', [])) or '—'} |\n"
    p += ("\nПорядок развилки: " + " → ".join(pep["priority"]) + ". Роли по рычагу: " + ", ".join(pep["lever_roles"]) + ".\n")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--core", action="store_true")
    a = ap.parse_args()
    files, parts, n = [], [], 0
    for title, group in GROUPS:
        if a.core and title[0] in "DEF":
            continue
        parts.append(f"\n\n---\n\n# ГРУППА {title}\n")
        for rel in group:
            n += 1
            files.append(rel)
            parts.append(md_section(n, rel) if rel.endswith(".md") else code_section(n, rel))
    doc = preamble(a.core, files) + "".join(parts)
    doc += ("\n\n---\n\n# КОНЕЦ СБОРКИ\n\n"
            f"Файлов: {len(files)}. Сборка не изменяет содержимое модулей: изменены только уровни заголовков "
            "и представление YAML-шапок. Целостность исходников проверяется по `MANIFEST.json` (sha256).\n")
    out = os.path.abspath(a.out)
    open(out, "w", encoding="utf-8").write(doc)
    # самопроверка: все ограждения тройные, парные, вложений нет; содержимое совпадает с исходниками
    fences = [l for l in doc.split("\n") if re.match(r"^`{3,}", l)]
    longer = [l for l in fences if not l.startswith("```") or l.strip("`").strip() and len(l) - len(l.lstrip("`")) > 3]
    nested, inside = 0, False
    for l in doc.split("\n"):
        if re.match(r"^`{3,}", l):
            if inside and len(l) - len(l.lstrip("`")) > 3:
                nested += 1
            inside = not inside
    drift = []
    for rel in files:
        raw = read(rel)
        if rel.endswith(".md"):
            _, body = split_header(raw)
            if demote(body).rstrip() not in doc:
                drift.append(rel)
        elif raw.rstrip() not in doc:
            drift.append(rel)
    ok = len(fences) % 2 == 0 and not longer and not nested and not drift and not inside
    sys.path.insert(0, HERE)
    from tokens import est_text
    print(f"СОБРАНО: {out}\n  файлов {len(files)}, {len(doc.encode())} байт, ≈{est_text(doc)} токенов (оценка gvk-bytes/1)")
    print(f"  ограждений {len(fences)} ({'парно' if len(fences)%2==0 else 'НЕПАРНО'}), вложений {nested}, длинных маркеров {len(longer)}")
    print(f"  обратная сверка с исходниками: {'все тела совпали' if not drift else 'РАСХОЖДЕНИЯ: ' + ', '.join(drift)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
