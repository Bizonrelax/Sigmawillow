---
id: GVK-FILEMAP
file: FILEMAP.md
etymology: FILEMAP = карта файлов целевого репозитория: что где лежит, кто пишет, по какой схеме.
desc: Полные таблицы GVK/ и REPORT/, соответствие схем, дерево проекта по стеку, адаптер совместимости с v4.3, команды проверки размещения.
name: Карта файлов GVK
F: спецификация
Q: полный
N: [gvk, карта, состояние, схемы]
O: практический
T: активен, v5.2
---

### FILEMAP.md — КАРТА ФАЙЛОВ ЦЕЛЕВОГО РЕПОЗИТОРИЯ

Грузится при записи незнакомого артефакта, при разборе наследия v4.3 и при уборке. Правило одного места — F1: поле живёт либо в `GVK/`, либо в `REPORT/`. Шапка md+ — F2. Правила атомарной записи — F6.

FM1. Каталог `GVK/` — операционное состояние. Все `*.md` с шапкой md+, кроме `PEP.json`.

| Путь | Кто создаёт и меняет | Содержимое | Живёт |
| --- | --- | --- | --- |
| `GVK/PLAN.md` | FIRST; правят WISH, TZFIX, TERMINATOR | фрагменты: номер, этап, пакеты, задачи ТЗ, наследие, критерий готовности командой, оценка часов, порт, `ci: windows`, поле `стек` | до закрытия, копия в main только для чтения |
| `GVK/AUDIT.md` | FIRST, FIREFIGHTER | опись наследия с вердиктами KEEP/REFACTOR/REWRITE/DELETE и доказательствами; решение о стеке (ST2) | весь проект |
| `GVK/PORTS.md` | FIRST; WISH при изменении | публичные сущности: имя, сигнатура, владелец-фрагмент, зависимые | весь проект |
| `GVK/LINKS.md` | FIRST; WISH | рёбра «фрагмент → порт → фрагмент», порядок слияния | весь проект |
| `GVK/REQUESTS.md` | DEV, CLEANER | заявки на изменение чужого порта или каркаса | до закрытия |
| `GVK/LIMITS.md` | FIRST; рычаг `ПОТОЛОК` | потолки попыток, циклов, часов | весь проект |
| `GVK/STAGES.md` | FIRST; WISH, TZFIX, TERMINATOR | ревизии: ревизия, этап, `tz_path`, `tz_sha`, версия ТЗ, дата, основание, автор | весь проект, только дописывание |
| `GVK/STATE.md` | любой владелец захвата, CLOSER | производная сводка для человека | до закрытия |
| `GVK/claims/NNN.md` | DEV, FIRST для 000 | захват фрагмента: `owner, role, lease_until, stage, tz_sha, branch, epoch, attempts` | до освобождения |
| `GVK/fixes/NNN.md` | CLEANER | захват исправления: то же плюс `finding` | до освобождения |
| `GVK/roles/<ROLE>.md` | роли-одиночки | аренда роли: `owner, role, lease_until, target, stage` | до освобождения |
| `GVK/STOP.md` | любой, кто доказал невыполнимость | общий стоп: `reason` (infeasible/replan/owner), доказательство, предложение правки | до снятия TZFIX или владельцем |
| `GVK/stopfix.md` | TZFIX | захват лечения стопа | до освобождения |
| `GVK/ACCESS.md` | владелец рычагом `ДОСТУП` | временно снятый запрет, срок, основание | до истечения срока, затем удаляется |
| `GVK/PEP.json` | FIRST; снимок занятости — сама роль | каталог ролей, права, `needs`/`lazy`, `stack`, версии, дефицит | весь проект |
| `GVK/births/<метка>-<owner>.md` | каждый агент при рождении | роль, версия протокола, время GitHub, цель | не удаляется |
| `GVK/releases/<метка>-<owner>.md` | TERMINATOR2, любой при массовом освобождении | что освобождено, почему, список захватов | не удаляется |
| `GVK/CHANGE-NNN.md` | WISH, TZFIX, TERMINATOR | изменение ТЗ или плана: основание, дифф по смыслу, влияние на фрагменты | не удаляется |
| `GVK/DICT.md` | FIRST, рычаг `ГВК-Э`/`СЛОВАРЬ ОБНОВИ` | словарь проекта: коды `%jN` → фразы домена (E3) | весь проект |
| `GVK/FINAL.md` | CLOSER | итог: `mode: close\|release`, этапы, слитые ветки, числа тестов, уборка, невыполненное с причиной | навсегда; новых агентов останавливает только `mode: close` |
| `GVK_PROTOCOL/` (или `more/GVK/`) | владелец | сам протокол, если лежит в целевом репозитории: только чтение для агентов (`@protocol`) | весь проект |

FM2. Каталог `REPORT/` — машинные контракты. JSON без шапки md+, с полями `schema` и `schema_ver`. Валидация по схеме до записи обязательна (C12.4).

| Путь | Схема в `GUIDEGVK/schema/` | Кто пишет | Смысл |
| --- | --- | --- | --- |
| `REPORT/frag/NNN.json` | `report` | DEV, CLEANER, FIRST | итог фрагмента: статус, тесты, попытки, циклы, остаток |
| `REPORT/review/NNN-<hash8>.json` | `review` | REVIEWER | вердикт по конкретному хэшу: проверка, зелёность, замечания |
| `REPORT/finding/NNN-<hash8>.json` | `finding` | REVIEWER, TESTER, COMPLIANCE | дефект: важность, воспроизведение, требование, статус |
| `REPORT/ckpt/NNN.json` | `checkpoint` | DEV, CLEANER | чек-поинт незавершённой работы: что готово, следующий шаг |
| `REPORT/test/PLAN.json` | `test_plan` | PLANNER_TEST | план тестирования: виды, покрытие требований, задачи |
| `REPORT/test/T-<id>.json` | `test_task` | PLANNER_TEST | одна задача: шаги, ожидания, среда, критерий приёмки |
| `REPORT/test/claims/T-<id>.json` | `test_claim` | TESTER | атомарный захват задачи |
| `REPORT/test/R-<id>.json` | `test_result` | TESTER | результат: факты по шагам, артефакты, дефекты |
| `REPORT/COMPLIANCE.json` | `compliance` | COMPLIANCE | заимствования, лицензии зависимостей, блокирующие флаги |
| `REPORT/stack.json` | `stack` | FIRST, DEV; проверяет CLOSER | стек и шесть фактов переносимости ST1 |
| `REPORT/FINAL.json` | `final_report` | CLOSER | машинный итог закрытия или релиза |
| `REPORT/events/<YYYYMMDD>/<owner>-<ROLE>-<HHMMSS>.jsonl` | `event` (построчно) | все роли | журнал сессии, только дописывание, чужих строк нет |
| `REPORT/events/<YYYYMMDD>.jsonl` | `event` (построчно) | наследие v4.3–v5.1 | читается как есть; дописывание — `api.py append` |
| `REPORT/tokens/<YYYYMMDD>/<owner>-<ROLE>-<HHMMSS>.json` | `tokens` | все роли, включая OBSERVER | расход токенов сессии: точный или оценённый (E7) |
| `REPORT/tokens/TOTAL.json` | `tokens_total` | OBSERVER, CLOSER | производная сводка расхода, допускается расхождение |

FM3. Дерево проекта. Каркас — по стеку (SKELETON.md K1 и файл своего стека), состав вне каркаса одинаков:

```text
README.md            EN, поведение и установка (README_SPEC.md)
README_RU.md         RU, то же содержание
CHANGELOG.md         история версий, ведёт CLOSER
THIRD-PARTY-NOTICES.md  реестр заимствований (LICENSES.md)
licenses/            полные тексты лицензий
docs/TZ.md           ТЗ владельца, путь фиксируется в STAGES.md
src/                 код: java — src/main и src/test; python — пакет src/<имя> и tests/
tests/               тесты python и прочих стеков
.github/workflows/   CI своего стека, job упаковки на windows-latest
GVK/  REPORT/        состояние и контракты (FM1, FM2), REPORT/tokens/ — расход
GVK_PROTOCOL/        протокол, если лежит в целевом репозитории (только чтение)
```

Артефакты сборки (`target/`, `dist/`, `build/`, `*.exe`, `*.zip`, `__pycache__/`, `.venv/`) в git не коммитятся: они живут в артефактах CI и Releases. Данные приложения — рядом с ним или в `%LOCALAPPDATA%/<имя>`, переносятся копированием (ST1).

FM4. Кто чего не трогает. Код чужого пакета, файлы каркаса своего стека, `PLAN.md` и ТЗ — вне прав роли (W7, S3, guard). Проверка границ программная, до действия. Исключения: CLEANER в пакете своего fix-захвата, CLOSER на время закрытия, FIREFIGHTER в ветке `gvk/fire`.

FM5. Адаптер совместимости с v4.3 (F5). Репозиторий, где работа уже шла, ничего не теряет.

| Наследие v4.3 | Как читать | Что писать дальше |
| --- | --- | --- |
| `GVK/reports/NNN.md` | как отчёт фрагмента: статус, тесты, остаток | `REPORT/frag/NNN.json` |
| `GVK/reviews/NNN-*.md` | как вердикт по хэшу | `REPORT/review/NNN-<hash8>.json` |
| `GVK/findings/*.md` | как дефект, важность из текста | `REPORT/finding/NNN-<hash8>.json` |
| `GVK/claims`, `fixes`, `roles`, `STOP.md`, `LIMITS.md`, `STAGES.md` | без изменений, формат тот же | так же |
| отсутствие `PEP.json` | каталог не создан | создаёт FIRST или любой агент по P7 |
| отсутствие `STAGES.md` | ревизий не было | первая ревизия по C8 |

Принятое и зелёное не переделывается, ветки и пины версий сохраняются, старые файлы не удаляются: они история. Дублировать одно и то же поле в md и JSON запрещено (F1) — при переносе старое поле помечается «перенесено в REPORT/…».

FM6. Команды проверки размещения и слияния:

```bash
# маркеры каркаса берутся из stack.skeleton карточки роли, а не из java-привычки
git ls-tree -r --name-only origin/main | grep -cE 'pom.xml|build.gradle|pyproject.toml|requirements.txt|\.csproj|go.mod|Cargo.toml|package.json|CMakeLists.txt|^(src|app|lib|cmd|internal|pkg)/'
git ls-tree -r --name-only origin/main | grep -E '^(GVK|REPORT)/' | head -40
git ls-tree -r --name-only origin/main | grep -E '\.(exe|zip|jar|class)$' || echo "артефактов нет"
```

Первая команда — факт появления каркаса после слияния 000 (ноль означает, что слияния не было). Вторая — что состояние на месте. Третья — что мусор не закоммичен. Расхождение `STATE.md` с захватами дефектом не является: истина в захватах (C6).
