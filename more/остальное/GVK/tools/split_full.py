#!/usr/bin/env python3
"""Разбирает монолит GVK_v5.1_FULL.md обратно в модульные файлы (для аудита)."""
import os, re, sys

src = sys.argv[1] if len(sys.argv) > 1 else "uploads/GVK_v5.1_FULL.md"
dst = sys.argv[2] if len(sys.argv) > 2 else "work/v51"
text = open(src, encoding="utf-8").read()
lines = text.split("\n")

heads = []
for i, ln in enumerate(lines):
    m = re.match(r"^## (\d+)\. `([^`]+)`\s*$", ln)
    if m:
        heads.append((i, int(m.group(1)), m.group(2)))

os.makedirs(dst, exist_ok=True)
report = []
for k, (i, num, path) in enumerate(heads):
    end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
    body = lines[i + 1:end]
    # убрать хвостовые разделители
    while body and body[-1].strip() in ("", "---") or (body and body[-1].startswith("# ГРУППА")) or (body and body[-1].startswith("# КОНЕЦ")):
        body.pop()
    while body and not body[0].strip():
        body.pop(0)
    out = "\n".join(body)
    ext = os.path.splitext(path)[1]
    if ext in (".py", ".json"):
        m = re.match(r"^```[a-z]*\n(.*)\n```$", out, re.S)
        if not m:
            print("!! не найден единый блок кода:", path); continue
        content = m.group(1) + "\n"
    else:
        # md: превратить блок шапки в YAML frontmatter
        m = re.match(r"^Шапка md\+ \(в репозитории это YAML-шапка файла\):\n\n```yaml\n(.*?)\n```\n", out, re.S)
        if m:
            content = "---\n" + m.group(1) + "\n---\n" + out[m.end():]
        else:
            print("!! нет шапки:", path)
            content = out
        content = content.rstrip() + "\n"
    fp = os.path.join(dst, path)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    open(fp, "w", encoding="utf-8").write(content)
    report.append((path, len(content.encode("utf-8"))))

print("files:", len(report))
for p, n in report:
    print(f"{n:7d}  {p}")
