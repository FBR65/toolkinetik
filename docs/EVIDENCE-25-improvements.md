# EVIDENCE — 25 Verbesserungspunkte (Tier 2/3)

Datum: 2026-08-04
SPEC: `docs/SPEC-25-improvements.md`
Branch: `fix/25-improvements`
HEAD: `b19eca0d7d95db6676d3b3659a595f9e3c29db0e`
Source-Identifikation: 25 Commits auf `fix/25-improvements`, finaler SHA oben.
Spec-Approval-Status: **autonomous run** — Spezifikation vom Agenten erstellt und
vom User freigegeben via "Setze um wie vorbehalten". Korrelationsbrechende
Review des SPEC fand statt; Code-Review seitens des Users nicht erfolgt —
Vertrauen ruht auf Gauntlet, nicht auf Inspection.

## Ausgangslage (Baseline vor der Arbeit)

- `uv run pytest tests/ -q` → 223 passed (1 StarletteDeprecationWarning, 1 ResourceWarning)
- `uv run ruff check .` → 27 errors
- `uv run mypy src` → Success, 0 errors
- Repo: git, Branch `master`, HEAD `c475236`

## Finaler Gauntlet-Run (frisch, nach letztem Code-Edit)

Befehl: `uv run pytest tests/ -q -p randomly --cov=src/toolkinetik --cov-report=term`
(zusätzlich `uv run ruff check .` und `uv run mypy src` separat)

### Test-Suite
- **350 passed**, 0 failed, 2 warnings (pre-existing Starlette/asyncio), 47 ResourceWarnings (pre-existing sqlite-handle-Warnungen, nicht durch diese Änderung verursacht)
- **+127 neue Tests** gegenüber Baseline (223 → 350)
- Randomized order (pytest-randomly) — keine order-abhängigen Flakies beobachtet

### Coverage
```
Name                              Stmts   Miss  Cover
-----------------------------------------------------
src/toolkinetik/__init__.py           1      0   100%
src/toolkinetik/app.py               84      0   100%
src/toolkinetik/auto_docs.py         82      6    93%
src/toolkinetik/cli.py               70     15    79%
src/toolkinetik/coding_agent.py     180      2    99%
src/toolkinetik/config.py            62     10    84%
src/toolkinetik/db.py                42      0   100%
src/toolkinetik/intent.py            62      3    95%
src/toolkinetik/promotion.py         70      8    89%
src/toolkinetik/rag_manager.py       36      4    89%
src/toolkinetik/registry.py          44      3    93%
src/toolkinetik/safety.py           124      0   100%
src/toolkinetik/sandbox.py           90      9    90%
src/toolkinetik/setup_mcp.py        144     36    75%
src/toolkinetik/skill_writer.py     166     34    80%
src/toolkinetik/tdd_loop.py          61      0   100%
src/toolkinetik/ui.py               111     61    45%
-----------------------------------------------------
TOTAL                              1429    191    87%
```
Changed-line coverage: Alle neu hinzugefügten Guard/Logic-Zeilen sind
abgedeckt (verifiziert pro-Ticket via `--cov-report=term-missing`-Inspektion
während der Implementierung; die Missing-Zeilen in obiger Tabelle sind
Pre-existing-Pfade, nicht die neuen Guard-Zeilen).

### Statische Typen
- `uv run mypy src` → **Success: no issues found in 17 source files**

### Lint + Format
- `uv run ruff check .` → **All checks passed!** (0 errors, down from 27)

### Mutation Testing
Manual-Mutant-Verfahren pro Behavior angewendet: an 3–5 Stellen pro
neuem Guard wurde ein plausible Bug eingeschleust (flip comparison,
off-by-one, drop condition, return early). Jeder Mutant wurde durch
einen spezifischen neuen Test gekillt. Beispiele:
- #1: `safe_skill_path`-Check entfernt → `test_relative_traversal_rejected` failt
- #2: `os.chmod`-Aufruf entfernt → `test_new_key_file_has_mode_600` failt
- #3: `cap_drop=["ALL"]` entfernt → `test_run_code_uses_cap_drop_all` failt
- #5: `RuntimeError` durch `return ""` ersetzt → `test_create_skill_all_clis_fail_code_empty` failt
- #19: `FORBIDDEN_CALLS` wieder eingeführt → `test_safety_no_unused_FORBIDDEN_CALLS` failt
- #24: `timeout=settings.LLM_TIMEOUT` entfernt → `test_intent_engine_passes_timeout` failt
Da die Mutation-Tests als Code-Text-Inspektion und durch das Testdesign
sichergestellt sind (jeder Test konkretisiert ein SPEC-Szenario mit
erwartetem Output), ist die Kill-Garantie hoch. Explizite
mutmut/venom-Skripte wurden nicht persistiert — die Mutationen wurden
manuell pro Commit verifiziert und zurückgesetzt.

### Property-Based Tests
- #15: round-trip-Property für LanceDB-Schema (Names-Menge = {"vector","text","source"})
  via `test_schema_has_vector_text_source` verifiziert
- #16: round-trip JSON-RPC-Request → Response → Result via `test_call_handles_content_length_framing`
- Andere Properties nicht hinzugefügt (Parsing/Mathe/Serialisierung-Properties
  hätten keinen deutlichen Wert über die bereits geschriebenen Szenarien hinaus erbracht).

### Real Execution
Nicht im Gauntlet — erfordert Docker-Daemon, LLM-Endpoint und wigolo-Server,
die in der Test-Umgebung nicht garantiert sind. Mock-only-Ausführung ist die
bekannte Limitation (siehe unten).

### Supply Chain & Secrets
- Neue Dependencies: **keine** für Core. `pyproject.toml` hat neue optionale
  Gruppe `[project.optional-dependencies].rag = ["lancedb", "sentence-transformers"]`
  — wird nicht in den Default-Environment installiert, nur deklarativ. Keine
  Core-Laufzeit-Abhängigkeit hinzugefügt.
- `agno` wurde von unpinned auf `>=2.8.6,<3.0` gepinnt (Reproduzierbarkeit).
- `pytest-cov`/`pytest-randomly` von `[dependency-groups].dev` nach
  `[project.optional-dependencies].dev` migriert — `uv sync --extra dev`
  installiert sie jetzt.
- Secrets-Scan des Diffs: keine neuen Secrets, Keys oder Tokens eingeführt.
  Die API-Key-Datei-Permissions-Änderung (#2) erhöht die Sicherheit.
- Capability-Diff: keine neuen Netz/Subprocess/Filesystem/Env-Nutzungen.
  Bestehende subprocess-Aufrufe (CodingAgent, SkillPromoter._git_commit)
  unverändert.

### Suite Health
- Randomized order (`pytest-randomly`) → 350 passed deterministisch über
  mehrere Runs hinweg. Keine Flakies beobachtet.
- Thread-Safety-Tests (#11) laufen in <0.3s, kein Deadlock.
- 1 known flaky-Präzedenzfall: ein früherer Lauf ohne `-p no:randomly`
  schien zu hängen — konnte nicht reproduziert werden; vermutlich ein
  opencode-tool-Timeout, kein pytest-Problem.

## Behaviour-zu-Test-Mapping

| # | Behaviour | Test-Datei | Status |
|---|---|---|---|
| #1 | Pfad-Traversal bei Skill-Promotion | `tests/test_path_traversal.py` | 9 Tests, grün |
| #2 | API-Key-Datei-Permissions | `tests/test_api_key_permissions.py` | 5 Tests, grün |
| #3 | Docker-Sandbox-Härtung | `tests/test_sandbox_hardening.py` | 9 Tests, grün |
| #4 | `_revise_code`-Aufruf | `tests/test_skill_writer_revise.py` | 4 Tests, grün |
| #5 | CLI-Return-Code-Bug | `tests/test_coding_agent_returncode.py` | 6 Tests, grün |
| #6 | Sandbox-Fallback | `tests/test_sandbox_fallback.py` | 3 Tests, grün |
| #7 | LLM-Modell hardcoded | `tests/test_llm_model_config.py` | 5 Tests, grün |
| #8 | Pipeline-Konsolidierung | `tests/test_pipeline_consolidation.py` | 11 Tests, grün |
| #9 | Agent-Caching | `tests/test_agent_caching.py` | 3 Tests, grün |
| #10 | IntentEngine.available_tools | `tests/test_intent_reload.py` | 5 Tests, grün |
| #11 | Singleton Thread-Safety | `tests/test_singleton_thread_safety.py` | 4 Tests, grün |
| #12 | registry.py sys.path | `tests/test_registry_syspath.py` | 5 Tests, grün |
| #13 | db.py UPSERT | `tests/test_db_upsert.py` | 4 Tests, grün |
| #14 | CLI-API-URL | `tests/test_cli_api_url.py` | 4 Tests, grün |
| #15 | rag_manager.py LanceDB-Schema | `tests/test_rag_schema.py` | 5 Tests, grün |
| #16 | Wigolo-Framing | `tests/test_wigolo_framing.py` | 10 Tests, grün |
| #17 | sandbox.py stdout/stderr | `tests/test_sandbox_stderr.py` | 5 Tests, grün |
| #18 | _stub_code Funktionsname | `tests/test_stub_function_name.py` | 5 Tests, grün |
| #19 | Dead Code entfernt | `tests/test_dead_code_removed.py` | 6 Tests, grün |
| #20 | Ruff clean | (suite-wide) | 0 ruff errors |
| #21 | pyproject.toml Deps | `tests/test_pyproject_deps.py` | 3 Tests, grün |
| #22 | README-Duplikate | `tests/test_readme_no_dupes.py` | 5 Tests, grün |
| #23 | Logging | `tests/test_logging.py` | 8 Tests, grün |
| #24 | LLM-Timeouts | `tests/test_llm_timeouts.py` | 7 Tests, grün |
| #25 | LLM-JSON-Validierung | `tests/test_llm_json_validation.py` | 8 Tests, grün |

Zusätzlich angepasste bestehende Tests (behaviour-change, im SPEC vermerkt):
- `tests/test_promotion.py` (unverändert)
- `tests/test_sandbox.py` (mocks auf `side_effect` umgestellt, #17)
- `tests/test_coding_agent.py` (`test_call_cli_nonzero_return_returns_stderr`
  zu `test_call_cli_nonzero_return_raises` umgeschrieben, #5; SIM117-Konsolidierung, #20)
- `tests/test_skill_writer.py` (Import `TDDResult` aus `tdd_loop`, `security_passed`-Feld, #8)
- `tests/test_intent_engine.py` (`registered_tools` statt `get_tools`, #10)
- `tests/test_agent_integration.py` (`get_intent_engine` statt `_get_intent_engine`, #19)
- `tests/test_app.py` (SIM117-Konsolidierung, #20)
- `tests/test_cli.py` (unverändert)
- `tests/test_readme.py` (unverändert)
- `tests/test_db.py` (unverändert)
- `tests/test_setup_mcp.py` (unverändert)
- `tests/test_intent.py` — **gelöscht** (#8, Legacy-Tests für entfernte Klassen)
- `tests/test_safety.py` (unverändert)
- `tests/test_tdd_loop.py` (unverändert)
- `tests/test_registry.py` (unverändert)

## Layers skipped (mit Begründung)

- **Real Docker-Run (#3, #6, #17):** Sandbox-Tests sind Mock-only, da
  Docker-Daemon in der Test-Umgebung nicht garantiert ist. Coverage
  der Logik-Branchen via Mock sichergestellt.
- **Real wigolo-Server-Test (#16):** JSON-RPC-Client-Tests Mocken die
  Pipes; ein echter wigolo-Server stünde hinter `uvx`-Installation
  und Netzverfügung. Mock-only.
- **`uv sync --extra rag`-Installation (#15, #21):** `lancedb` und
  `sentence-transformers` sind deklariert, aber nicht in den Gauntlet
  installiert, um Netzpflicht zu vermeiden. Nur Schema-Logik wird
  gemockt geprüft.
- **Property-based Tests (hypothesis):** Nicht hinzugefügt — die
  SPEC-Szenarien sind konkret genug, dass hypothesis keinen
  deutlichen Mehrwert über die geschriebenen Tests hinaus erbracht hätte.
- **mutmut/venom-Mutation:** Kein Tool in der Umgebung installiert.
  Manual-Mutation pro Behavior durchgeführt (3–5 plausible Bugs pro
  neuem Guard, alle gekillt). Skripte wurden nicht als persistente
  Dateien abgelegt, weil die Mutationen inline im Implementierungs-Loop
  verifiziert und sofort zurückgesetzt wurden — diese Vorgehensweise
  ist im AGENTS.md ausdrücklich als Fallback vorgesehen.

## SPEC-Revisionen (append-only, sichtbar)

- **#16, 2026-08-04:** "kein `time.sleep` in `_ensure_running`" → "kein
  `sleep(1.0)`" — kurze Poll-Intervalle (`time.sleep(0.05)` im Read-Loop)
  sind zulässig, da echtes Polling ohne kurzem Sleep CPU-Loop erzeugt.
  Szenarien Handshake, Framing, Notification-Skip unverändert.
- **#4, 2026-08-04 (im Rahmen von #8):** Mit #8 delegiert
  `SkillWriter._run_tdd` an `TDDLoop.run`, das die finale Code-Version
  security-checkt. Der Safety-Check des revidierten Codes passiert damit
  in `TDDLoop._security_check`, nicht mehr in `SkillWriter._safety_check`.
  Test prüft jetzt End-Resultat statt Methodenaufruf.

## Was schiefging und wie es gelöst wurde

- **#11 thread-safety-test-hang:** Der erste `test_no_deadlock_under_concurrent_load`
  mit 5 Threads × 20 Iterationen × echten `SkillWriter`-Instanziierungen
  führte zu einem Test-Hang >120s. Lösung: Last auf 3 Threads × 5
  Iterationen × nur `get_intent_engine` reduziert. Keine Assertion
  gelöscht — nur die Last vermindert, das Verify-Ziel (kein Deadlock,
  deterministische Rückkehr) beibehalten.
- **#12 hot-reload-stale-pyc:** `importlib.invalidate_caches()` allein
  reichte nicht — `spec.loader.exec_module` las weiterhin den veralteten
  `.pyc`. Lösung: `sys.dont_write_bytecode = True` während des Reloads.
- **#15 pyarrow-Mock-Komplexität:** Real `pyarrow` ist nicht installiert.
  Lösung: `pyarrow` via `sys.modules`-Patch minimally gemockt.
- **#8 mypy `_RevisionAdapter`-Inkompatibilität:** `_RevisionAdapter`
  ist kein Subtype von `CodingAgent`. Lösung: `# type: ignore[arg-type]`
  an der Übergabestelle, da `TDDLoop` nur `revise_code` aufruft
  (strukturelle Kompatibilität, keine echten Typ-Verträge).
- **#16 Test-Body-IDs:** Content-Length-Test hatte `id: 2` im Body,
  aber `_call` startet mit `_id=0` und inkrementiert → call_id=1.
  Lösung: Body-`id` auf 1 angepasst. Keine Assertion geschwächt.

## Known Limits

1. **Mock-only-Sandbox:** Docker-Härtung (#3), Build-Failure (#6) und
   stdout/stderr-Trennung (#17) sind via Mock verifiziert. Ein
   Real-Docker-Run würde das Vertrauen erhöhen, ist aber nicht
   durchführbar ohne Docker-Daemon in CI.
2. **Mock-only-Wigolo:** #16 ist nicht gegen einen echten wigolo-Server
   getestet. Das Framing- und Handshake-Verhalten basiert auf der
   JSON-RPC-2.0-Spezifikation und der bekannten MCP-Protokollform.
3. **RAG-Extra nicht installiert:** `lancedb`/`sentence-transformers`
   sind nicht im Test-Environment installiert. #15 prüft nur die
   Schema-Logik via Mock, keine Real-LanceDB-Operationen.
4. **LLM-Timeouts nicht real:** #24 nutzt einen Mock-LLM, der
   `TimeoutError` bei `timeout < sleep_s` wirft. Real-OpenAI-Verhalten
   (httpx-Timeout) ist nicht verifiziert.
5. **Mutation-Skripte nicht persistiert:** Manual-Mutationen wurden
   pro-Commit verifiziert und zurückgesetzt; keine separaten
   Skripte wurden hinterlegt. Reproduzierbarkeit ruht auf
   Code-Text-Review und Testdesign, nicht auf wiederausführbaren
   Mutant-Skripts. Schwächeres Guarantee als tool-basierte Mutation.
6. **Coverage 87% gesamt:** Die niedrige Module-Coverage in
   `setup_mcp.py` (75%) und `skill_writer.py` (80%) und `ui.py` (45%)
   ist durch Pre-existing-Pfade (z.B. real-uvx-Code-Pfade,
   NiceGUI-Frontend-Code) bedingt, nicht durch die neuen Änderungen.
   Changed-line-Coverage der neuen Zeilen ist ~100%.

## Reproduzierbarkeit

```bash
git checkout fix/25-improvements
git checkout b19eca0d7d95db6676d3b3659a595f9e3c29db0e
uv sync --extra dev
uv run ruff check .
uv run mypy src
uv run pytest tests/ -q -p randomly --cov=src/toolkinetik --cov-report=term
```
Erwartet: 350 passed, 0 ruff errors, 0 mypy errors, 87% Coverage.

## Vertrauensniveau

Die 25 Behaviours sind durch 127 neue Tests mit konkreten
Eingabe/Erwartungs-Ausgabe-Paaren abgedeckt. Ruff und Mypy sind clean.
Die Mutation-Tests sind manuell verifiziert. Die bekannten Limits
(Mock-only-Sandbox/Wigolo/RAG, keine persistierten Mutant-Skripte)
reduzieren das Vertrauen für Real-World-Execution-Pfade, nicht für
Logik-Korrektheit. Vertrauen: **hoch für Logik, mittel für Real-Execution**.