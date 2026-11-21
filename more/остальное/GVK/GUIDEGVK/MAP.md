---
id: GVK-MAP
file: MAP.md
etymology: MAP = карта модулей протокола: что грузить по какому факту.
desc: Какой модуль протокола нужен для какого факта; вынесено из шлюза, чтобы не платить за карту в каждой сессии.
name: Карта модулей протокола GVK
F: справочник
Q: полный
N: [gvk, маршрутизация, экономия]
O: практический
T: активен, v5.2
---

### MAP.md — КАРТА МОДУЛЕЙ ПРОТОКОЛА

Грузится по факту: нужен модуль, а в `needs` его нет и в `lazy` не obvious. Основной источник маршрутизации — карточка роли (`needs`, `lazy`), эта карта — справочник для спорных случаев.


| Файл | Кто грузит |
| --- | --- |
| `GUIDEGVK/COMMON.md` | все роли: полномочия, среда, развилка, стоп, запреты, отчёт |
| `GUIDEGVK/PEP.md`, `pep.template.json` | FIRST, а также любой при расхождении реестра |
| `GUIDEGVK/SECURITY.md` | все роли при первой записи; полностью — FIRST, CLOSER, COMPLIANCE |
| `GUIDEGVK/FORMATS.md` | при первой записи в `GVK/` или `REPORT/` |
| `GUIDEGVK/FILEMAP.md` | FIRST, CLOSER, FIREFIGHTER; незнакомые артефакты; репозиторий v4.3 |
| `GUIDEGVK/STAGES.md` | создание и правка ревизий: FIRST, WISH, TZFIX, TERMINATOR; спорный пин |
| `GUIDEGVK/STOPFLOW.md` | когда `STOP.md` действительно есть; роли, ставящие или лечащие стоп |
| `GUIDEGVK/LEVERS.md` | только при рычаге или «продолжай» |
| `GUIDEGVK/WORK.md` | роли, пишущие код: DEV, CLEANER, FIRST, CLOSER, FIREFIGHTER |
| `GUIDEGVK/STACK.md` | FIRST при выборе стека, CLOSER при приёмке; остальные — упаковка, наследие, смена стека |
| `GUIDEGVK/SKELETON.md`, `SKEL_*.md` | FIRST, CLOSER; только файл своего стека |
| `GUIDEGVK/README_SPEC.md`, `LICENSES.md` | роли, меняющие поведение или заимствования; CLOSER, COMPLIANCE |
| `GUIDEGVK/ECONOMY.md` | по факту: сжатие служебных полей, учёт токенов, превышение бюджета, рычаги `ГВК-Э` и `РАСХОД` |
| `GUIDEGVK/dict/*.dict.md` | не грузить в контекст: словарь живёт в `bin/dict.py` (E4) |
| `GUIDEGVK/ROLE_*.md` | своя роль, один файл |
| `GUIDEGVK/CONTRACTS.md`, `schema/*.json` | при записи или чтении структурированного артефакта |
| `GUIDEGVK/QUALITY.md` | PLANNER_TEST, TESTER, CLOSER |
| `GUIDEGVK/RESILIENCE.md` | при повторяющихся отказах; FIRST, CLOSER, TERMINATOR, FIREFIGHTER |
| `GUIDEGVK/bin/` | `pep.py` карточка роли, `api.py` операции и срез, `guard.py` права, `validate.py` схемы, `dict.py` сжатие, `tokens.py` учёт, `doctor.py` самопроверка поставки, `selftest.py` золотой случай, `manifest.py` и `assemble.py` для владельца |
| `GUIDE.md` | только человек |
