---
id: GVK-CONTRACTS
file: CONTRACTS.md
etymology: CONTRACTS = контракты межагентского обмена GVK.
desc: Каталог схем, общие поля, правила валидации, примеры артефактов, версионирование контрактов и запреты свободного текста.
name: Контракты GVK
F: спецификация
Q: полный
N: [gvk, json, контракты]
O: практический
T: активен, v5.2
---

### CONTRACTS.md — КОНТРАКТЫ МЕЖДУ АГЕНТАМИ

Грузится ролью, которая записывает или читает структурированный артефакт: PLANNER_TEST, TESTER, COMPLIANCE, CLOSER, REVIEWER, DEV. Схемы лежат в `GUIDEGVK/schema/`, они машинные и короткие.

CT1. Принцип. Агенты обмениваются не пересказом, а полями. Отчёт, вердикт, дефект, задача тестирования, результат, комплаенс и итог — JSON по схеме. Это убирает разночтения и «поломку аргументов», когда следующий агент получает не то, что ожидал. Проза допустима только внутри строковых полей, предназначенных для человека (`remaining`, `symptom`, `remarks`).

CT2. Общие поля каждого артефакта: `schema` (например `gvk/report/1`), `schema_ver`, `at` (ISO-8601 UTC из заголовка `Date` GitHub), `owner`, `protocol_ver` (композитная версия G7). Артефакты, привязанные к ТЗ, дополнительно несут `stage` и `tz_sha`. Артефакты, привязанные к коду, — `checked_sha` или `last_green`. Необязательные поля лучше опускать, чем писать со значением `null`: пустое поле и отсутствующее поле читаются одинаково, а лишние символы жгут квоту.

CT3. Каталог.

| Схема | Артефакт | Кто пишет | Кто читает |
| --- | --- | --- | --- |
| `pep` | `GVK/PEP.json` | FIRST, снимки — все роли | все роли на входе |
| `report` | `REPORT/frag/NNN.json` | DEV, CLEANER | REVIEWER, PLANNER_TEST, TERMINATOR, CLOSER |
| `checkpoint` | `REPORT/ckpt/NNN.json` | DEV, CLEANER | DEV при возобновлении, TERMINATOR |
| `review` | `REPORT/review/NNN-<hash8>.json` | REVIEWER | CLEANER, CLOSER, TERMINATOR |
| `finding` | `REPORT/finding/NNN-<hash8>.json` | REVIEWER, TESTER, COMPLIANCE | CLEANER, CLOSER |
| `test_plan` | `REPORT/test/PLAN.json` | PLANNER_TEST | TESTER, CLOSER |
| `test_task` | `REPORT/test/T-<id>.json` | PLANNER_TEST | TESTER |
| `test_claim` | `REPORT/test/claims/T-<id>.json` | TESTER | TESTER, TERMINATOR2 |
| `test_result` | `REPORT/test/R-<id>.json` | TESTER | PLANNER_TEST, CLOSER, CLEANER |
| `compliance` | `REPORT/COMPLIANCE.json` | COMPLIANCE | CLOSER |
| `final_report` | `REPORT/FINAL.json` | CLOSER | владелец, следующий этап |
| `event` | `REPORT/events/<дата>/<owner>-<ROLE>-<время>.jsonl` | все роли | разбор инцидентов |
| `tokens` | `REPORT/tokens/<дата>/<owner>-<ROLE>-<время>.json` | все роли | расход токенов сессии (E7) |
| `tokens_total` | `REPORT/tokens/TOTAL.json` | OBSERVER, CLOSER | сводка расхода по проекту |
| `stack` | `REPORT/stack.json` | FIRST, DEV | шесть критериев переносимости ST1 |

CT4. Валидация до записи.

```bash
python3 /opt/gvk/p/GUIDEGVK/bin/validate.py \
  --schema /opt/gvk/p/GUIDEGVK/schema/report.schema.json --file /tmp/007.json
```

Код возврата 0 — писать можно, 1 — исправить поля по тексту ошибок и проверить снова (не более двух попыток), 2 — ошибка проверки, считается запретом. Журналы `.jsonl` проверяются построчно (в v5.1 валидатор падал на них всегда). После записи — обратное чтение (C12.5). Валидатор работает без внешних зависимостей и понимает `pattern`, `format: date-time`, `anyOf/oneOf/allOf`, `$ref`, `uniqueItems`, `dependentRequired`; если в среде есть `jsonschema`, допустимо проверить им, результат тот же. `bin/api.py --schema <имя>` вызывает валидатор сам до записи.

CT5. Примеры.

Отчёт фрагмента:

```json
{"schema":"gvk/report/1","schema_ver":"1","fragment":"007","stage":1,"tz_sha":"a1b2c3d","owner":"gvk-qwen-7","role":"DEV","branch":"gvk/007","last_green":"dc5733f","status":"ЗЕЛЕНО","tests":{"passed":42,"failed":0,"skipped":1},"attempts":1,"cycles":0,"remaining":["экспорт в CSV не покрыт"],"at":"2026-11-16T09:12:03Z","protocol_ver":"ALV-5.1_PPV-5.1_MRV-qwen3-coder_TAV-1.1"}
```

Задача тестировщику:

```json
{"schema":"gvk/test_task/1","schema_ver":"1","id":"T-004","kind":"uiux","title":"Читаемость главного окна при максимуме","requirement_ref":"ТЗ 3.2","fragment":"005","level":2,"env":"windows-ci","preconditions":["сборка app-image из CI"],"steps":[{"do":"развернуть окно на максимум","expect":"все элементы видимы, текст не обрезан"},{"do":"переключить локаль на RU","expect":"подписи помещаются, кнопки не наезжают"}],"data":null,"seed":null,"expected":"ни одного обрезанного или невидимого элемента","acceptance":"скриншоты EN и RU приложены, расхождений нет","artifacts":["shot-en.png","shot-ru.png"],"severity_if_fail":"важно","deps":[],"est_min":25,"stage":1,"tz_sha":"a1b2c3d","at":"2026-11-16T09:20:00Z","owner":"gvk-qwen-3","protocol_ver":"ALV-5.1_PPV-5.1_MRV-qwen3-coder_TAV-1.1"}
```

Результат теста:

```json
{"schema":"gvk/test_result/1","schema_ver":"1","task":"T-004","verdict":"fail","env_used":"windows-ci","checked_sha":"dc5733f","branch":"gvk/test-T-004","steps":[{"step":"развернуть окно","expect":"все элементы видимы","fact":"кнопка Экспорт обрезана на 12 px","status":"fail"}],"artifacts":["shot-ru.png"],"defects":["F-005-dc5733f"],"judge":[{"criterion":"читаемость","score":3,"why":"подписи читаемы, но обрезка кнопки"}],"manual_notes":"","stage":1,"tz_sha":"a1b2c3d","at":"2026-11-16T10:02:00Z","owner":"gvk-qwen-9","protocol_ver":"ALV-5.1_PPV-5.1_MRV-qwen3-coder_TAV-1.1"}
```

CT6. Версионирование контрактов. Несовместимое изменение полей поднимает `TAV` (v5.2 → TAV-1.2) и `schema_ver`, требует правила чтения старых артефактов в F5 и упоминания в `CHANGELOG.md`. Добавление необязательного поля — совместимо, версия схемы не меняется. Удалять или переименовывать поле без правила миграции запрещено: в репозитории лежат артефакты прошлых этапов.

CT7. Запреты. Свободный текст вместо полей схемы. JSON внутри md-файла вместо отдельного артефакта. Дублирование одного поля в `GVK/` и `REPORT/` (правило одного места, F1). Запись без валидации. Отчёт об успехе без обратного чтения. Чтение всего каталога `REPORT/` вместо нужных файлов. Токен, секреты и персональные данные в артефактах.

CT8. Как читать чужой артефакт. Сначала список имён каталога одним вызовом, затем только нужные файлы. Из отчёта фрагмента нужны `status`, `last_green`, `tz_sha`, `remaining`; из вердикта — `verdict` и `checked_sha`; из дефекта — `status`, `severity`, `defects`; из результата теста — `verdict` и `defects`. Остальное читать по необходимости, а не «на всякий случай».

CT9. Словарь в строковых полях. Служебные строковые поля (`remaining`, `remarks`, `symptom`, `manual_notes`, `why`, `note`, `detail`, `proof`) могут содержать словарные коды `%g3`, `%k1`, `%d2` — это разрешённое сжатие (E5). Ключи, enum, идентификаторы, пути, хэши, время и числа сжатию не подлежат никогда. Сжимает и раскрывает `bin/dict.py`, словарь в контекст не грузится. Проверка — `dict.py lint`: код в запрещённой зоне или неизвестный код — ошибка, артефакт не записывать.
