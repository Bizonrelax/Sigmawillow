---
id: GVK-FILEMAP
file: FILEMAP.md
etymology: GVK-FILEMAP = модуль протокола GVK v5.
desc: Полные таблицы файлов состояния GVK/ и контрактов REPORT/, схемы, адаптер совместимости с v4.3.
name: Карта файлов GVK
F: справочник
Q: полный
N: [gvk]
O: практический
T: активен, v5.0
---

# FILEMAP.md — КАРТА ФАЙЛОВ (F3–F5)

Грузится FIRST, CLOSER, FIREFIGHTER и любой ролью при записи незнакомых артефактов или при работе с репозиторием v4.3. Обычному циклу достаточно F1, F2, F6, F7 в `FORMATS.md`.

F3. Файлы `GVK/`.

| Файл | Где | Тело |
| --- | --- | --- |
| `PEP.json` | main | реестр ролей по PEP.md, единственный JSON в `GVK/` |
| `PLAN.md` | gvk-plan | № \| этап \| пакеты \| задачи ТЗ \| наследие \| готовность (команда) \| оценка ч \| TCP-порт \| ci |
| `PORTS.md` | gvk-plan | порт \| сигнатура \| владелец № \| зависимые № |
| `LINKS.md` | gvk-plan | рёбра №A → порт → №B; ниже порядок слияния, включая ветки прошлых этапов |
| `AUDIT.md` | gvk-plan, дописывается | файл \| вердикт \| обоснование \| доказательство |
| `REQUESTS.md` | main | заявка \| порт \| от № \| к № \| статус |
| `STATE.md` | main | шапка: этап, ревизия ТЗ, СТОП; таблица: № \| статус \| владелец \| epoch \| аренда до \| ветка \| последний зелёный \| этап \| tz_sha8 |
| `LIMITS.md` | main | cycles_max, attempts_max, stopfix_max, set_by, set_at |
| `STAGES.md` | main, дописывается | ревизия \| этап \| tz_path \| tz_sha \| версия ТЗ \| дата \| основание \| автор |
| `STOP.md` | main, атомарно | reason, author, created_at, lease_until, stage, tz_path, tz_sha, requirement, evidence, why, suggestion |
| `stopfix.md` | main, атомарно | owner, stop_sha, lease_until (4 ч) |
| `ACCESS.md` | main, атомарно | grantee, glob, mode, granted_by, granted_at, expires_at, reason (S7) |
| `claims/NNN.md` | main, атомарно | owner, epoch, lease_until, packages, branch, attempts, stage, tz_sha |
| `fixes/NNN.md` | main, атомарно | owner, finding_id, base_sha, tz_sha, lease_until |
| `roles/<ROLE>.md` | main, атомарно | owner, role, lease_until, target, lever, stage |
| `births/<метка>-<owner>.md` | main, не изменяется | owner, role, fragment, epoch, repo, branch, protocol_ver, pep_ver, model, lever, stage, born_at |
| `releases/<метка>-<owner>.md` | main, не изменяется | cause, author, дата, список № \| epoch \| last_green \| что осталось |
| `CHANGE-NNN.md` | main | cause (wish/stopfix/terminator), было → стало, затронутые фрагменты и порты, оценка, вердикт выполнимости |
| `DICT.md` | main | словарь ГВК-Э, только при включённом рычаге |
| `FINAL.md` | main | этапы и ревизии, слитые ветки, числа тестов, релиз, удалённый мусор, невыполненные пункты ТЗ |

Статусы фрагмента: `свободен`, `в работе`, `готов`, `провален`, `blocked`, `наследие`.

F4. Файлы `REPORT/` и их схемы.

| Файл | Схема | Содержание |
| --- | --- | --- |
| `REPORT/frag/NNN.json` | `report` | отчёт фрагмента: статус, ветка, last_green, тесты, attempts, cycles, stage, tz_sha, remaining |
| `REPORT/ckpt/NNN.json` | `checkpoint` | последний зелёный чек-поинт: sha, step, тесты, время |
| `REPORT/review/NNN-<hash8>.json` | `review` | вердикт ПРИНЯТО/ВЕРНУТЬ, checked_sha, reviewer, tz_sha, stage, remarks |
| `REPORT/finding/NNN-<hash8>.json` | `finding` | дефекты: файл, строка, симптом, требование ТЗ, severity, status open/closed, fixed_sha |
| `REPORT/test/PLAN.json` | `test_plan` | план тестирования: покрытие требований ТЗ, список задач, критерии приёмки |
| `REPORT/test/T-<id>.json` | `test_task` | одна задача одному тестировщику: вид (gui/uiux/logic/absurd), шаги, ожидание, данные, среда |
| `REPORT/test/R-<id>.json` | `test_result` | результат: pass/fail/blocked, факты, артефакты, ссылки на дефекты |
| `REPORT/test/claims/T-<id>.json` | `test_claim` | захват задачи тестировщиком: owner, lease_until |
| `REPORT/COMPLIANCE.json` | `compliance` | зависимости и заимствования, лицензии SPDX, конфликты, вердикт |
| `REPORT/FINAL.json` | `final_report` | итог: требования → статус → доказательство, тесты, релиз, остатки |
| `REPORT/events/<YYYYMMDD>.jsonl` | `event` | журнал событий (S5), только дописывание |

Каждый JSON содержит `schema`, `schema_ver`, `at`, `owner`, `protocol_ver`. Валидация до записи обязательна (C12.4). Схемы лежат в `GUIDEGVK/schema/`, контракты и примеры — в `GUIDEGVK/CONTRACTS.md`.

F5. Адаптер совместимости с v4.3. Репозиторий, начатый по v4.3, не переделывается: старые файлы читаются, новые пишутся по-новому.

| v4.3 | v5 | Правило |
| --- | --- | --- |
| `GVK/reports/NNN.md` | `REPORT/frag/NNN.json` | читать оба, при наличии обоих авторитетен JSON; md не удалять |
| `GVK/reviews/NNN.md` | `REPORT/review/NNN-<hash8>.json` | `checked_sha` из md считается проверенным хэшем |
| `GVK/findings/NNN-hash8.md` | `REPORT/finding/NNN-<hash8>.json` | `status: open` в md так же блокирует закрытие |
| нет `PEP.json` | создать по P7 | каталог из шаблона, занятость из захватов |
| нет `stage`/`tz_sha` в записи | этап 1, ревизия 1 | пин = первая строка `STAGES.md` |
| `GVK/roles/` отсутствует | создать при первом захвате роли-одиночки | каталог создаётся вместе с файлом |

