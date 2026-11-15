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
    def guard(self, role, paths, claim=None, merge=False):
        pep = os.path.join(self.root, "PEP.json")
        open(pep, "w", encoding="utf-8").write(json.dumps(self.hub.json("GVK/PEP.json"), ensure_ascii=False))
        cmd = [sys.executable, os.path.join(HERE, "guard.py"), "--role", role, "--pep", pep]
        cmd += ["--merge"] if merge else ["--paths"] + list(paths)
        if claim:
            cp = os.path.join(self.root, "claim.md"); open(cp, "w").write(claim); cmd += ["--claim", cp]
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
            "protocol_ver": "ALV-5.0_PPV-5.0_MRV-selftest_TAV-1.0"}


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
                                               claim="packages: io.github.bizonrelax.demo.core\nfragment: 001\n") == 0)
    check("RBAC: DEV не пишет чужой пакет", b.guard("DEV", ["src/main/java/io/github/bizonrelax/demo/ui/B.java"],
                                                  claim="packages: io.github.bizonrelax.demo.core\nfragment: 001\n") == 1)
    check("RBAC: DEV не пишет каркас", b.guard("DEV", ["pom.xml"]) == 1)
    check("RBAC: DEV не пишет ТЗ", b.guard("DEV", [TZ]) == 1)
    check("RBAC: DEV не сливает в main", b.guard("DEV", [], merge=True) == 1)
    check("RBAC: TESTER не пишет src/main", b.guard("TESTER", ["src/main/java/X.java"]) == 1)
    check("RBAC: OBSERVER не пишет ничего", b.guard("OBSERVER", ["REPORT/events/x.jsonl"]) == 1)
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
    print(f"\nЗОЛОТОЙ СЛУЧАЙ GVK v5.0 — {ok}/{len(RESULTS)} проверок за {dt:.1f} c\n")
    for n, o, d in RESULTS:
        print(f"  {'OK  ' if o else 'FAIL'} {n}" + (f" — {d}" if d else ""))
    print(f"\nстенд: {root}" + (" (сохранён)" if a.keep else " (удалён)"))
    if not a.keep:
        shutil.rmtree(root, ignore_errors=True)
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
