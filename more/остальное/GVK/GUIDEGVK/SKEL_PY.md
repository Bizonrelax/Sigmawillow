---
id: GVK-SKEL-PY
file: SKEL_PY.md
etymology: SKEL_PY = каркас своего стека; грузится только тот, кто работает на этом стеке.
desc: Каркас python: структура пакета, requirements с точными пинами, pyproject.toml, PyInstaller --onedir, workflow python.yml с проверкой переносимости на windows-latest, ловушки Anaconda и PyQt.
name: SKEL_PY — каркас стека
F: каркас
Q: полный
N: [gvk, каркас, ci, python]
O: практический
T: активен, v5.2
---

### SKEL_PY.md — КАРКАС СТЕКА PYTHON

Грузится вместе с SKELETON.md только тем, чей стек — python. Общие правила каркаса и приёмка — SKELETON.md K1, K3, K9; критерии поставки — STACK.md ST1.

K6.0. Бутстрап окружения (C3.1). Выполняется после общей части C3.0, один вызов:

```bash
python
```

K6. Каркас python. Структура: пакет в `src/<имя>/`, точки входа `src/<имя>/__main__.py` и `app.py`, тесты в `tests/`, данные рядом с приложением или в `%LOCALAPPDATA%/<имя>`. Имя пакета — имя репозитория в нижнем регистре, только `[a-z0-9_]`.

`requirements.txt` — пины через `==`, только свободные зависимости. Для математики допустимы numpy, scipy, pandas, sympy, matplotlib. GUI — PySide6 (LGPL) или tkinter из стандартной библиотеки; PyQt в закрытом продукте без платной лицензии запрещён (ST4).

```text
# requirements.txt — пример для расчётной программы с GUI
numpy==2.1.3
scipy==1.14.1
PySide6==6.8.0.2
pytest==8.3.3
pyinstaller==6.11.1
```

`pyproject.toml` — минимальный, без обязательного сетевого индекса при сборке поставки:

```toml
[project]
name = "app"
version = "0.1.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Сборка поставки — только на Windows (K7), команда:

```text
pyinstaller --noconfirm --clean --onedir --windowed --name app ^
  --collect-submodules scipy --hidden-import numpy.core.multiarray ^
  src/app/__main__.py
```

`--onedir` предпочтительнее `--onefile`: быстрее старт, меньше ложных срабатываний антивируса, проще проверка переносимости копированием папки. Рантайм CPython попадает внутрь `dist/app/`. Дополнить `.gitignore`: `dist/`, `build/`, `*.spec` при генерации, `.venv/`, `__pycache__/`, `.pytest_cache/`.

K7. `.github/workflows/python.yml` — сборка и проверка переносимости на Windows.

```yaml
name: python
on:
  push:
    branches: [ main, 'gvk/**' ]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: python -m pytest -q
  package:
    needs: test
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: pyinstaller --noconfirm --clean --onedir --windowed --name app src/app/__main__.py
      - name: переносимость ST1
        shell: pwsh
        run: |
          $p = "C:\Проверка GVK\app"
          New-Item -ItemType Directory -Force -Path $p | Out-Null
          Copy-Item -Recurse -Force dist/app/* $p
          Start-Process -FilePath "$p\app.exe" -ArgumentList "--selftest" -Wait -NoNewWindow
          Copy-Item -Recurse -Force $p "C:\Проверка GVK\app2"
          Start-Process -FilePath "C:\Проверка GVK\app2\app.exe" -ArgumentList "--selftest" -Wait -NoNewWindow
      - uses: actions/upload-artifact@v4
        with:
          name: app-windows
          path: dist/app
```

Приложение обязано поддерживать флаг `--selftest`: быстрый прогон основной логики без GUI, код возврата 0 при успехе. Это делает переносимость проверяемой без ручных кликов. GUI-проверки — отдельные задачи TESTER с `env: windows-ci`.

Ловушки стоимости стека python (ST4). Интерпретатор — CPython с python.org (лицензия PSF, бесплатно); дистрибутив Anaconda `defaults` платен для организаций свыше 200 человек — не использовать, при необходимости conda-forge. PyQt под GPL требует платной лицензии для закрытого продукта — брать PySide6 (LGPL) или tkinter из стандартной библиотеки. Коммерческие сборки numpy с MKL не брать.

Математика и наука (ST5). numpy, scipy, pandas, sympy, matplotlib — свободные лицензии, допустимы. Обязательны: пины `==` в `requirements.txt`, фиксированный `seed` и воспроизводимость вычислений, численные проверки тестами уровня 1, явные `hiddenimports` и `--collect-submodules` для PyInstaller (иначе scipy и numpy теряют подмодули в собранной поставке). Отказ от `.py` в расчётном проекте — дефект, а не решение агента (ST3).
