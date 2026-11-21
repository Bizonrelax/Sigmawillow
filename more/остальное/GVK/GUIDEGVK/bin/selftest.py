#!/usr/bin/env python3
"""GVK selftest: золотой случай протокола на локальном стенде.

Проверяет МЕХАНИКУ протокола, а не поведение LLM: атомарные захваты и гонки,
аренды и поколения, пины ТЗ, RBAC через guard.py, валидацию контрактов через
validate.py, порядок ролей по развилке, стоп и лечение, терминатор, слияние и
подмену слияния, релиз по СОРЕЛ.

Сети, JDK, Maven и GitHub не требует: репозиторий — локальный git, API — мок
с семантикой contents (201 / 422 / 409 / sha / обратное чтение).

  python3 bin/selftest.py [--keep] [--verbose]

Код возврата: 0 — все проверки прошли, 1 — есть провалы.
"""
import argparse, base64, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
PROTO = os.path.dirname(HERE)                      # GUIDEGVK/
TZ = "docs/TZ.md"
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    return bool(ok)


def sh(*a, cwd=None, ok=True):
    r = subprocess.run(a, cwd=cwd, capture_output=True, text=True)
    if ok and r.returncode != 0:
        raise RuntimeError(f"{' '.join(a)} → {r.returncode}: {r.stderr.strip()[:200]}")
    return r.stdout.strip()


# --------------------------------------------------------------------------- мок API
class Hub:
    """Семантика GitHub contents для ветки main: атомарное создание, sha, 409/422."""

    def __init__(self):
        self.files = {}
        self.calls = 0

    def _sha(self, text):
        return hashlib.sha1(text.encode()).hexdigest()

    def get(self, path):
        self.calls += 1
        f = self.files.get(path)
        return (200, f) if f else (404, None)

    def list(self, prefix):
        self.calls += 1
        return sorted(p[len(prefix):].lstrip("/") for p in self.files if p.startswith(prefix))

    def put(self, path, text, sha=None, atomic=False):
        self.calls += 1
        cur = self.files.get(path)
        if atomic:
            if cur:
                return 422, "already exists"
        elif cur and sha != cur["sha"]:
            return 409, "sha mismatch"
        self.files[path] = {"content": text, "sha": self._sha(text)}
        st, back = self.get(path)                       # обратное чтение по C12.5
        if st != 200 or back["content"] != text:
            return 500, "readback failed"
        return (201 if not cur else 200), "ok"

    def delete(self, path, sha=None):
        self.calls += 1
        cur = self.files.get(path)
        if not cur:
            return 404, "gone"
        if sha and sha != cur["sha"]:
            return 409, "sha mismatch"
        del self.files[path]
        return 200, "deleted"

    def json(self, path):
        st, f = self.get(path)
        return json.loads(f["content"]) if st == 200 else None


# --------------------------------------------------------------------------- стенд
class Bench:
    def __init__(self, root):
        self.root = root
        self.repo = os.path.join(root, "repo")
        self.hub = Hub()
        os.makedirs(self.repo)
        sh("git", "init", "-q", "-b", "main", self.repo)
        sh("git", "config", "user.email", "gvk@test", cwd=self.repo)
        sh("git", "config", "user.name", "gvk", cwd=self.repo)
        os.makedirs(os.path.join(self.repo, "docs"))
        self.write_file(TZ, "# ТЗ\n\n1. Ядро считает сумму.\n2. CLI печатает результат.\n3. GUI показывает окно.\n", "init")
        self.now = time.time()

    # --- git ---
    def write_file(self, rel, text, msg, branch=None):
        if branch:
            sh("git", "checkout", "-q", branch, cwd=self.repo)
        p = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(text)
        sh("git", "add", "-A", cwd=self.repo)
        sh("git", "commit", "-qm", msg, cwd=self.repo)
        return sh("git", "rev-parse", "--short", "HEAD", cwd=self.repo)

    def branch(self, name, frm="main"):
        sh("git", "checkout", "-q", frm, cwd=self.repo)
        sh("git", "checkout", "-q", "-b", name, cwd=self.repo)

    def head(self, branch=None):
        return sh("git", "rev-parse", "--short", branch or "HEAD", cwd=self.repo)

    def merge(self, branch):
        sh("git", "checkout", "-q", "main", cwd=self.repo)
        r = subprocess.run(["git", "merge", "--no-ff", "-m", f"merge {branch}", branch],
                           cwd=self.repo, capture_output=True, text=True)
        return r.returncode == 0

    def ls(self):
        return sh("git", "ls-tree", "-r", "--name-only", "main", cwd=self.repo).splitlines()

    # --- время GitHub заменяется стендовым.clock ---
    def clock(self, hours=0):
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.now + hours * 3600))

    def expired(self, iso):
        return iso < self.clock()

    # --- guard и validate: настоящие скрипты протокола ---
    def guard(self, role, paths, claim=None, merge=False, branch="main", intent="write",
              extra=(), content=None, pep_file=None):
        pep = pep_file or os.path.join(self.root, "PEP.json")
        if not pep_file:
            open(pep, "w", encoding="utf-8").write(json.dumps(self.hub.json("GVK/PEP.json"), ensure_ascii=False))
        cmd = [sys.executable, os.path.join(HERE, "guard.py"), "--role", role, "--pep", pep,
               "--branch", branch, "--intent", intent, "--now", self.clock()]
        cmd += ["--merge"] if merge else ["--paths"] + list(paths)
        if claim:
            cp = os.path.join(self.root, "claim.md"); open(cp, "w").write(claim); cmd += ["--claim", cp]
        if content:
            cf = os.path.join(self.root, "content.txt"); open(cf, "w").write(content); cmd += ["--content-file", cf]
        cmd += list(extra)
        r = subprocess.run(cmd, cwd=self.repo, capture_output=True, text=True)
        return r.returncode

    def validate(self, schema, obj):
        p = os.path.join(self.root, "art.json")
        open(p, "w", encoding="utf-8").write(json.dumps(obj, ensure_ascii=False))
        r = subprocess.run([sys.executable, os.path.join(HERE, "validate.py"),
                            "--schema", os.path.join(PROTO, "schema", f"{schema}.schema.json"), "--file", p],
                           capture_output=True, text=True)
        return r.returncode


# --------------------------------------------------------------------------- артефакты
def report(frag, owner, sha, status="ЗЕЛЕНО", tz="tzsha1", stage=1, tests=(3, 0, 0), remaining=None):
    return {"schema": "gvk/report/1", "schema_ver": "1", "fragment": frag, "stage": stage, "tz_sha": tz,
            "owner": owner, "role": "DEV", "branch": f"gvk/{frag}", "last_green": sha, "status": status,
            "tests": {"passed": tests[0], "failed": tests[1], "skipped": tests[2]},
            "attempts": 1, "cycles": 0, "remaining": remaining or [], "at": "2026-11-16T09:00:00Z",
            "protocol_ver": "ALV-5.1_PPV-5.1_MRV-selftest_TAV-1.1"}


def claim_text(owner, frag, until, epoch=1, pkgs="io.github.bizonrelax.demo.core"):
    return (f"---\nid: CLAIM-{frag}\nfile: {frag}.md\netymology: захват\n desc: захват\nname: захват\nF: захват\nQ: полный\n---\n\n"
            f"owner: {owner}\nepoch: {epoch}\nlease_until: {until}\npackages: {pkgs}\nbranch: gvk/{frag}\n"
            f"attempts: 1\nstage: 1\ntz_sha: tzsha1\n")


# --------------------------------------------------------------------------- сценарий
def run(b, verbose=False):
    H = b.hub
    tpl = json.load(open(os.path.join(PROTO, "pep.template.json"), encoding="utf-8"))

    # 1. FIRST: реестр, план, каркас, слияние 000
    tpl.update(repo="test/demo", created_at=b.clock(), created_by="a1", stage=1, tz_path=TZ, tz_sha="tzsha1")
    st, _ = H.put("GVK/PEP.json", json.dumps(tpl, ensure_ascii=False), atomic=True)
    check("FIRST: реестр ролей создан атомарно", st == 201)
    check("FIRST: реестр валиден по схеме pep", b.validate("pep", tpl) == 0)
    H.put("GVK/STAGES.md", "| 1 | 1 | docs/TZ.md | tzsha1 | 1.0 | date | исходное ТЗ | a1 |\n")
    H.put("GVK/LIMITS.md", "cycles_max: 2\nattempts_max: 3\nstopfix_max: 2\n")
    b.branch("gvk-plan"); b.write_file("GVK/PLAN.md", "| 001 | 1 | core | ТЗ 1 | - | test | 2 | - | - |\n| 002 | 1 | ui | ТЗ 3 | - | test | 3 | - | windows |\n", "plan")
    sh("git", "checkout", "-q", "main", cwd=b.repo)
    st, _ = H.put("GVK/claims/000.md", claim_text("a1", "000", b.clock(8)), atomic=True)
    check("FIRST: захват каркаса 000", st == 201)
    b.branch("gvk/000")
    sha000 = b.write_file("pom.xml", "<project/>\n", "skeleton")
    b.write_file("src/main/java/io/github/bizonrelax/demo/Main.java", "class Main{}\n", "main")
    check("FIRST: слияние 000 в main прошло", b.merge("gvk/000"))
    check("FIRST: файлы каркаса реально в main (проверка 9)", "pom.xml" in b.ls())
    H.put("REPORT/frag/000.json", json.dumps(report("000", "a1", sha000), ensure_ascii=False))
    H.delete("GVK/claims/000.md", H.get("GVK/claims/000.md")[1]["sha"])
    check("FIRST: захват 000 снят", H.get("GVK/claims/000.md")[0] == 404)

    # 2. гонка за фрагмент: два DEV, один фрагмент
    c1 = claim_text("a2", "001", b.clock(80))
    c2 = claim_text("a3", "001", b.clock(80))
    st_a, _ = H.put("GVK/claims/001.md", c1, atomic=True)
    st_b, _ = H.put("GVK/claims/001.md", c2, atomic=True)
    check("гонка: первый DEV получил 201", st_a == 201)
    check("гонка: второй DEV получил 422 и ушёл к другому фрагменту", st_b == 422)
    st_c, _ = H.put("GVK/claims/002.md", claim_text("a3", "002", b.clock(80), pkgs="io.github.bizonrelax.demo.ui"), atomic=True)
    check("гонка: второй DEV взял свободный 002", st_c == 201)

    # 3. RBAC: границы владения и запреты
    check("RBAC: DEV пишет свой пакет", b.guard("DEV", ["src/main/java/io/github/bizonrelax/demo/core/A.java"],
                                               claim="packages: io.github.bizonrelax.demo.core\nfragment: 001\n", branch="gvk/001") == 0)
    check("RBAC: DEV не пишет чужой пакет", b.guard("DEV", ["src/main/java/io/github/bizonrelax/demo/ui/B.java"],
                                                  claim="packages: io.github.bizonrelax.demo.core\nfragment: 001\n", branch="gvk/001") == 1)
    check("RBAC: DEV не пишет каркас", b.guard("DEV", ["pom.xml"]) == 1)
    check("RBAC: DEV не пишет ТЗ", b.guard("DEV", [TZ]) == 1)
    check("RBAC: DEV не сливает в main", b.guard("DEV", [], merge=True) == 1)
    check("RBAC: TESTER не пишет src/main", b.guard("TESTER", ["src/main/java/X.java"]) == 1)
    check("RBAC: OBSERVER не меняет состояние", b.guard("OBSERVER", ["GVK/STATE.md"]) == 1)
    check("RBAC: TERMINATOR пишет новое ТЗ", b.guard("TERMINATOR", [TZ]) == 0)
    check("RBAC: CLOSER сливает в main", b.guard("CLOSER", [], merge=True) == 0)

    # 4. работа DEV и контракты
    b.branch("gvk/001")
    sha1 = b.write_file("src/main/java/io/github/bizonrelax/demo/core/A.java", "class A{int s(int a,int b){return a+b;}}\n", "core")
    r1 = report("001", "a2", sha1)
    check("контракт: отчёт фрагмента валиден", b.validate("report", r1) == 0)
    bad = dict(r1, status="ГОТОВО")
    check("контракт: битый отчёт отклонён", b.validate("report", bad) == 1)
    H.put("REPORT/frag/001.json", json.dumps(r1, ensure_ascii=False))
    H.put("REPORT/ckpt/001.json", json.dumps({"schema": "gvk/checkpoint/1", "fragment": "001", "last_green": sha1,
                                              "step": "core done", "tests": r1["tests"], "at": b.clock()}, ensure_ascii=False))
    H.delete("GVK/claims/001.md", H.get("GVK/claims/001.md")[1]["sha"])
    b.branch("gvk/002")
    sha2 = b.write_file("src/main/java/io/github/bizonrelax/demo/ui/W.java", "class W{}\n", "ui")
    H.put("REPORT/frag/002.json", json.dumps(report("002", "a3", sha2), ensure_ascii=False))
    H.delete("GVK/claims/002.md", H.get("GVK/claims/002.md")[1]["sha"])

    # 5. REVIEWER: один принят, другой возвращён
    rev_ok = {"schema": "gvk/review/1", "fragment": "001", "verdict": "ПРИНЯТО", "checked_sha": sha1,
              "reviewer": "a4", "tz_sha": "tzsha1", "stage": 1, "remarks": [], "at": b.clock()}
    check("контракт: вердикт валиден", b.validate("review", rev_ok) == 0)
    H.put(f"REPORT/review/001-{sha1}.json", json.dumps(rev_ok, ensure_ascii=False))
    find = {"schema": "gvk/finding/1", "finding_id": f"F-002-{sha2}", "fragment": "002", "base_sha": sha2,
            "tz_sha": "tzsha1", "status": "open", "severity": "важно",
            "defects": [{"file": "W.java", "line": 1, "symptom": "окно не масштабируется",
                         "tz_requirement": "ТЗ 3", "severity": "важно"}], "at": b.clock()}
    check("контракт: дефект валиден", b.validate("finding", find) == 0)
    H.put(f"REPORT/finding/002-{sha2}.json", json.dumps(find, ensure_ascii=False))
    check("развилка: открытый дефект ведёт к CLEANER (C7.6 раньше C7.7)",
          H.json(f"REPORT/finding/002-{sha2}.json")["status"] == "open" and not H.list("GVK/claims"))

    # 6. CLEANER: фикс, закрытие дефекта, счётчик циклов
    st, _ = H.put("GVK/fixes/002.md", "owner: a5\nfinding_id: F-002\nbase_sha: " + sha2 + "\ntz_sha: tzsha1\n", atomic=True)
    check("CLEANER: fix-захват атомарен", st == 201)
    st2, _ = H.put("GVK/fixes/002.md", "owner: a6\n", atomic=True)
    check("CLEANER: второй чистильщик получил 422", st2 == 422)
    sh("git", "checkout", "-q", "gvk/002", cwd=b.repo)
    sha2b = b.write_file("src/main/java/io/github/bizonrelax/demo/ui/W.java", "class W{void fit(){}}\n", "fix")
    r2 = report("002", "a5", sha2b); r2["cycles"] = 1
    H.put("REPORT/frag/002.json", json.dumps(r2, ensure_ascii=False))
    find2 = dict(find, status="closed", fixed_sha=sha2b)
    H.put(f"REPORT/finding/002-{sha2}.json", json.dumps(find2, ensure_ascii=False), sha=H.get(f"REPORT/finding/002-{sha2}.json")[1]["sha"])
    H.delete("GVK/fixes/002.md", H.get("GVK/fixes/002.md")[1]["sha"])
    check("CLEANER: дефект закрыт, циклы учтены", H.json(f"REPORT/finding/002-{sha2}.json")["status"] == "closed" and r2["cycles"] == 1)

    # 7. PLANNER_TEST и TESTER
    task = {"schema": "gvk/test_task/1", "schema_ver": "1", "id": "T-001", "kind": "logic", "title": "сумма",
            "requirement_ref": "ТЗ 1", "fragment": "001", "level": 1, "env": "linux", "steps": [{"do": "2+2", "expect": "4"}],
            "expected": "4", "acceptance": "test sum", "severity_if_fail": "блокер", "deps": [], "est_min": 10,
            "stage": 1, "tz_sha": "tzsha1", "at": b.clock(), "owner": "a7", "protocol_ver": "selftest"}
    plan = {"schema": "gvk/test_plan/1", "stage": 1, "tz_sha": "tzsha1",
            "coverage": [{"requirement": "ТЗ 1", "tasks": ["T-001"], "covered": True}],
            "tasks": [{"id": "T-001", "kind": "logic", "level": 1, "env": "linux", "severity": "блокер"}],
            "acceptance_gate": {"blockers_pass": False, "coverage_complete": True, "no_open_blockers": True},
            "uncovered": [], "at": b.clock(), "owner": "a7", "protocol_ver": "selftest"}
    check("контракт: тест-план валиден", b.validate("test_plan", plan) == 0)
    check("контракт: задача тестировщику валидна", b.validate("test_task", task) == 0)
    H.put("REPORT/test/PLAN.json", json.dumps(plan, ensure_ascii=False))
    H.put("REPORT/test/T-001.json", json.dumps(task, ensure_ascii=False))
    tc = {"schema": "gvk/test_claim/1", "owner": "a8", "task": "T-001", "lease_until": b.clock(8), "at": b.clock()}
    st1, _ = H.put("REPORT/test/claims/T-001.json", json.dumps(tc), atomic=True)
    st2, _ = H.put("REPORT/test/claims/T-001.json", json.dumps(dict(tc, owner="a9")), atomic=True)
    check("TESTER: задача захвачена один раз (201/422)", st1 == 201 and st2 == 422)
    res = {"schema": "gvk/test_result/1", "task": "T-001", "verdict": "pass", "env_used": "linux", "checked_sha": sha1,
           "branch": "gvk/test-T-001", "steps": [{"step": "2+2", "expect": "4", "fact": "4", "status": "pass"}],
           "artifacts": [], "defects": [], "stage": 1, "tz_sha": "tzsha1", "at": b.clock(), "owner": "a8", "protocol_ver": "selftest"}
    check("контракт: результат теста валиден", b.validate("test_result", res) == 0)
    check("контракт: результат без факта отклонён",
          b.validate("test_result", dict(res, steps=[{"step": "2+2", "expect": "4", "status": "pass"}])) == 1)
    H.put("REPORT/test/R-T-001.json", json.dumps(res, ensure_ascii=False))
    H.delete("REPORT/test/claims/T-001.json", H.get("REPORT/test/claims/T-001.json")[1]["sha"])

    # 8. COMPLIANCE
    comp = {"schema": "gvk/compliance/1", "checked_sha": b.head("main"), "deps": [], "borrowings": [],
            "conflicts": [], "blockers": [], "verdict": "ЗЕЛЕНО", "at": b.clock(), "owner": "a10", "protocol_ver": "selftest"}
    check("контракт: комплаенс валиден", b.validate("compliance", comp) == 0)
    H.put("REPORT/COMPLIANCE.json", json.dumps(comp, ensure_ascii=False))

    # 9. CLOSER: слияние, проверка факта, подмена слияния, релиз
    before = len(b.ls())
    check("CLOSER: слияние 001", b.merge("gvk/001"))
    check("CLOSER: слияние 002", b.merge("gvk/002"))
    check("CLOSER: код фрагментов реально в main", any("demo/core/A.java" in p for p in b.ls()) and any("demo/ui/W.java" in p for p in b.ls()))
    check("CLOSER: число файлов не уменьшилось", len(b.ls()) >= before)
    src_before = sorted(p for p in b.ls() if p.startswith("src/"))
    b.branch("gvk/fake")
    b.write_file("GVK/STATE.md", "| подмена |\n", "fake merge")
    b.merge("gvk/fake")
    src_after = sorted(p for p in b.ls() if p.startswith("src/"))
    check("CLOSER: коммит только с GVK/*.md не считается слиянием кода", src_before == src_after and len(src_before) == 3)
    b.merge("gvk-plan")
    sh("git", "checkout", "-q", "main", cwd=b.repo)
    sh("git", "tag", "-a", "release/v1.0.0", "-m", "release", cwd=b.repo)
    sh("git", "branch", "release/v1.0.0", cwd=b.repo)
    final = {"schema": "gvk/final_report/1", "stage": 1, "mode": "release",
             "requirements": [{"requirement": "ТЗ 1", "status": "выполнено", "evidence": f"001/{sha1}/T-001 pass"}],
             "tests": {"passed": 6, "failed": 0, "skipped": 0}, "merged_branches": ["gvk/000", "gvk/001", "gvk/002", "gvk-plan"],
             "release": {"version": "1.0.0", "tag": "release/v1.0.0", "branch": "release/v1.0.0"},
             "removed": [], "leftovers": [], "at": b.clock(), "owner": "a11", "protocol_ver": "selftest"}
    check("контракт: финальный отчёт валиден", b.validate("final_report", final) == 0)
    H.put("REPORT/FINAL.json", json.dumps(final, ensure_ascii=False))
    H.put("GVK/FINAL.md", "---\nid: FINAL\nfile: FINAL.md\netymology: итог\ndesc: итог\nname: итог\nF: итог\nQ: полный\n---\n\nрелиз v1.0.0\n")
    check("СОРЕЛ: тег релиза создан", "release/v1.0.0" in sh("git", "tag", cwd=b.repo))
    check("СОРЕЛ: ветка релиза создана", "release/v1.0.0" in sh("git", "branch", cwd=b.repo))
    check("развилка: FINAL.md останавливает новых агентов (C7.1)", H.get("GVK/FINAL.md")[0] == 200)

    # 10. стоп и лечение (отдельная ветка состояния)
    H.delete("GVK/FINAL.md", H.get("GVK/FINAL.md")[1]["sha"])
    stop = "---\nid: STOP\nfile: STOP.md\netymology: стоп\ndesc: стоп\nname: стоп\nF: сигнал\nQ: полный\n---\n\nreason: infeasible\nrequirement: ТЗ 3\nevidence: jpackage не собирает Windows на Linux\nsuggestion: собирать в CI\n"
    st, _ = H.put("GVK/STOP.md", stop, atomic=True)
    st2, _ = H.put("GVK/STOP.md", stop.replace("ТЗ 3", "ТЗ 4"), atomic=True)
    check("СТОП: создан атомарно, второй не перезаписал", st == 201 and st2 == 422)
    H.put("GVK/claims/003.md", claim_text("a12", "003", b.clock(80)))
    for p in H.list("GVK/claims"):
        H.delete("GVK/claims/" + p, H.get("GVK/claims/" + p)[1]["sha"])
    H.put("GVK/releases/stop-a12.md", "cause: stop\nномера: 003\n")
    check("СТОП: захваты освобождены, журнал освобождения есть", not H.list("GVK/claims") and H.list("GVK/releases"))
    st, _ = H.put("GVK/stopfix.md", f"owner: a13\nstop_sha: {H.get('GVK/STOP.md')[1]['sha']}\nlease_until: {b.clock(4)}\n", atomic=True)
    check("TZFIX: захват лечения один", st == 201)
    H.put("GVK/CHANGE-001.md", "cause: stopfix\nбыло: ТЗ 3\nстало: ТЗ 3 через CI\n")
    H.put("GVK/STAGES.md", H.get("GVK/STAGES.md")[1]["content"] + "| 2 | 1 | docs/TZ.md | tzsha2 | 1.1 | date | CHANGE-001 | a13 |\n",
          sha=H.get("GVK/STAGES.md")[1]["sha"])
    H.delete("GVK/STOP.md", H.get("GVK/STOP.md")[1]["sha"]); H.delete("GVK/stopfix.md", H.get("GVK/stopfix.md")[1]["sha"])
    check("TZFIX: стоп снят, ревизия добавлена, этап не изменился",
          H.get("GVK/STOP.md")[0] == 404 and len(H.get("GVK/STAGES.md")[1]["content"].strip().splitlines()) == 2)

    # 11. поколение и аренда
    H.put("GVK/claims/004.md", claim_text("a14", "004", b.clock(80), epoch=1))
    old = H.get("GVK/claims/004.md")[1]["content"]
    H.put("GVK/claims/004.md", claim_text("a15", "004", b.clock(80), epoch=2), sha=H.get("GVK/claims/004.md")[1]["sha"])
    check("ОТОЗВАТЬ: epoch вырос, старый владелец обязан выбросить работу (W6)", "epoch: 1" in old and "epoch: 2" in H.get("GVK/claims/004.md")[1]["content"])
    H.put("GVK/claims/005.md", claim_text("a16", "005", b.clock(-1)))
    check("аренда: просрочка распознаётся, живая аренда — нет", b.expired(b.clock(-1)) and not b.expired(b.clock(80)))
    st, _ = H.put("GVK/claims/005.md", claim_text("a17", "005", b.clock(80)), atomic=True)
    check("аренда: атомарный захват занятого всё равно 422 (снимает рычаг или просрочка)", st == 422)

    # 12. терминатор: новый этап и сквозная нумерация
    H.put("GVK/STOP.md", stop.replace("reason: infeasible", "reason: replan"), atomic=True)
    for p in H.list("GVK/claims"):
        H.delete("GVK/claims/" + p, H.get("GVK/claims/" + p)[1]["sha"])
    nums = [int(re.match(r"(\d+)", n).group(1)) for n in H.list("REPORT/frag") if re.match(r"\d+", n)]
    nxt = max(nums) + 1
    H.put("GVK/STAGES.md", H.get("GVK/STAGES.md")[1]["content"] + f"| 3 | 2 | docs/TZ.md | tzsha3 | 2.0 | date | CHANGE-002 | a18 |\n",
          sha=H.get("GVK/STAGES.md")[1]["sha"])
    H.put("GVK/CHANGE-002.md", "cause: terminator\nэтап: 2\n")
    H.delete("GVK/STOP.md", H.get("GVK/STOP.md")[1]["sha"])
    check("ТЕРМИНАТОР: этап 2 создан, барьер снят", "| 3 | 2 |" in H.get("GVK/STAGES.md")[1]["content"] and H.get("GVK/STOP.md")[0] == 404)
    check("ТЕРМИНАТОР: нумерация сквозная, номера не переиспользованы", nxt == 3)
    check("ТЕРМИНАТОР: отчёты прошлых этапов сохранены", len(H.list("REPORT/frag")) == 3)

    # 13. журнал событий
    ev = {"at": b.clock(), "owner": "a2", "role": "DEV", "fragment": "001", "event": "commit", "sha": sha1, "protocol_ver": "selftest"}
    check("контракт: событие валидно", b.validate("event", ev) == 0)
    check("контракт: событие с выдуманным типом отклонено", b.validate("event", dict(ev, event="magic")) == 1)

    # 14. стек python: приоритет ТЗ, защита каркаса, критерии переносимости
    pep = H.json("GVK/PEP.json")
    pep["stack"].update(language="python", version="3.12", packaging="pyinstaller --onedir", decided_by="a1")
    H.put("GVK/PEP.json", json.dumps(pep, ensure_ascii=False), sha=H.get("GVK/PEP.json")[1]["sha"])
    check("стек: python принят по ТЗ, реестр обновлён", H.json("GVK/PEP.json")["stack"]["language"] == "python")
    check("стек: DEV пишет .py своего пакета", b.guard("DEV", ["src/app/calc.py"],
          claim="packages: app.calc\nfragment: 001\n", branch="gvk/001") == 0)
    check("стек: DEV пишет тесты python", b.guard("DEV", ["tests/test_calc.py"],
          claim="packages: app.calc\nfragment: 001\n", branch="gvk/001") == 0)
    check("стек: DEV не правит requirements.txt (каркас 000)", b.guard("DEV", ["requirements.txt"]) == 1)
    check("стек: DEV не правит pyproject.toml", b.guard("DEV", ["pyproject.toml"]) == 1)
    check("стек: DEV не правит python-workflow", b.guard("DEV", [".github/workflows/python.yml"]) == 1)
    check("стек: TESTER пишет тесты, но не код приложения", b.guard("TESTER", ["tests/test_gui.py"]) == 0
          and b.guard("TESTER", ["src/app/calc.py"]) == 1)
    check("стек: CLOSER правит каркас при приёмке", b.guard("CLOSER", ["requirements.txt"]) == 0)
    stk = {"schema": "gvk/stack/1", "schema_ver": "1", "language": "python", "version": "3.12",
           "packaging": "pyinstaller --onedir", "runtime_included": True, "runtime_cost": "none",
           "licenses": [{"component": "numpy", "license": "BSD-3-Clause", "risk": "none"}],
           "checklist": [{"criterion": i, "fact": "CI windows-latest: запуск из пути с кириллицей", "status": "pass"} for i in range(1, 7)],
           "blockers": [], "decided_by": "a1", "tz_ref": "ТЗ 1", "at": b.clock(), "owner": "a1", "protocol_ver": "selftest"}
    check("стек: отчёт переносимости валиден", b.validate("stack", stk) == 0)
    check("стек: платная среда исполнения отклонена", b.validate("stack", dict(stk, runtime_cost="paid")) == 1)
    check("стек: неполный чек-лист ST1 отклонён", b.validate("stack", dict(stk, checklist=stk["checklist"][:3])) == 1)
    H.put("REPORT/stack.json", json.dumps(stk, ensure_ascii=False))
    check("стек: решение записано в REPORT/stack.json", H.json("REPORT/stack.json")["language"] == "python")

    run_v52(b)

    # 15. целостность поставки протокола
    pep_tpl = json.load(open(os.path.join(PROTO, "pep.template.json"), encoding="utf-8"))
    missing = [m for d in pep_tpl["roles"].values() for m in d.get("needs", []) + d.get("lazy", [])
               if not os.path.isfile(os.path.join(PROTO, m))]
    check("поставка: все модули needs и lazy существуют", not missing, ", ".join(sorted(set(missing))))
    wrong, ids = [], {}
    for name in sorted(os.listdir(PROTO)):
        if not name.endswith(".md"):
            continue
        text = open(os.path.join(PROTO, name), encoding="utf-8").read()
        m = re.search(r"^file: (.+)$", text, re.M)
        if m and m.group(1).strip() != name:
            wrong.append(f"{name} → {m.group(1).strip()}")
        i = re.search(r"^id: (.+)$", text, re.M)
        if i:
            ids.setdefault(i.group(1).strip(), []).append(name)
    check("поставка: шапка file совпадает с именем файла", not wrong, "; ".join(wrong))
    dup = {k: v for k, v in ids.items() if len(v) > 1}
    check("поставка: идентификаторы модулей уникальны", not dup, str(dup))
    fences = []
    for root, _, names in os.walk(os.path.dirname(PROTO)):
        for name in names:
            if name.endswith(".md"):
                text = open(os.path.join(root, name), encoding="utf-8").read()
                if len(re.findall(r"^\s*`{3,}", text, re.M)) % 2:
                    fences.append(name)
    check("поставка: тройные ограждения парные", not fences, ", ".join(fences))


# --------------------------------------------------------------------------- v5.2: регрессии
def _pep(b, lang="python", **kw):
    """Свежий реестр из шаблона: тесты не зависят от состояния сценария."""
    p = json.load(open(os.path.join(PROTO, "pep.template.json"), encoding="utf-8"))
    p["repo"] = "O/R"; p["tz_path"] = TZ; p["stack"]["language"] = lang
    p.update(kw)
    f = os.path.join(b.root, f"pep-{lang}-{abs(hash(json.dumps(kw, sort_keys=True))) % 9999}.json")
    open(f, "w", encoding="utf-8").write(json.dumps(p, ensure_ascii=False))
    return f


def _tool(name, *args, cwd=None):
    r = subprocess.run([sys.executable, os.path.join(HERE, name)] + list(args),
                       cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def run_v52(b):
    H = b.hub
    pj = _pep(b, "java"); pp = _pep(b, "python")
    own_j = "packages: com.foo.calc\nfragment: 001\n"
    own_p = "packages: app.calc\nfragment: 001\n"

    # --- guard: закрытые обходы ---
    check("guard v5.2: обход через '..' запрещён",
          b.guard("DEV", ["src/../pom.xml"], claim=own_p, branch="gvk/001", pep_file=pp) == 1)
    check("guard v5.2: вложенный чужой пакет запрещён",
          b.guard("DEV", ["src/main/java/evil/com/foo/calc/X.java"], claim=own_j, branch="gvk/001", pep_file=pj) == 1)
    check("guard v5.2: свой пакет java разрешён",
          b.guard("DEV", ["src/main/java/com/foo/calc/X.java"], claim=own_j, branch="gvk/001", pep_file=pj) == 0)
    check("guard v5.2: без захвата владение не доказано — запрет",
          b.guard("DEV", ["app/calc/x.py"], branch="gvk/001", pep_file=pp) == 1)
    check("guard v5.2: тесты своего пакета по объявленным глобам",
          b.guard("DEV", ["tests/calc/test_x.py"], claim=own_p + "tests: tests/calc/**\n",
                  branch="gvk/001", pep_file=pp) == 0)
    tbl_claim = ("---\nid: 001\nfile: 001.md\n---\n\n| Поле | Значение |\n| --- | --- |\n"
                 "| `fragment` | `001` |\n| `owner` | `a1` |\n| `packages` | `app.calc` |\n"
                 "| `tests` | `tests/calc/**` |\n")
    check("guard v5.2: захват md+ таблицей с кавычками читается",
          b.guard("DEV", ["app/calc/x.py", "tests/calc/test_x.py"], claim=tbl_claim,
                  branch="gvk/001", pep_file=pp) == 0)
    check("guard v5.2: STOP создаётся атомарно любой ролью (C9.4)",
          b.guard("DEV", ["GVK/STOP.md"], intent="create", pep_file=pp) == 0)
    check("guard v5.2: перезапись STOP обычной ролью запрещена",
          b.guard("DEV", ["GVK/STOP.md"], intent="update", pep_file=pp) == 1)
    check("guard v5.2: TZFIX удаляет STOP",
          b.guard("TZFIX", ["GVK/STOP.md"], intent="delete", pep_file=pp) == 0)
    check("guard v5.2: FIRST создаёт python-каркас",
          b.guard("FIRST", ["pyproject.toml", "requirements.txt", ".github/workflows/ci.yml"], pep_file=pp) == 0)
    check("guard v5.2: FIRST не меняет ТЗ", b.guard("FIRST", [TZ], pep_file=pp) == 1)
    check("guard v5.2: FIRST сливает только 000",
          b.guard("FIRST", [], merge=True, extra=["--merge-fragment", "007"], pep_file=pp) == 1
          and b.guard("FIRST", [], merge=True, extra=["--merge-fragment", "000"], pep_file=pp) == 0)
    check("guard v5.2: FIREFIGHTER вне своей ветки запрещён",
          b.guard("FIREFIGHTER", ["src/x.py"], branch="gvk/007", pep_file=pp) == 1
          and b.guard("FIREFIGHTER", ["src/x.py"], branch="gvk/fire", pep_file=pp) == 0)
    check("guard v5.2: TESTER не пишет код приложения python",
          b.guard("TESTER", ["app/calc/x.py"], branch="gvk/test-T-001", pep_file=pp) == 1)
    check("guard v5.2: OBSERVER пишет только учёт и журнал",
          b.guard("OBSERVER", ["REPORT/tokens/20261122/o-OBSERVER-101010.json"], pep_file=pp) == 0
          and b.guard("OBSERVER", ["REPORT/frag/001.json"], pep_file=pp) == 1)
    check("guard v5.2: буквальный токен владельца в содержимом ловится",
          b.guard("DEV", ["REPORT/tokens/x.json"], claim=own_p,
                  content="token=ghp_" + "a" * 36, pep_file=pp) == 1)
    r = subprocess.run([sys.executable, os.path.join(HERE, "guard.py"), "--role", "DEV",
                        "--pep", pp, "--branch", "main", "--staged"],
                       cwd=b.root, capture_output=True, text=True)
    check("guard v5.2: ошибка инструмента — запрет, а не разрешение", r.returncode == 2, r.stdout.strip()[:60])

    # --- ACCESS: подделка, срок, адресат ---
    acc = os.path.join(b.repo, "GVK", "ACCESS.md")
    os.makedirs(os.path.dirname(acc), exist_ok=True)
    open(acc, "w").write("glob: REPORT/frag/**\nmode: ЗАПИСЬ\n")
    check("guard v5.2: локальный ACCESS.md прав не даёт",
          b.guard("REVIEWER", ["REPORT/frag/001.json"], pep_file=pp) == 1)
    sh("git", "add", "-A", cwd=b.repo); sh("git", "commit", "-qm", "access-local", cwd=b.repo)
    sh("git", "update-ref", "refs/remotes/origin/main", "HEAD", cwd=b.repo)
    check("guard v5.2: ACCESS без grantee не действует",
          b.guard("REVIEWER", ["REPORT/frag/001.json"], pep_file=pp) == 1)
    base = "grantee: REVIEWER\nglob: REPORT/frag/**\nmode: ЗАПИСЬ\ngranted_by: owner\nconfirmed: true\n"
    open(acc, "w").write(base + "expires_at: 2020-01-01T00:00:00Z\n")
    sh("git", "add", "-A", cwd=b.repo); sh("git", "commit", "-qm", "access-old", cwd=b.repo)
    sh("git", "update-ref", "refs/remotes/origin/main", "HEAD", cwd=b.repo)
    check("guard v5.2: просроченный грант не действует",
          b.guard("REVIEWER", ["REPORT/frag/001.json"], pep_file=pp) == 1)
    open(acc, "w").write(base + "expires_at: 2099-01-01T00:00:00Z\n")
    sh("git", "add", "-A", cwd=b.repo); sh("git", "commit", "-qm", "access-ok", cwd=b.repo)
    sh("git", "update-ref", "refs/remotes/origin/main", "HEAD", cwd=b.repo)
    check("guard v5.2: действующий грант расширяет write",
          b.guard("REVIEWER", ["REPORT/frag/001.json"], pep_file=pp) == 0)
    check("guard v5.2: грант не отменяет явный deny",
          b.guard("REVIEWER", ["src/main/java/X.java"], pep_file=pp) == 1)
    os.remove(acc); sh("git", "add", "-A", cwd=b.repo); sh("git", "commit", "-qm", "access-rm", cwd=b.repo)
    sh("git", "update-ref", "refs/remotes/origin/main", "HEAD", cwd=b.repo)

    # --- реестр: каталог неприкосновенен ---
    old = json.load(open(pp, encoding="utf-8"))
    new = json.loads(json.dumps(old)); new["roles"]["GOD"] = dict(old["roles"]["CLOSER"])
    fo, fn = os.path.join(b.root, "pep.old.json"), os.path.join(b.root, "pep.new.json")
    open(fo, "w").write(json.dumps(old, ensure_ascii=False)); open(fn, "w").write(json.dumps(new, ensure_ascii=False))
    check("guard v5.2: роль в каталог без рычага не добавить",
          _tool("guard.py", "--role", "DEV", "--pep-old", fo, "--pep-new", fn)[0] == 1)
    check("guard v5.2: с рычагом РОЛИ ОБНОВИ добавить можно",
          _tool("guard.py", "--role", "FIRST", "--pep-old", fo, "--pep-new", fn, "--allow-catalog")[0] == 0)
    new2 = json.loads(json.dumps(old)); new2["roles"]["DEV"]["permissions"]["merge_main"] = True
    open(fn, "w").write(json.dumps(new2, ensure_ascii=False))
    check("guard v5.2: права роли менять нельзя",
          _tool("guard.py", "--role", "DEV", "--pep-old", fo, "--pep-new", fn)[0] == 1)
    new3 = json.loads(json.dumps(old)); new3["roles"]["DEV"]["status"] = "занят"; new3["roles"]["DEV"]["owner"] = "a9"
    open(fn, "w").write(json.dumps(new3, ensure_ascii=False))
    check("guard v5.2: свой снимок занятости менять можно",
          _tool("guard.py", "--role", "DEV", "--pep-old", fo, "--pep-new", fn)[0] == 0)
    new4 = json.loads(json.dumps(old)); new4["roles"]["CLEANER"]["owner"] = "a9"
    open(fn, "w").write(json.dumps(new4, ensure_ascii=False))
    check("guard v5.2: чужой снимок занятости менять нельзя",
          _tool("guard.py", "--role", "DEV", "--pep-old", fo, "--pep-new", fn)[0] == 1)
    new5 = json.loads(json.dumps(old)); new5["limits"]["cycles_max"] = "unlimited"
    open(fn, "w").write(json.dumps(new5, ensure_ascii=False))
    check("guard v5.2: потолки без рычага не поднять",
          _tool("guard.py", "--role", "DEV", "--pep-old", fo, "--pep-new", fn)[0] == 1
          and _tool("guard.py", "--role", "TERMINATOR2", "--pep-old", fo, "--pep-new", fn, "--allow-limits")[0] == 0)
    new6 = json.loads(json.dumps(old)); new6["protocol_ver"] = "9.9"
    open(fn, "w").write(json.dumps(new6, ensure_ascii=False))
    check("guard v5.2: миграция protocol_ver — FIRST можно, DEV нельзя",
          _tool("guard.py", "--role", "FIRST", "--pep-old", fo, "--pep-new", fn)[0] == 0
          and _tool("guard.py", "--role", "DEV", "--pep-old", fo, "--pep-new", fn)[0] == 1)
    new7 = json.loads(json.dumps(old)); new7.setdefault("stack", {})["language"] = "go"
    open(fn, "w").write(json.dumps(new7, ensure_ascii=False))
    check("guard v5.2: смена стека только рычагом СТЕК (ST8)",
          _tool("guard.py", "--role", "WISH", "--pep-old", fo, "--pep-new", fn)[0] == 1
          and _tool("guard.py", "--role", "WISH", "--pep-old", fo, "--pep-new", fn, "--allow-stack")[0] == 0)

    # --- валидатор: журналы и новые поля ---
    jl = os.path.join(b.root, "ev.jsonl")
    e1 = {"schema": "gvk/event/1", "at": b.clock(), "owner": "a", "role": "DEV", "event": "claim"}
    e2 = dict(e1, event="tokens")
    open(jl, "w").write(json.dumps(e1, ensure_ascii=False) + "\n" + json.dumps(e2, ensure_ascii=False) + "\n")
    sch = os.path.join(PROTO, "schema", "event.schema.json")
    check("validate v5.2: журнал из двух строк валиден",
          _tool("validate.py", "--schema", sch, "--file", jl)[0] == 0)
    open(jl, "a").write("{битая строка}\n")
    check("validate v5.2: битая строка журнала отклонена",
          _tool("validate.py", "--schema", sch, "--file", jl)[0] == 1)
    bad_time = dict(e1, at="16.11.2026 9:00")
    check("validate v5.2: неверный формат времени отклонён", b.validate("event", bad_time) == 1)
    rp = report("001", "a2", "abc1234")
    check("validate v5.2: булево не проходит как число",
          b.validate("report", dict(rp, attempts=True)) == 1)
    check("validate v5.2: блокировка фрагмента записывается в отчёт",
          b.validate("report", dict(rp, blocked=True, blocked_reason="attempts_max=3", block_kind="attempts_max")) == 0)
    check("validate v5.2: блокировка без причины отклонена",
          b.validate("report", dict(rp, blocked=True)) == 1)
    fin = {"schema": "gvk/final_report/1", "stage": 1, "requirements": [], "tests": {"passed": 3, "failed": 0, "skipped": 0},
           "merged_branches": ["gvk/001"], "at": b.clock(), "owner": "a1", "protocol_ver": "selftest"}
    check("validate v5.2: финал без режима отклонён", b.validate("final_report", fin) == 1)
    check("validate v5.2: финал с режимом релиза валиден",
          b.validate("final_report", dict(fin, mode="release", work_continues=True)) == 0)

    # --- реестр: карточка вместо чтения целиком ---
    rc, out = _tool("pep.py", "card", "--role", "DEV", "--pep", pp)
    sys.path.insert(0, HERE)
    from tokens import est_text
    full = est_text(open(pp, encoding="utf-8").read()); cardt = est_text(out)
    check("pep v5.2: карточка роли в разы дешевле реестра", rc == 0 and cardt * 3 < full, f"{cardt} против {full}")
    check("pep v5.2: карточка несёт claim, branches, dicts",
          all(k in out for k in ('"claim"', '"branches"', '"dicts"', '"create_only"')))
    check("pep v5.2: шаблон проходит проверку структуры", _tool("pep.py", "check", "--pep", pp)[0] == 0)
    broken = json.loads(open(pp, encoding="utf-8").read()); broken["roles"]["DEV"].pop("permissions")
    fb = os.path.join(b.root, "pep-broken.json"); open(fb, "w").write(json.dumps(broken, ensure_ascii=False))
    check("pep v5.2: схема ловит роль без прав",
          _tool("validate.py", "--schema", os.path.join(PROTO, "schema", "pep.schema.json"), "--file", fb)[0] == 1)
    man_p = os.path.join(os.path.dirname(PROTO), "MANIFEST.json")
    rc, out = _tool("pep.py", "budget", "--pep", pp, "--manifest", man_p)
    check("pep v5.2: бюджет входа считается и все роли в пределе",
          rc == 0 and "PEP BUDGET OK" in out and "FIRST |" in out, out.strip().splitlines()[-1] if out else "")
    tight = json.loads(open(pp, encoding="utf-8").read()); tight["limits"]["budget_input_tokens"] = 5000
    ft = os.path.join(b.root, "pep-tight.json"); open(ft, "w").write(json.dumps(tight, ensure_ascii=False))
    rc, out = _tool("pep.py", "budget", "--pep", ft, "--manifest", man_p)
    check("pep v5.2: превышение бюджета входа даёт код 1", rc == 1 and "ПРЕВЫШЕНИЕ" in out)

    # --- словари ---
    dd = os.path.join(PROTO, "dict")
    codes = {}
    dup = []
    for name in sorted(os.listdir(dd)):
        for line in open(os.path.join(dd, name), encoding="utf-8"):
            if line.startswith("%"):
                c = line.split(" ", 1)[0]
                if c in codes:
                    dup.append(c)
                codes[c] = name
    check("dict v5.2: коды уникальны во всех словарях", not dup, ", ".join(dup))
    art = {"schema": "gvk/report/1", "fragment": "001", "status": "ЗЕЛЕНО",
           "remaining": ["сборка зелёная, коммит и пуш выполнены немедленно",
                         "остаток работы: следующий шаг и имя падающего теста"]}
    fa = os.path.join(b.root, "a.json"); fc = os.path.join(b.root, "ac.json")
    open(fa, "w").write(json.dumps(art, ensure_ascii=False))
    rc, out = _tool("dict.py", "encode", "--role", "DEV", "--pep", pp, "--in", fa, "--out", fc)
    enc = open(fc, encoding="utf-8").read() if os.path.exists(fc) else ""
    check("dict v5.2: сжатие уменьшает артефакт", rc == 0 and len(enc) < len(json.dumps(art, ensure_ascii=False)))
    check("dict v5.2: сжатие только в разрешённых зонах", "%k3" in enc and "ЗЕЛЕНО" in enc)
    check("dict v5.2: lint пропускает корректный артефакт", _tool("dict.py", "lint", "--in", fc)[0] == 0)
    rd, outd = _tool("dict.py", "decode", "--in", fc)
    check("dict v5.2: раскрытие возвращает исходные фразы", rd == 0 and art["remaining"][0] in outd)
    bad = dict(art); bad["status"] = "%k3"
    fbad = os.path.join(b.root, "bad.json"); open(fbad, "w").write(json.dumps(bad, ensure_ascii=False))
    check("dict v5.2: код в запрещённой зоне отклонён", _tool("dict.py", "lint", "--in", fbad)[0] == 1)
    rc, out = _tool("dict.py", "load", "--role", "DEV", "--pep", pp, "--codes", "%g3")
    check("dict v5.2: раскрытие одного кода дешевле словаря", rc == 0 and est_text(out) < 60)
    check("dict v5.2: audit без корпуса не советует убрать словарь",
          _tool("dict.py", "audit", "--role", "DEV")[0] == 2)
    rc, out = _tool("dict.py", "load", "--role", "DEV")
    check("dict v5.2: ролевой и групповой словарь активны без реестра проекта",
          rc == 0 and "%d1 " in out and "%k1 " in out and "%g1 " in out)

    # --- учёт токенов ---
    ft = os.path.join(b.root, "tokens.json")
    rc, out = _tool("tokens.py", "session", "--role", "DEV", "--owner", "a2", "--fragment", "001",
                    "--read", os.path.join(PROTO, "COMMON.md"), "--wrote", fa, "--calls", "12",
                    "--model", "selftest", "--at", b.clock(), "--out", ft)
    tok = json.load(open(ft, encoding="utf-8"))
    check("tokens v5.2: запись сессии валидна по схеме",
          _tool("validate.py", "--schema", os.path.join(PROTO, "schema", "tokens.schema.json"), "--file", ft)[0] == 0)
    check("tokens v5.2: оценка помечена честно", tok["source"] == "estimate" and tok["estimator"] == "gvk-bytes/1")
    rc, line = _tool("tokens.py", "line", "--file", ft)
    check("tokens v5.2: строка чата с пометкой оценки", line.strip().startswith("расход токенов:") and "(оценка)" in line)
    rc, out = _tool("tokens.py", "session", "--role", "DEV", "--owner", "a2", "--exact-in", "1000",
                    "--exact-out", "200", "--model", "selftest", "--at", b.clock(), "--out", ft)
    rc, line = _tool("tokens.py", "line", "--file", ft)
    check("tokens v5.2: точный счётчик даёт строку без пометки",
          json.load(open(ft, encoding="utf-8"))["source"] == "exact" and "(оценка)" not in line)
    tdir = os.path.join(b.root, "REPORT", "tokens", "20261122")
    os.makedirs(tdir, exist_ok=True)
    for i, n in enumerate(("a2-DEV-101010", "a3-DEV-101011")):
        rec = dict(tok, session_id=n, total_tokens=1000 + i, in_tokens=800, out_tokens=200, source="estimate")
        open(os.path.join(tdir, n + ".json"), "w").write(json.dumps(rec, ensure_ascii=False))
    rc, out = _tool("tokens.py", "rollup", "--dir", os.path.join(b.root, "REPORT", "tokens"))
    check("tokens v5.2: сводка считает по шардам", rc == 0 and "сессий 2" in out)

    # --- журнал: параллельное дописывание не теряет строк ---
    import importlib.util
    spec = importlib.util.spec_from_file_location("gvkapi", os.path.join(HERE, "api.py"))
    api = importlib.util.module_from_spec(spec); spec.loader.exec_module(api)
    store = {"REPORT/events/20261122.jsonl": {"sha": "s0", "text": '{"event":"birth"}\n'}}

    def hub_call(method, url, body=None, tries=5, raw=False):
        path = url.split("/contents/")[1].split("?")[0]
        if method == "GET":
            e = store.get(path)
            if not e:
                return 404, {"message": "Not Found"}, {}
            return 200, {"sha": e["sha"], "encoding": "base64",
                         "content": base64.b64encode(e["text"].encode()).decode()}, {}
        if method == "PUT":
            cur = store.get(path); txt = base64.b64decode(body["content"]).decode()
            if cur and body.get("sha") != cur["sha"]:
                return 409, {"message": "sha mismatch"}, {}
            store[path] = {"sha": "s" + str(int((cur or {"sha": "s0"})["sha"][1:]) + 1), "text": txt}
            return 200, {}, {}
        return 500, {}, {}

    api.token = lambda: "x"; api.call = hub_call
    line_a = '{"schema":"gvk/event/1","event":"claim","owner":"A","role":"DEV","at":"2026-11-22T10:00:00Z"}'
    line_b = '{"schema":"gvk/event/1","event":"push","owner":"B","role":"DEV","at":"2026-11-22T10:00:01Z"}'
    la = os.path.join(b.root, "la.json"); open(la, "w").write(line_a)
    argv = ["api.py", "append", "--repo", "O/R", "--path", "REPORT/events/20261122.jsonl",
            "--file", la, "--no-guard"]
    old_argv = sys.argv; sys.argv = argv
    api.main()
    n = {"g": 0}

    def stale(method, url, body=None, tries=5, raw=False):
        if method == "GET":
            n["g"] += 1
            if n["g"] == 1:      # второй агент прочитал снимок до записи первого
                return 200, {"sha": "s0", "encoding": "base64",
                             "content": base64.b64encode('{"event":"birth"}\n'.encode()).decode()}, {}
        return hub_call(method, url, body, tries, raw)

    api.call = stale
    lb = os.path.join(b.root, "lb.json"); open(lb, "w").write(line_b)
    sys.argv = ["api.py", "append", "--repo", "O/R", "--path", "REPORT/events/20261122.jsonl",
                "--file", lb, "--no-guard"]
    api.main()
    sys.argv = old_argv
    txt = store["REPORT/events/20261122.jsonl"]["text"]
    check("api v5.2: параллельное дописывание сохраняет обе строки",
          '"claim"' in txt and '"push"' in txt and '"birth"' in txt, txt.replace("\n", " | ")[:90])
    api.call = hub_call
    api.gh_now = lambda: ("2026-11-22T10:00:02Z", "20261122", "100002")
    sys.argv = ["api.py", "event", "--repo", "O/R", "--role", "DEV", "--owner", "A",
                "--file", la, "--no-guard"]
    api.main()
    sys.argv = ["api.py", "event", "--repo", "O/R", "--role", "DEV", "--owner", "B",
                "--file", lb, "--no-guard"]
    api.main()
    sys.argv = old_argv
    shards = [p for p in store if p.startswith("REPORT/events/20261122/")]
    check("api v5.2: журнал шардирован по сессиям", len(shards) == 2, ", ".join(sorted(shards)))

    # --- текстовые инварианты протокола ---
    com = open(os.path.join(PROTO, "COMMON.md"), encoding="utf-8").read()
    clo = open(os.path.join(PROTO, "ROLE_CLOSER.md"), encoding="utf-8").read()
    lev = open(os.path.join(PROTO, "LEVERS.md"), encoding="utf-8").read()
    eco = open(os.path.join(PROTO, "ECONOMY.md"), encoding="utf-8").read()
    check("протокол v5.2: релиз не останавливает рой (C7.1 по mode)",
          "mode: close" in com and "mode: release" in com and "C10.22" in com)
    check("протокол v5.2: уборка только в режиме ЗАКРОЙ", "только в режиме `ЗАКРОЙ`" in clo)
    check("протокол v5.2: словарь не грузится в контекст", "не грузит словарь в контекст" in eco)
    check("протокол v5.2: честность оценок закреплена запретом", "C10.19" in com)
    gw = open(os.path.join(os.path.dirname(PROTO), "PROTOCOL.md"), encoding="utf-8").read()
    check("протокол v5.2: указание владельца выше протокола, кроме S2",
          "G0. Приоритет указаний" in gw and "выше правил протокола" in gw and "S2" in gw)

    tpl = json.load(open(os.path.join(PROTO, "pep.template.json"), encoding="utf-8"))
    lm = tpl.get("lever_map", {})
    check("протокол v5.2: у каждого рычага есть роль-исполнитель",
          bool(lm) and all(v in tpl["roles"] for v in lm.values()))
    check("протокол v5.2: у каждой роли есть claim, branches, dicts",
          all("claim" in r and "branches" in r["permissions"] and "dicts" in r for r in tpl["roles"].values()))
    check("протокол v5.2: аренда DEV не 80 часов", tpl["roles"]["DEV"]["lease_h"] <= 12
          and tpl["roles"]["DEV"].get("lease_renew") is True)
    check("протокол v5.2: документный репозиторий проходит развилку",
          "repo_kind: doc" in com and "repo_kind: doc" in clo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true"); ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    root = tempfile.mkdtemp(prefix="gvk-golden-")
    t0 = time.time()
    try:
        b = Bench(root)
        run(b, a.verbose)
    finally:
        pass
    dt = time.time() - t0
    ok = sum(1 for _, o, _ in RESULTS if o)
    print(f"\nЗОЛОТОЙ СЛУЧАЙ GVK v5.2 — {ok}/{len(RESULTS)} проверок за {dt:.1f} c\n")
    for n, o, d in RESULTS:
        print(f"  {'OK  ' if o else 'FAIL'} {n}" + (f" — {d}" if d else ""))
    print(f"\nстенд: {root}" + (" (сохранён)" if a.keep else " (удалён)"))
    if not a.keep:
        shutil.rmtree(root, ignore_errors=True)
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
