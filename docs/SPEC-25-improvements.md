# SPEC — 25 Verbesserungspunkte (Tier 2/3)

Status: **DRAFT — wartet auf Freigabe**
Datum: 2026-08-04
Kontext: Code-Analyse vom 2026-08-04 — 17 Module, 3.216 Zeilen, 223 Tests grün,
27 Ruff-Fehler, 0 Mypy-Fehler. Alle 25 in der Analyse genannten Punkte werden
hier in executable acceptance criteria übersetzt.

Klassifizierung:
- **Tier 3** (Sicherheit, Datenverlust, Auth, unvertrauter Code): Punkte #1, #2, #3, #5, #6, #8, #23
- **Tier 2** (Bugfixes, kleine Features, Refactors mit Verhaltensänderung): Rest

## Setup-Plan (Wird mit Spec-Freigabe autorisiert)

**Werkzeuge (bereits vorhanden):** pytest, pytest-cov, pytest-randomly, ruff, mypy, uv.
**Keine neuen Dependencies für Kern-Work.** Optionale Extra-Gruppe `[project.optional-dependencies.rag]`
wird neu in `pyproject.toml` angelegt (enthält `lancedb`, `sentence-transformers`) —
wird **nicht** in den default-Environment installiert, nur deklarativ. `rag_manager.py`
bleibt lazy-import, Tests mocken. Jede andere neue Abhängigkeit ist unten explizit
mit Begründung aufgeführt — es gibt keine.

**Git:** Repo existiert. Checkpoint-Commits nach jedem GREEN/REFACTOR-Schritt,
wie in AGENTS.md vorgesehen. Cadence: pro Behaviour-Cluster (A/B/C/D/E) ein
Commit. Branch: `master` bleibt, Arbeit erfolgt auf neuem Branch `fix/25-improvements`.

**Dateien, die der Gauntlet anlegt:**
- `tests/test_path_traversal.py` (neu, für #1)
- `tests/test_api_key_permissions.py` (neu, für #2)
- `tests/test_sandbox_hardening.py` (neu, für #3)
- `tests/test_skill_writer_revise.py` (neu, für #4)
- `tests/test_coding_agent_returncode.py` (neu, für #5)
- `tests/test_sandbox_fallback.py` (neu, für #6)
- `tests/test_llm_model_config.py` (neu, für #7)
- `tests/test_pipeline_consolidation.py` (neu, für #8)
- `tests/test_agent_caching.py` (neu, für #9)
- `tests/test_intent_reload.py` (neu, für #10)
- `tests/test_singleton_thread_safety.py` (neu, für #11)
- `tests/test_registry_syspath.py` (neu, für #12)
- `tests/test_db_upsert.py` (neu, für #13)
- `tests/test_cli_api_url.py` (neu, für #14)
- `tests/test_rag_schema.py` (neu, für #15)
- `tests/test_wigolo_framing.py` (neu, für #16)
- `tests/test_sandbox_stderr.py` (neu, für #17)
- `tests/test_stub_function_name.py` (neu, für #18)
- `tests/test_dead_code_removed.py` (neu, für #19)
- `tests/test_ruff_clean.py` (neu, für #20)
- `tests/test_pyproject_deps.py` (neu, für #21)
- `tests/test_readme_no_dupes.py` (neu, für #22)
- `tests/test_logging.py` (neu, für #23)
- `tests/test_llm_timeouts.py` (neu, für #24)
- `tests/test_llm_json_validation.py` (neu, für #25)
- `scripts/gauntlet_25.sh` (neu, Single-Entry für alle Layer)

**Source-Identifikation:** Commit-SHA wird in EVIDENCE festgehalten.

---

## A. Kritische Bugs & Sicherheitslücken (Tier 3)

### #1 — Pfad-Traversal bei Skill-Promotion

**Problem:** `skill_writer.py:322` und `promotion.py:58` bauen den Skill-Pfad als
`Path(self._skills_dir) / f"{skill_name}.py"` ohne Prüfung. Ein LLM-generiertes
`skill_name = "../evil"` schreibt außerhalb von `skills/`. `SkillVersionManager._skill_path`
(safety.py:292) hat bereits einen Guard — derselbe Schutz fehlt an den Promote-Pfaden.

**Failure-Model:**
- Modus 1: `skill_name = "../etc/cron.d/evil"` → Code-Datei landet außerhalb des Skills-Dirs.
- Modus 2: `skill_name = "../../" + beliebiger Pfad` → Überschreiben von Source-Dateien.
- Modus 3: Absolute Pfade (`skill_name = "/tmp/x"`) → `Path / "/tmp/x"` resolves to `/tmp/x`.

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: Skill-Name mit Pfad-Traversal wird abgelehnt
  Given ein SkillPromoter mit skills_dir="/tmp/skills_x"
  When promote(skill_name="../evil", code="pass") aufgerufen wird
  Then PromotionResult.success is False
  And "traversal" in PromotionResult.error.lower()
  And die Datei "/tmp/evil.py" existiert nicht

Scenario: Skill-Name mit absolutem Pfad wird abgelehnt
  Given ein SkillPromoter
  When promote(skill_name="/tmp/abs", code="pass") aufgerufen wird
  Then PromotionResult.success is False
  And "/tmp/abs.py" existiert nicht

Scenario: Gültiger Skill-Name funktioniert weiterhin (Regression)
  Given ein SkillPromoter mit skills_dir=tmpdir
  When promote(skill_name="my_skill", code="def my_skill(): pass")
  Then PromotionResult.success is True
  And (tmpdir/"my_skill.py").exists() is True

Scenario: SkillWriter._promote mit Traversal wird abgelehnt
  Given einen SkillWriter mit skills_dir=tmpdir
  When _promote(skill_name="../bad", code="pass")
  Then PromoteResult.success is False
```

**Implementation-Hint:** `_safe_skill_path(skills_dir, skill_name) -> Path | None`,
gibt `None` zurück, wenn `candidate.relative_to(base)` ValueError wirft. Beide
Promoter und SkillWriter nutzen dieselbe Hilfsfunktion. Bei `None` wird
`PromotionResult(success=False, error="path traversal detected")` zurückgegeben.

**Negativ-Invariante:** Bestehende `tests/test_promotion.py` und
`tests/test_skill_writer.py` bleiben grün bis auf neu hinzukommende Assertions.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage auf geänderten Zeilen,
mutation (manual: flip `relative_to`-Check → muss von neuem Test gekillt werden).

---

### #2 — API-Key-Datei-Permissions

**Problem:** `config.py:39` schreibt den generierten API-Key mit
`key_file.write_text(new_key)` ohne `chmod 600`. Die Datei liegt world-readable
auf der Platte.

**Failure-Model:**
- Andere User auf dem System können `/home/.../data/.api_key` lesen → API-Zugang.
- Backup-Systeme ziehen die Datei im Klartext.

**Acceptance Criteria:**

```gherkin
Scenario: Neue Key-Datei hat Mode 0o600
  Given ein leeres data_dir und keine existierende Key-Datei
  When _load_or_generate_api_key() aufgerufen wird
  Then die Datei data/.api_key existiert
  And stat.S_IMODE(os.stat(path).st_mode) == 0o600

Scenario: Vorhandene Key-Datei mit zu offenen Permissions wird korrigiert
  Given eine existierende Key-Datei mit Mode 0o644
  When _load_or_generate_api_key() aufgerufen wird
  Then die Datei hat Mode 0o600 nach dem Aufruf

Scenario: Env-Key überschreibt Datei (Regression)
  Given ENV AGNO_API_KEY="env-secret"
  And keine Datei wird angefasst
  When _load_or_generate_api_key()
  Then Rückgabe == "env-secret"
  And keine Datei wurde erzeugt
```

**Implementation:** `os.chmod(key_file, 0o600)` nach `write_text`, und beim
Lesen einer existierenden Datei Mode prüfen und korrigieren. `umask` kann
nicht vertraut werden.

**Negativ-Invariante:** Bestehende `tests/test_app.py` und Config-Tests bleiben grün.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation (manual: chmod
weglassen → Test "Mode 0o600" kkillt es).

---

### #3 — Docker-Sandbox-Härtung

**Problem:** `sandbox.py:149` setzt `network_mode="none"`, `mem_limit`, `cpu_quota`,
aber es fehlen: `read_only=True`, `pids_limit`, `cap_drop=["ALL"]`,
`security_opt=["no-new-privileges"]`, `tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"}`.

**Failure-Model:**
- Container-Shell-Code schreibt Payload nach `/tmp` und führt ihn aus → `tmpfs noexec` verhindert.
- Skill nutzt `socket` nach Netztrennung trotzdem via `cap_drop=ALL` → keine Raw-Sockets.
- Fork-Bomb → `pids_limit`.
- Skill schreibt nach `/etc/passwd` o.ä. → `read_only=True`.

**Acceptance Criteria:**

```gherkin
Scenario: Container wird mit harten Isolations-Flags erzeugt
  Given einen SandboxRunner mit gemocktem docker client
  When run_code("print('hi')")
  Then client.containers.run wurde aufgerufen mit:
    | Parameter        | Wert                                    |
    | network_mode     | "none"                                  |
    | mem_limit        | "256m"                                  |
    | cpu_quota        | 50000                                   |
    | read_only        | True                                    |
    | pids_limit       | (int > 0)                               |
    | cap_drop         | ["ALL"]                                 |
    | security_opt     | ["no-new-privileges"]                   |
    | tmpfs            | enthält "/tmp" mit "noexec,nosuid,size" |

Scenario: tmpfs-Flag enthält noexec
  Given SandboxRunner
  When run_tests(test_code="...", skill_code="...")
  Then der run()-Aufruf hat tmpfs mit "noexec" im /tmp-Eintrag

Scenario: Bisheriger Code läuft weiterhin durch (Regression)
  Given SandboxRunner mit Mock
  When run_code("x=1")
  Then exit_code == 0 (gemockt) und keine Exception
```

**Implementation:** Erweite die `_exec_container`-Signatur um ein Klassenkonstanten-Set
`_HARDENING = {"read_only": True, "pids_limit": 64, "cap_drop": ["ALL"],
"security_opt": ["no-new-privileges"], "tmpfs": {"/tmp": "rw,noexec,nosuid,size=64m"}}`
und merge in jeden `containers.run()`-Call.

**Negativ-Invariante:** `tests/test_sandbox.py` bleibt grün (Mocks müssen neue
kwargs tolerieren — ggf. Mocks auf `**kwargs` umstellen, aber keine Assertion
wird gelöscht).

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation (manual: `read_only`
weglassen → Test "read_only=True" killt es).

---

### #4 — `_revise_code`-Aufruf kaputt

**Problem:** `skill_writer.py:271`:
```python
revised = self._revise_code(code, stderr + stdin_to_error(stdout), spec_name=code)
```
- `spec_name=code` übergibt den Code als Spec-Namen.
- `_revise_code` nimmt `spec_name` entgegen, nutzt es nicht → toter Parameter.
- `stdin_to_error(stdout)` ist No-Op.
- Revidierter Code wird nicht safety-gecheckt.
- `tests` wird nicht revidiert.

**Acceptance Criteria:**

```gherkin
Scenario: _revise_code wird mit korrekten Argumenten aufgerufen
  Given einen SkillWriter mit gemocktem LLM
  And sandbox.run_tests gibt exit_code=1, stderr="ImportError" zurück
  When _run_tdd(code, tests) aufgerufen wird
  Then _revise_code wurde aufgerufen mit:
    | Parameter     | Wert                            |
    | code          | (ursprünglicher Code-String)    |
    | error_trace   | enthält "ImportError"           |
  And der spec_name-Parameter ist nicht mehr Bestandteil der Signatur

Scenario: Revidierter Code wird erneut safety-gecheckt
  Given SkillWriter, sandbox gibt einmal Fail, dann Pass
  And _revise_code gibt Code mit "import os" zurück
  When _run_tdd aufgerufen
  Then die Rückgabe hat success=False
  And "safety" in error.lower() ODER safety_issues ist nicht leer

Scenario: stdin_to_error-Funktion ist entfernt
  Given die Quelle von skill_writer.py
  When nach "stdin_to_error" gesucht wird
  Then kein Match in src/

Scenario: Kein Spec-Name-Parameter mehr in _revise_code
  Given die Signatur von SkillWriter._revise_code
  When inspiziert
  Then hat genau 2 Parameter: code, error_trace
```

**Implementation:**
1. `stdin_to_error` löschen.
2. `_revise_code(self, code, error_trace) -> str | None` — nur 2 Parameter.
3. Im Retry-Loop: `revised = self._revise_code(code, stderr + "\n" + stdout)`,
   danach `safety = self._safety_check(revised)` → wenn fail, Loop abbrechen
   mit `TDDResult(success=False, error="revised code failed safety")`.
4. `tests` unververändert lassen (die Spec sagt ausdrücklich nur Code wird revidiert —
   Test-Revision wäre ein separates Behaviour).

**Negativ-Invariante:** `tests/test_skill_writer.py` bleibt bis auf neu
hinzukommende Assertions grün.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation (manual: safety-check
auf revised weglassen → Test "safety-gecheckt" killt es).

---

### #5 — CLI-Return-Code-Bug in `coding_agent.py`

**Problem:** `coding_agent.py:380`:
```python
if proc.returncode != 0:
    return proc.stderr or proc.stdout or ""
```
Bei Fehler wird stderr als Output zurückgegeben. `create_skill` prüft nur
`raw.strip()` → nicht-leerer stderr wird als Code-Output interpretiert.

**Failure-Model:** CLI-Aufruf schlägt fehl, stderr enthält "command not found"
→ wird als "Skill-Code" promotet → Skill-Datei enthält Shell-Fehlermeldung.

**Acceptance Criteria:**

```gherkin
Scenario: CLI-Fehler returncode != 0 propagiert als Exception
  Given einen CodingAgent mit gemocktem subprocess.run
  And returncode=1, stderr="boom", stdout=""
  When _call_cli(prompt, "claude") aufgerufen
  Then eine Exception wird geworfen (RuntimeError oder subprocess.CalledProcessError)
  And die Exception-Nachricht enthält "boom"

Scenario: Leerer Output bei returncode=0 wird als Exception propagiert
  Given returncode=0, stdout=""
  When _call_cli aufgerufen
  Then Exception mit Hinweis auf "empty output"

Scenario: Erfolg mit nicht-leerem stdout (Regression)
  Given returncode=0, stdout="def foo(): pass"
  When _call_cli aufgerufen
  Then Rückgabe == "def foo(): pass"

Scenario: create_skill fällt durch bei CLI-Fehler
  Given alle CLIs liefern returncode=1
  When create_skill(spec) aufgerufen
  Then CodingResult.success is False
  And CodingResult.code == ""  (kein stderr als Code)
```

**Implementation:** `_call_cli` raiset `subprocess.CalledProcessError` bei
`returncode != 0`, `ValueError("empty output")` bei leerem stdout. `create_skill`
und `revise_code` haben bereits try/except, die dann in Fallback laufen.

**Negativ-Invariante:** `tests/test_coding_agent.py` wird angepasst — einige
Tests setzen auf das alte Verhalten (stderr als Output). Das ist ein
Verhaltenswechsel und gehört in den Spec; diese Tests werden explizit als
"behaviour change" markiert und ihre Assertions verschärft, nicht gelöscht.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation (manual: Exception
durch `return ""` ersetzen → Test "create_skill fällt durch" killt es).

---

### #6 — Sandbox-Fallback lügt

**Problem:** `sandbox.py:127` Kommentar: "fall back to the base image —
run_tests will use pip install with network." Aber `run_tests` nutzt
`network_mode="none"` → pip schlägt fehl, Tests hängen.

**Acceptance Criteria:**

```gherkin
Scenario: Build-Fehler wird als harter Fehler gemeldet, nicht stiller Fallback
  Given SandboxRunner mit gemocktem client
  And client.images.build wirft Exception
  When _ensure_test_image() aufgerufen
  Then eine RuntimeError wird geworfen mit "sandbox image build failed"

Scenario: Bereits existierendes Image wird genutzt (Regression)
  Given client.images.get("toolkinetik-sandbox:latest") gibt Image zurück
  When _ensure_test_image()
  Then Rückgabe == "toolkinetik-sandbox:latest" und kein build

Scenario: run_tests mit Build-Fehler propagiert
  Given Runner, _ensure_test_image wirft RuntimeError
  When run_tests(...)
  Then Rückgabe hat exit_code != 0 und stderr enthält "image build failed"
```

**Implementation:** `_ensure_test_image` wirft `RuntimeError` statt still zu
fallen; `_exec_container`/`run_tests` fangen strukturiert und geben dict mit
`exit_code=-1, stderr="..."` zurück (bisheriges Schema beibehalten, aber mit
echter Meldung).

**Negativ-Invariante:** `tests/test_sandbox.py` muss angepasst werden — bisherige
Tests, die den Fallback expecten, werden explizit umgeschrieben. Diese Tests
sind "behaviour change", keine bloßen Regressionen; Änderung im Spec vermerkt.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation.

---

### #7 — LLM-Modell hardcoded

**Problem:** `intent.py:108`, `skill_writer.py:216,404,467` verwenden
konstant `model="gpt-4o"`. `settings.OPENAI_MODEL` aus `.env` wirkt nicht.

**Acceptance Criteria:**

```gherkin
Scenario: IntentEngine nutzt settings.OPENAI_MODEL
  Given Settings mit OPENAI_MODEL="llama3"
  And IntentEngine mit gemocktem llm
  When analyze("hello")
  Then der LLM-Aufruf hat model="llama3"

Scenario: SkillWriter._generate_code nutzt settings.OPENAI_MODEL
  Given Settings OPENAI_MODEL="llama3"
  And SkillWriter mit gemocktem llm
  When _generate_code(spec)
  Then der LLM-Aufruf hat model="llama3"

Scenario: SkillWriter._llm_classify nutzt settings.OPENAI_MODEL
  Given Settings OPENAI_MODEL="phi3"
  When generate_spec("...") mit LLM
  Then Aufruf hat model="phi3"

Scenario: SkillWriter._revise_code nutzt settings.OPENAI_MODEL
  Given Settings OPENAI_MODEL="mistral"
  When _revise_code(...) mit LLM
  Then Aufruf hat model="mistral"

Scenario: Default unverändert (Regression)
  Given keine .env, OPENAI_MODEL="gpt-4o" (Default)
  When IntentEngine.analyze
  Then model="gpt-4o"
```

**Implementation:** In jeder der 4 Stellen `model=settings.OPENAI_MODEL`.
`get_settings()` ist cached — an den Stellen einzubinden.

**Negativ-Invariante:** Bestehende Tests, die `model="gpt-4o"` asserten,
werden auf `settings.OPENAI_MODEL` umgestellt — behaviour change im Spec
vermerkt. Keine Assertion wird gelöscht.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation (manual:
hardcoded "gpt-4o" einbauen → Test "nutzt settings" killt es).

---

### #8 — Zwei parallele TDD/Promotion-Pipelines konsolidieren

**Problem:**
- `SkillWriter._run_tdd`/`_promote` (skill_writer.py) vs. `TDDLoop` (tdd_loop.py) + `SkillPromoter` (promotion.py).
- `PromoteResult` (skill_writer.py:33) vs. `PromotionResult` (promotion.py:21) — zwei identische Dataclasses.
- `SkillCreationOrchestrator` (intent.py:211) vs. `SkillWriter` — dieselbe Pipeline doppelt.

**Entscheidung:** `SkillWriter` ist neuer, vollständiger und wird vom `app.py`
genutzt. Legacy-Pipeline wird gelöscht, `SkillWriter` delegiert an die
losgelösten Klassen `TDDLoop` und `SkillPromoter`, um Wiederverwendung zu
erhalten. D.h.:
- `PromoteResult` (skill_writer.py) wird entfernt, `SkillWriter` nutzt `PromotionResult` (promotion.py).
- `TDDResult` (skill_writer.py) wird entfernt, `SkillWriter` nutzt `TDDResult` (tdd_loop.py).
- `SkillWriter._run_tdd` delegiert an `TDDLoop.run`.
- `SkillWriter._promote` delegiert an `SkillPromoter.promote`.
- `IntentDetector` und `SkillCreationOrchestrator` (intent.py) werden entfernt.
- `intent.py` wird um `SkillCreationOrchestrator` und `IntentDetector` gesäubert.

**Acceptance Criteria:**

```gherkin
Scenario: SkillWriter nutzt SkillPromoter
  Given die Quelle von skill_writer.py
  When nach "class PromoteResult" gesucht wird
  Then kein Match in src/

Scenario: SkillWriter nutzt TDDLoop
  Given skill_writer.py
  When nach "class TDDResult" gesucht wird
  Then kein Match in src/

Scenario: IntentDetector entfernt
  Given src/toolkinetik/intent.py
  When nach "class IntentDetector" gesucht
  Then kein Match

Scenario: SkillCreationOrchestrator entfernt
  Given src/toolkinetik/intent.py
  When nach "class SkillCreationOrchestrator" gesucht
  Then kein Match

Scenario: SkillWriter.write_skill verhält sich unverändert (End-to-End-Regression)
  Given einen SkillWriter mit mocks für llm/sandbox
  When write_skill("create fibonacci")
  Then SkillWriterResult.success == (bisheriger Erfolgsfall)

Scenario: Importe von IntentDetector/Orchestrator schlagen fehl
  Given `from toolkinetik.intent import IntentDetector`
  When importiert
  Then ImportError

Scenario: TDDLoop und SkillPromoter bleiben einzeln nutzbar
  Given TDDLoop(sandbox).run(spec, code, tests)
  Then gibt TDDResult (aus tdd_loop) zurück
  And SkillPromoter().promote(...) gibt PromotionResult (aus promotion) zurück
```

**Negativ-Invariante:**
- `tests/test_skill_writer.py` wird so umgeschrieben, dass es `PromotionResult`/`TDDResult`
  aus den kanonischen Modulen importiert. Assertions zu Erfolg/Fehler bleiben erhalten.
- `tests/test_intent.py` (Legacy IntentDetector-Tests) wird gelöscht — Verhaltenswechsel
  explizit im Spec. Die Tests für `IntentEngine` (test_intent_engine.py) bleiben.
- `tests/test_tdd_loop.py`, `tests/test_promotion.py` bleiben unverändert.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation, **API-compat**:
expliziter Check, dass `SkillWriter.write_skill`-Verhalten identisch bleibt (5
Szenarien in `test_pipeline_consolidation.py`).

---

## B. Architektur-Probleme (Tier 2)

### #9 — Agent wird pro WebSocket-Message neu erstellt

**Problem:** `app.py:147` ruft `create_agent()` pro Nachricht auf. Lädt alle
Tools, baut OpenAI-Client, instanziiert Agno-Agent — teuer.

**Acceptance Criteria:**

```gherkin
Scenario: Agent wird nur einmal erzeugt
  Given app.py, gemockter create_agent
  When 3 Nachrichten über WebSocket geschickt
  Then create_agent wurde genau 1x aufgerufen

Scenario: Nach reload-skills wird Agent invalidiert
  Given Agent gecacht
  When POST /api/reload-skills
  And nächste WS-Nachricht
  Then create_agent wurde erneut aufgerufen (insgesamt 2x)

Scenario: Erster Aufruf erzeugt Agent (Regression)
  Given kein Cache
  When WS-Nachricht
  Then Agent wurde erzeugt
```

**Implementation:** `_agent: Agent | None = None`, `get_agent()`-Singleton wie
`get_intent_engine`. Bei `/api/reload-skills` Cache invalidieren:
`global _agent; _agent = None`.

**Negativ-Invariante:** Bestehende WS-Tests bleiben grün.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation.

---

### #10 — `IntentEngine.available_tools` triggert Full-Reload

**Problem:** `intent.py:60` ruft `registry.get_tools()` auf → re-executed alle
Skill-Module bei jeder `analyze()`. Teuer und gefährdet Seiteneffekte.

**Acceptance Criteria:**

```gherkin
Scenario: available_tools liest aus registered_tools ohne Reload
  Given Registry mit 2 registrierten Tools
  And spy auf registry.get_tools
  When IntentEngine.available_tools()
  Then get_tools wurde 0x aufgerufen
  And Rückgabe enthält beide Tool-Namen

Scenario: analyze liest Tools ohne Reload
  Given IntentEngine, Registry mit Tools
  When analyze("hello")
  Then registry.get_tools wurde 0x aufgerufen

Scenario: Bei leerer Registry wird einmalig nachgeladen
  Given registry.registered_tools == {}
  When available_tools()
  Then get_tools wurde 1x aufgerufen

Scenario: SkillListe bleibt korrekt (Regression)
  Given Registry mit weather_skill, math_skill
  When available_tools()
  Then Rückgabe sortiert == ["math_skill", "weather_skill"] o.ä.
```

**Implementation:** `available_tools` nutzt `registry.registered_tools`, lädt
nur nach, wenn die leer ist (defensiv).

**Negativ-Invariante:** `tests/test_intent_engine.py` wird angepasst — bisherige
Tests, die `get_tools`-Aufruf expecten, werden auf `registered_tools` umgestellt.
Behaviour change im Spec vermerkt.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation.

---

### #11 — Global-Mutable-Singletons nicht thread-safe

**Problem:** `app.py:51-82` `global _x; if _x is None` ohne Lock. FastAPI
läuft async/multi-worker.

**Acceptance Criteria:**

```gherkin
Scenario: Singleton-Factory ist thread-safe
  Given 10 Threads, die gleichzeitig get_intent_engine aufrufen
  When alle starten
  Then genau eine IntentEngine-Instanz existiert (id(identical))

Scenario: Gleiche Garantie für get_skill_writer
  Given 10 Threads
  When gleichzeitig get_skill_writer
  Then genau eine Instanz

Scenario: Gleiche Garantie für get_rag_manager
  Given 10 Threads
  When gleichzeitig get_rag_manager
  Then genau eine Instanz

Scenario: Concurrent reload + get-Aufruf deadlock-free
  Given reload_skills und get_intent_engine concurrent
  When 100x wiederholt
  Then kein Deadlock, alle Aufrufe kehren zurück
```

**Implementation:** `threading.Lock`-guarded Singleton. Alternativ
`functools.lru_cache` auf Factory (maxsize=1).

**Negativ-Invariante:** Bestehende `tests/test_app.py` bleibt grün.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation, **stress-test**
(100 concurrently-spawned Threads).

---

### #12 — `registry.py` mutiert `sys.path` global

**Problem:** `sys.path.insert(0, self.skills_dir)` pro Instanz. Mehrere
Registrys verschmutzen `sys.path`. Module gleichen Namens werden in
`sys.modules` ersetzt, alte Referenzen verweisen weiter auf alten Code.

**Acceptance Criteria:**

```gherkin
Scenario: Registry fügt skills_dir nur einmal zu sys.path hinzu
  Given sys.path ohne skills_dir
  When DynamicToolRegistry(tmpdir1) erzeugt
  Then skills_dir 1x in sys.path

Scenario: Zweite Registry mit anderem Dir fügt hinzu
  Given Registry(tmpdir1)
  When DynamicToolRegistry(tmpdir2)
  Then tmpdir1 und tmpdir2 jeweils 1x in sys.path

Scenario: Skill-Module erhalten eindeutigen Namen mit Prefix
  Given Registry(tmpdir) mit foo.py
  When get_tools()
  Then sys.modules enthält "toolkinetik_skills.foo" (oder ähnlich)
  And sys.modules enthält NICHT "foo" als nackten Key

Scenario: Hot-Reload invalidiert Caches
  Given geladenes foo.py mit Version 1
  When foo.py auf Disk geändert, get_tools() erneut
  Dann importlib.invalidate_caches() wurde aufgerufen (spy)
  And die neue Version ist aktiv (Function-Source enthält neuen Code)

Scenario: Bestehende Skills laden weiterhin (Regression)
  Given skills/weather_skill.py und math_skill.py
  When get_tools()
  Then beide Tools vorhanden, aufrufbar
```

**Implementation:**
- Modul-Präfix `toolkinetik_skills_` für geladene Module.
- `importlib.invalidate_caches()` vor jedem Reload.
- `sys.path.insert` nur, wenn nicht vorhanden.

**Negativ-Invariante:** `tests/test_registry.py` wird angepasst — Tests, die
Modulnamen ohne Prefix expecten, werden umgeschrieben. Behaviour change im Spec.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation, **isolation-test**
(zwei Registrys mit gleichem Skill-Namen in unterschiedlichen Dirs → keine
Kollision).

---

## C. Logik- & Korrektheitsfehler (Tier 2)

### #13 — `db.py:INSERT OR REPLACE` zerstört `created_at`

**Acceptance Criteria:**

```gherkin
Scenario: Re-Promotion eines Skills erhält created_at
  Given SkillStore mit registriertem "foo" (created_at = T0)
  When register_skill("foo", ...) erneut aufgerufen
  Then get_skill("foo")["created_at"] == T0
  And get_skill("foo")["updated_at"] > T0

Scenario: Neue Skill bekommt created_at gesetzt
  Given leere DB
  When register_skill("bar", ...)
  Then get_skill("bar")["created_at"] is not None
  And get_skill("bar")["updated_at"] == created_at

Scenario: Update-Version ändert nur updated_at
  Given Skill "foo" mit created_at=T0, updated_at=T1
  When update_version("foo", "2.0.0")
  Then created_at == T0 unverändert
  And updated_at > T1
```

**Implementation:** `INSERT INTO skills ... ON CONFLICT(name) DO UPDATE SET
function=excluded.function, description=excluded.description, signature=...,
version=excluded.version, status=excluded.status, created_by=excluded.created_by,
git_commit=excluded.git_commit, updated_at=excluded.updated_at` — `created_at`
bleibt unangetastet.

**Negativ-Invariante:** `tests/test_db.py` wird erweitert — bestehende
Tests, die `created_at == updated_at` oder `created_at`-Überschreibung
asserten, werden explizit umgeschrieben. Behaviour change im Spec vermerkt.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation.

---

### #14 — `cli.py` ignorierte konfigurierte API-URL

**Acceptance Criteria:**

```gherkin
Scenario: CLI nutzt TOOLKINETIK_API_URL
  Given ENV TOOLKINETIK_API_URL="http://remote:9000"
  When `cli health` aufgerufen
  Then httpx.get wurde mit "http://remote:9000/api/health" aufgerufen

Scenario: Default localhost bleibt (Regression)
  Given keine ENV
  When `cli health`
  Then httpx.get URL startet mit "http://localhost:8000"

Scenario: skills list nutzt API_URL
  Given ENV TOOLKINETIK_API_URL="http://x:1"
  When `cli skills list`
  Then httpx.get URL == "http://x:1/api/skills"

Scenario: skills reload nutzt API_URL
  Given ENV TOOLKINETIK_API_URL="http://x:1"
  When `cli skills reload`
  Then httpx.post URL == "http://x:1/api/reload-skills"
```

**Implementation:** `API_BASE = settings.TOOLKINETIK_API_URL` statt hardcoded.

**Negativ-Invariante:** `tests/test_cli.py` wird angepasst — Mocks, die
 hardcoded localhost expecten, werden auf konfigurierbare URL umgestellt.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation.

---

### #15 — `rag_manager.py` — LanceDB-Schema kaputt

**Problem:** `"{embedding}"` ist ein String-Literal, kein Typ. LanceDB-API
erwartet `pa.list_(pa.float32(), dim=384)`. Außerdem fehlen `lancedb`,
`sentence-transformers` in `pyproject.toml`.

**Acceptance Criteria:**

```gherkin
Scenario: Schema-Definition nutzt pyarrow-Typen
  Given RagManager, gemocktes lancedb mit echtem schema-Aufruf-Recording
  When initialize()
  Then lancedb.create_table erhielt ein Schema, dessen vector-Spalte
    vom Typ pa.list_(pa.float32(), 384) ist
  And text-Spalte ist pa.string()
  And source-Spalte ist pa.string()

Scenario: pyproject.toml enthält rag-Extra
  Given pyproject.toml
  When nach "lancedb" gesucht
  Then Match in [project.optional-dependencies].rag
  And Match für "sentence-transformers" in derselben Sektion

Scenario: Bei fehlendem lancedb degradiert graceful
  Given monkeypatch sys.modules: lancedb nicht importierbar
  When RagManager.search("...")
  Then Rückgabe == [] und is_ready == False

Scenario: Embedding-Dimension 384 (all-MiniLM-L6-v2)
  Given das Schema
  When inspiziert
  Dann vector-Spalte hat dim=384
```

**Implementation:**
- `import pyarrow as pa` in `rag_manager.py`, Schema als
  `pa.schema([("vector", pa.list_(pa.float32(), 384)), ("text", pa.string()),
  ("source", pa.string())])` und `lancedb.create_table("...", schema=schema)`.
- `pyproject.toml` erhält `[project.optional-dependencies].rag = ["lancedb", "sentence-transformers"]`.
- Tests mocken `lancedb` und `SentenceTransformer`.

**Negativ-Invariante:** Bestehende Tests unberührt, weil das Modul bisher
ungetestet war. Neue `test_rag_schema.py`.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation, **property-test**
(`schema.names == {"vector", "text", "source"}`, round-trip dict → table → list).

---

### #16 — `setup_mcp.py:_WigoloClient._call` ist fragil

**Problem:** Liest genau eine Zeile. MCP JSON-RPC sendet aber Header,
Notifications, multi-line-Payloads. Kein Handshake, kein Framing.

**Acceptance Criteria:**

```gherkin
Scenario: _WigoloClient führt initialize-Handshake durch
  Given gemocktes subprocess.Popen mit stdout, das erst "initialize"-Response, dann "initialized"-Notification sendet
  When _WigoloClient._ensure_running() (oder _call("research", ...))
  Then eine "initialize"-JSON-RPC-Nachricht wurde gesendet
  And eine "notifications/initialized"-Antwort wurde gesendet

Scenario: _call toleriert Notifications vor der eigentlichen Response
  Given stdout sendet: notification, dann {"id":1, "result":{...}}
  When _call("research", ...)
  Dann Rückgabe == {...} (Result der id=1)
  And notification wurde ignoriert

Scenario: Content-Length-Framing wird unterstützt
  Given stdout sendet: "Content-Length: 42\r\n\r\n{...json...}"
  When _call(...)
  Then der JSON-Body wurde korrekt extrahiert

Scenario: time.sleep(1.0) durch Polling ersetzt
  Given die Quelle von setup_mcp.py
  When nach "time.sleep" gesucht
  Then kein Match in der _ensure_running-Methode (anderswo ok)

Scenario: Stub-Fallback bei Start-Fehler (Regression)
  Given uvx fehlt
  When WigoloMCPToolkit.research("...")
  Then Rückgabe enthält "wigolo server unavailable"
```

**Implementation:**
- Handshake: `initialize` senden, auf Response warten,
  `notifications/initialized` senden.
- Framing: HTTP-Style-Header `Content-Length: N` parsen, dann N Bytes lesen.
  Falls kein Header: zeilenbasiert mit Skip von Notifications (ohne `id`).
- `time.sleep(1.0)` ersetzen durch Polling mit Timeout (max 5s, 100ms-Schritte).

**Negativ-Invariante:** `tests/test_setup_mcp.py` wird erweitert; bestehende
Stub-Tests bleiben.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation, **property-test**
(round-trip: JSON-RPC-Request → Response → Result).

---

### #17 — `sandbox.py:_decode_logs` merged stdout+stderr

**Problem:** `stderr` im Ergebnis immer `""`. Echte Fehlermeldungen gehen verloren.

**Acceptance Criteria:**

```gherkin
Scenario: stdout und stderr werden getrennt ausgegeben
  Given SandboxRunner mit gemocktem Container
  And container.logs(stdout=True, stderr=False) returns b"out-line"
  And container.logs(stdout=False, stderr=True) returns b"err-line"
  When _exec_container(...)
  Then result["stdout"] == "out-line"
  And result["stderr"] == "err-line"

Scenario: tdd_loop nutzt echtes stderr
  Given sandbox.run_tests returns {"stderr": "ImportError: no module", "stdout": ""}
  When TDDLoop.run(...)
  And failure
  Then error_msg enthält "ImportError"

Scenario: Bestehende Schnittstelle erhalten (Regression)
  Given _exec_container
  When aufgerufen
  Then Rückgabe hat Schlüssel {"exit_code", "stdout", "stderr"}
```

**Implementation:** `_exec_container` ruft `container.logs(stdout=True, stderr=False)`
und `container.logs(stdout=False, stderr=True)` getrennt auf. `_decode_logs`
bleibt für beide.

**Negativ-Invariante:** `tests/test_sandbox.py` wird angepasst — Mocks
bisher meist nur ein combined-Log, werden auf zwei Aufrufe umgestellt.
Behaviour change im Spec.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation.

---

### #18 — `skill_writer._stub_code` erzeugt falschen Funktionsnamen

**Problem:** `def test_function():` statt `def {spec.name}():`. Tests
importieren `test_function`, Skill trägt nicht den Spec-Namen.

**Acceptance Criteria:**

```gherkin
Scenario: Stub-Code definiert Funktion mit spec.name
  Given SkillSpec(name="fibonacci", ...)
  When _stub_code(spec)
  Then der Code enthält "def fibonacci("
  And enthält NICHT "def test_function("

Scenario: Stub-Tests importieren spec.name
  Given SkillSpec(name="fibonacci", ...)
  When _stub_tests(spec)
  Then der Code enthält "from skill import fibonacci"
  And enthält "fibonacci()" als Test-Aufruf

Scenario: Stub-Code ist ast-valid
  Given _stub_code(spec)
  When ast.parse
  Then kein SyntaxError
```

**Implementation:** In `_stub_code` und `_stub_tests` `spec.name` interpolieren.

**Negativ-Invariante:** `tests/test_skill_writer.py` wird umgeschrieben, wo
es `test_function` assertet — behaviour change im Spec.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation.

---

## D. Dead Code & Inkonsistenzen (Tier 1/2)

### #19 — Toter Code entfernt

**Acceptance Criteria:**

```gherkin
Scenario: safety.py hat keine ungenutzten FORBIDDEN_CALLS
  Given src/toolkinetik/safety.py
  When nach "FORBIDDEN_CALLS" gesucht
  Then kein Match (entfernt) ODER nur noch eine kanonische Konstante

Scenario: app.py hat kein _get_intent_engine
  Given src/toolkinetik/app.py
  When nach "_get_intent_engine" gesucht
  Then kein Match

Scenario: skill_writer.py hat kein stdin_to_error
  Given src/toolkinetik/skill_writer.py
  When nach "stdin_to_error" gesucht
  Then kein Match

Scenario: _FORBIDDEN_ATTR_CALLS ist Teilmenge, kein Duplikat
  Given safety.py
  When inspiziert
  Dann entweder FORBIDDEN_CALLS gelöscht ODER _FORBIDDEN_ATTR_CALLS gelöscht,
    nicht beide als separate Konstanten mit überlappender Semantik

Scenario: IntentDetector und SkillCreationOrchestrator entfernt
  (siehe #8 — dieselben Szenarien gelten hier)
```

**Implementation:** Insgesamt mit #8 zusammenfassen, da sich die Lösche
überlappen. Dedizierte Commits nur für `app._get_intent_engine`,
`skill_writer.stdin_to_error`, `safety.FORBIDDEN_CALLS`, falls #8
teilweise zurückgestellt wird.

**Negativ-Invariante:** Bestehende Tests, die diese Entitäten importieren,
werden gelöscht oder umgeschrieben. Explizit im Spec vermerkt.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, **`vulture`-Check**
(wenn verfügbar) oder manuelle Suche nach ungenutzten Symbolen in `src/`.

---

### #20 — Ruff: 27 Fehler beheben

**Acceptance Criteria:**

```gherkin
Scenario: ruff check ist clean
  Given der Repo-Zustand nach allen Fixes
  When `uv run ruff check .`
  Then exit_code == 0
  And Output == "All checks passed!"

Scenario: ruff --fix hat nur automatable Fixes angewendet
  Given ein Diff-Review
  When inspiziert
  Dann alle Änderungen sind: Import-Sortierung, unused-import-Entfernung,
    keine inhaltlichen Logikänderungen
```

**Implementation:** `uv run ruff check . --fix`, gefolgt von manueller
Review der restlichen 1 Fehler (wahrscheinlich unused-import in
`test_ui_intent_flow.py`). Falls Logikänderungen nötig, separat behandeln.

**Negativ-Invariante:** Suite bleibt grün (Ruff-Fixes sind nicht-verhaltensändernd).

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage.

---

### #21 — `pyproject.toml`: Deps konsolidieren

**Acceptance Criteria:**

```gherkin
Scenario: agno ist gepinnt
  Given pyproject.toml
  When die dependencies-Zeile für agno inspiziert
  Dann enthält eine Version-Pin (z.B. "agno>=2.8.6,<3.0" oder "agno==2.8.6")

Scenario: Dev-Dependencies sind nur in einer Sektion
  Given pyproject.toml
  When [project.optional-dependencies].dev und [dependency-groups].dev inspiziert
  Dann sind pytest, ruff, mypy, pytest-cov, pytest-randomly alle in derselben Sektion
  And die jeweils andere Sektion hat keine Duplikate

Scenario: rag-Extra existiert
  (siehe #15)

Scenario: uv sync --extra dev installiert pytest-cov und pytest-randomly
  Given einen frischen venv
  When `uv sync --extra dev`
  Then pytest-cov und pytest-randomly sind installiert (importierbar)

Scenario: uv sync --extra rag installiert lancedb und sentence-transformers
  Given einen frischen venv
  When `uv sync --extra rag`
  Then lancedb und sentence_transformers importierbar
```

**Implementation:**
- `agno` mit Pin versehen.
- `pytest-cov`, `pytest-randomly` zusätzlich in `[project.optional-dependencies].dev` aufnehmen,
  oder komplett auf `[dependency-groups].dev` migrieren und `optional-dependencies.dev` leeren.
- `[project.optional-dependencies].rag` neu.

**Negativ-Invariante:** `uv.lock` wird neu generiert; die aktuellen Tests
bleiben lauffähig.

**Gauntlet-Layer:** Full suite, ruff, mypy, **`uv sync --extra dev` smoke-test**,
**`uv sync --extra rag` smoke-test** (in CI-freier Umgebung: nur checken,
dass `uv` den Plan auflöst, nicht tatsächlich installieren, wenn Netz fehlt).

---

### #22 — README-Duplikate

**Acceptance Criteria:**

```gherkin
Scenario: "Prerequisites" erscheint genau einmal
  Given README.md
  When nach "## Prerequisites" gesucht (count)
  Dann count == 1

Scenario: "Tech Stack" erscheint genau einmal
  Given README.md
  When nach "## Tech Stack" gesucht
  Dann count == 1

Scenario: "Quick Start" erscheint genau einmal
  Given README.md
  When count "## Quick Start"
  Dann count == 1

Scenario: README-Inhalt bleibt semantisch erhalten (Regression)
  Given eine Stichprobe von Inhalten: Agno, IntentEngine, SkillWriter,
    Docker sandbox, wigolo, RAG, FastAPI
  When README.md gesucht
  Then jeder Begriff hat mindestens 1 Match
```

**Implementation:** Manuelle Bereinigung der doppelten Sektionen.
Zweit "Prerequisites" (Zeile 167-170) und zweites "Tech Stack"
(Zeile 240-253) löschen, Inhalt zusammenführen wo nötig.

**Negativ-Invariante:** `tests/test_readme.py` wird umgeschrieben, falls es
die doppelten Sektionen assertet — behaviour change im Spec. Inhalt bleibt.

**Gauntlet-Layer:** Full suite, ruff, mypy, manuelle Inhaltsreview der README-Diff.

---

## E. Robustheit & Observability (Tier 2/3)

### #23 — Kein strukturiertes Logging

**Problem:** Überall `except Exception: pass`. Fehler verschwinden lautlos.

**Acceptance Criteria:**

```gherkin
Scenario: Modulweites Logger-Setup
  Given ein src-Modul (skill_writer, setup_mcp, promotion, sandbox, intent)
  When inspiziert
  Then hat `import logging`, `logger = logging.getLogger(__name__)`

Scenario: Defensive except-Blöcke loggen Exceptions
  Given skill_writer._research_dependencies mit wigolo, das Exception wirft
  When aufgerufen
  Then logger.exception oder logger.warning wurde mit der Exception aufgerufen
  And Rückgabe unverändert ("" bzw. graceful)

Scenario: setup_mcp.research loggt Fallback
  Given WigoloMCPToolkit.research, client.research wirft Exception
  When research("...")
  Then logger.warning oder .exception wurde aufgerufen
  And Rückgabe ist Stub-Result

Scenario: promotion.rollback loggt DB-Fehler
  Given SkillPromoter, db.delete_skill wirft Exception
  When rollback("foo")
  Then logger.exception wurde aufgerufen
  And Rückgabe bleibt True (bisheriges Verhalten)

Scenario: sandbox._ensure_test_image loggt Build-Fehler
  (siehe #6 — Verhalten gekoppelt)

Scenario: Logging kann via ENV gesteuert werden
  Given ENV TOOLKINETIK_LOG_LEVEL="DEBUG"
  When get_settings() oder Modul-Init
  Then logging.root.level == logging.DEBUG (oder mindestens logger.level)
```

**Implementation:**
- `logging.getLogger(__name__)` in jedem der 5 Module.
- `except Exception:` → `except Exception as exc: logger.exception(...); <bisheriges Verhalten>`.
- Optional: `TOOLKINETIK_LOG_LEVEL` ENV-Variable in `config.py`, konfiguriert
  `logging.basicConfig` in `__init__.py` oder `app.py`.

**Negativ-Invariante:** Bestehende Tests bleiben grün, sofern sie nicht auf
lautlose Exceptions prüfen. `tests/test_setup_mcp.py`, `tests/test_skill_writer.py`,
`tests/test_promotion.py` werden um Assertions erweitert, dass `logger.exception`
aufgerufen wurde (via `caplog`-Fixture).

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation, **caplog-Assertions**
als Teil der Tests.

---

### #24 — Keine Timeouts bei LLM-Calls

**Problem:** `intent.py:107`, `skill_writer.py:215,403,466`. Hängender
LLM-Endpoint blockiert den Request-Thread.

**Acceptance Criteria:**

```gherkin
Scenario: IntentEngine._ask_llm nutzt Timeout
  Given gemockter LLM, chat.completions.create schläft 10s
  When _ask_llm mit Timeout=1
  Then Exception (Timeout) wird geworfen oder gefangen und als "chat"-Intent degradiert
  And der Aufruf hat timeout=1 übergeben bekommen

Scenario: SkillWriter._generate_code hat Timeout
  Given LLM schläft 100s
  When _generate_code(spec) mit Timeout=2
  Then Fallback auf stub (bisheriges Exception-Verhalten), Dauer < 5s

Scenario: SkillWriter._llm_classify hat Timeout
  Given LLM schläft
  When _llm_classify mit Timeout=1
  Then Rückgabe == {} (bisheriges Exception-Verhalten), Dauer < 3s

Scenario: SkillWriter._revise_code hat Timeout
  Given LLM schläft
  When _revise_code mit Timeout=1
  Then Rückgabe == None, Dauer < 3s

Scenario: Timeout via ENV konfigurierbar
  Given ENV LLM_TIMEOUT=30
  When Settings geladen
  Then settings.LLM_TIMEOUT == 30
  And dieser Wert wird an LLM-Aufrufe übergeben

Scenario: Default Timeout 60s (Regression)
  Given keine ENV
  When Settings geladen
  Then LLM_TIMEOUT == 60
```

**Implementation:**
- Neues Setting `LLM_TIMEOUT: int = 60` in `config.py`.
- `timeout=settings.LLM_TIMEOUT` an allen 4 LLM-Aufruf-Stellen.
- Die `except Exception:`-Blöcke bleiben bestehen (degradation), aber die
  Exceptions schließen `Timeout` ein.

**Negativ-Invariante:** Bestehende Tests, die LLM-Calls mocken, müssen das
`timeout`-Keyword tolerieren. `unittest.mock.MagicMock` akzeptiert beliebige
kwargs, daher i.d.R. unproblematisch.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation, **stress-test**
(LLM schläft → Aufruf klläfft in <Timeout+epsilon).

---

### #25 — LLM-JSON-Antworten ungeprüft

**Problem:** `intent.py:112`, `skill_writer.py:413`. `json.loads` wirft bei
malformed JSON → breit gefangen → leerer Dict → stiller Fallback auf "chat"/Stub.

**Acceptance Criteria:**

```gherkin
Scenario: IntentEngine akzeptiert nur wohlgeformtes Intent-JSON
  Given LLM returns '{"intent": "execute_skill", "skill_name": "foo"}'
  When analyze("...")
  Then SkillMatch.action == "execute_skill"
  And SkillMatch.skill_name == "foo"

Scenario: IntentEngine behandelt malformed JSON als chat-Fallback
  Given LLM returns "not json at all"
  When analyze("...")
  Then SkillMatch.action == "chat"
  And eine Warnung wurde geloggt (siehe #23)

Scenario: IntentEngine validiert Pflichtfelder
  Given LLM returns '{"intent": "execute_skill"}'  # kein skill_name
  When analyze("...")
  Then SkillMatch.action == "execute_skill"
  And SkillMatch.skill_name == ""  (leer ist zulässig, aber Feld vorhanden)

Scenario: IntentEngine mit unbekanntem Intent fällt auf chat zurück
  Given LLM returns '{"intent": "unknown_xyz"}'
  When analyze("...")
  Then SkillMatch.action == "chat"
  And Warnung geloggt

Scenario: SkillWriter._llm_classify bei malformed JSON
  Given LLM returns "{broken"
  When generate_spec("...")
  Then heuristic_spec wurde genutzt (Fallback)
  And Warnung geloggt

Scenario: SkillWriter._llm_classify bei fehlendem "name"
  Given LLM returns '{"description": "x"}'
  When generate_spec("...")
  Then name aus _extract_skill_name abgeleitet (Fallback)
```

**Implementation:**
- Pydantic-Modell `IntentResponse(BaseModel)`: `intent: Literal["execute_skill",
  "create_skill", "rag_search", "chat"]`, `skill_name: str = ""`,
  `description: str = ""`, `signature: str = ""`, `query: str = ""`.
- `_ask_llm` versucht `IntentResponse.model_validate_json(raw)`, bei Fehler
  `logger.warning(...)` und Rückgabe `{"intent": "chat"}`.
- `_llm_classify` analog mit `SkillSpecDraft(BaseModel)`, Fallback auf Heuristik.
- `Literal` ersetzt die string-Vergleiche in `analyze()` — Typprüfung zur
  Compile-Zeit via mypy.

**Negativ-Invariante:** Bestehende Tests, die LLM-Roh-JSON dict-mocken, müssen
entweder auf `IntentResponse`-kompatible JSON umgestellt werden oder die
Mocks bleiben dicts (dann wird `model_validate` direkt mit dict gefüttert).
Behaviour change im Spec.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation, **property-test**
(round-trip: IntentResponse-JSON → Model → dict → Model == original),
**fuzzing**: 20 Random-Strings → alle landen im "chat"-Fallback, keine
unbehandelte Exception.

---

## Negativ-Constraints (Invariants, die überleben müssen)

1. `tests/test_intent_engine.py` (5 Tests) bleibt bis auf #10-Anpassung grün.
2. `tests/test_skill_writer.py` wird umgeschrieben im Rahmen von #4, #7, #8, #18, #23 —
   jede geänderte Assertion ist im Spec vermerkt, keine wird heimlich gelöscht.
3. `tests/test_tdd_loop.py` und `tests/test_promotion.py` bleiben unverändert.
4. `tests/test_safety.py` wird erweitert (#19 löscht `FORBIDDEN_CALLS`), keine
   Assertion gelöscht.
5. `tests/test_sandbox.py` wird angepasst für #3, #6, #17 — Mocks umgestellt,
   keine Assertion gelöscht.
6. `tests/test_coding_agent.py` wird angepasst für #5 — Assertions verschärft,
   keine gelöscht.
7. `tests/test_cli.py` wird angepasst für #14 — URL-Variabilisierung.
8. `tests/test_readme.py` wird angepasst für #22 — Duplikat-Assertions umgeschrieben.
9. `tests/test_db.py` wird erweitert für #13 — neue Szenarien, bestehende
   angepasst wo `created_at` überschreibung assertionen waren.
10. `tests/test_setup_mcp.py` wird erweitert für #16, #23.
11. `tests/test_app.py` bleibt grün bis auf #9, #11 — Anpassungen dort.

## Auführungsgrenzen (Known Limits)

- **#16 Wigolo-Framing:** Real-Test gegen wigolo-Server nicht im Gauntlet
  (Netz-/uvx-Abhängigkeit). Nur Mock-Tests.
- **#3 Sandbox-Härtung:** Real-Docker-Run nicht im Gauntlet (Docker-Daemon in
  Test-Env nicht garantiert). Mock-only.
- **#15 RAG-Schema:** `uv sync --extra rag` wird deklariert, aber nicht in
  Gauntlet installiert, um Netzpflicht zu vermeiden. Nur Schema-Logik wird
  gemockt geprüft.
- **#23 Logging-Level via ENV:** Implementiert, aber kein assert auf
  Production-Log-Format (nur `caplog`-Prüfung in Tests).
- **#8 Pipeline-Konsolidierung:** `SkillCreationOrchestrator` wird gelöscht,
  ohne dass eine Feature-Parity-Garantie für externe Aufrufer gegeben wird —
  das Modul ist nicht Teil einer öffentlichen API, nur intern genutzt
  (verifiziert via `grep -r "SkillCreationOrchestrator" src tests`).

## Test-Abdeckungs-Ziel

- Alle neu hinzugefügten Zeilen in `src/`: 100% changed-line coverage.
- Alle neu hinzugefügten Zeilen in geänderten Tests: 100%.
- Bestehende Coverage-Percentage darf nicht sinken (aktueller Stand wird
  als Baseline in EVIDENCE festgehalten).

## Gauntlet-Ausführung (Single-Entry)

`scripts/gauntlet_25.sh` führt aus, in Reihenfolge:

```bash
#!/usr/bin/env bash
set -euo pipefail
echo "=== RUFF ==="
uv run ruff check .
echo "=== MYPY ==="
uv run mypy src
echo "=== PYTEST (randomized) ==="
uv run pytest tests/ -q -p randomly --cov=src/toolkinetik --cov-report=term-missing
echo "=== MUTATION (manual, scripted) ==="
bash scripts/mutation_25.sh
echo "=== GAUNTLET COMPLETE ==="
```

`scripts/mutation_25.sh` enthält die manual-mutant-Skripte je Behaviour
(wird während der Implementierung generiert, persistiert im Repo).

## EVIDENCE-Report-Plan

Am Ende wird `EVIDENCE-25-improvements.md` erstellt mit:
- Spec-Verweis (dieses Dokument, freigegebener Stand).
- Pro Behaviour-Cluster (#1..#25): Testname, Kommando, Resultat (pasted Zahlen).
- Gauntlet-Layer-Ergebnisse, alle aus einem finalen Fresh-Run.
- Source-Identifikation: Commit-SHA, Branch, Tree-Hash.
- Layers skipped + Begründung (siehe Known Limits).
- Spec-Approval-Status (autonomous oder human-approved).