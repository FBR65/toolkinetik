# SPEC — Production-Ready ToolKinetik

**Datum:** 2026-08-05  
**Basis:** `PRODUCTION-READINESS.md` (31 open Punkte, P0–P4)  
**Status:** DRAFT — wartet auf Freigabe vor Implementierung  
**Branch:** `master` (HEAD aktuell)  
**Tier:** P0 = Tier 3 (Security/Datenverlust), P1 = Tier 2-3, P2 = Tier 2, P3 = Tier 1-2  

---

## Status quo (Baseline)

- **Tests:** 350 passed (nach 25-Punkte-Arbeit)  
- **Ruff:** clean  
- **Mypy:** clean  
- **Coverage:** 87% (ui.py 45%, setup_mcp.py 75%, skill_writer.py 80%, cli.py 79%)  
- **Git:** Sauberes Repo, alle Änderungen committed  
- **Skill-Bestand:** 47 SKILL.md-basierte Skills (7 Kategorien) + 55 Python-Scripts + 3 Legacy `*.py` + 3 Index-Cache-Dateien — **nur die 3 Legacy-Skills sind funktionsfähig**

---

## Setup-Plan (autorisiert mit Spec-Freigabe)

**Werkzeuge (bereits vorhanden):** pytest, pytest-cov, pytest-randomly, ruff, mypy, uv, docker.

**Neue Entwicklungs-Dependencies (nur dev-Extra):**
- `pytest-asyncio` — für async WebSocket/health-check Tests (Begründung: async Test-Patterns für `/ws/chat` und `/api/health/deep`)
- `hypothesis` — für property-based Tests des SafetyChecker (P3.8)
- `playwright` — für NiceGUI E2E-Tests (P1.1, optional)

**Neue Production-Dependencies:**
- `pyyaml` — für YAML-Frontmatter-Parser in SKILL.md (P0.7). Standard-Bibliothek hat keinen YAML-Parser.
- `slowapi` oder `fastapi-limiter` — für Rate-Limits (P1.3)
- `python-json-logger` oder `structlog` — für structured Logging (P1.5)
- `prometheus_client` — für `/metrics`-Endpoint (P1.5)
- `alembic` — für DB-Migration (P2.4)
- Keine weiteren. `lancedb`/`sentence-transformers` bleiben im optional `rag` Extra.

**Git:** Repo existiert. Checkpoint-Commits nach jedem Behaviour-Cluster. Branch: Arbeit direkt auf `master`, da kein `fix/`-Branch mehr aktiv ist. Cadence: pro Tier (P0, dann P1, dann P2).

**Neue ENV-Variablen:**
- `TOOLKINETIK_DEV=1` — Dev-Modus (erlaubt API-Key-Auto-Gen, P0.5)
- `TOOLKINETIK_LOG_LEVEL=INFO` — Log-Level konfigurieren (P1.5)
- `RATE_LIMIT_CHAT=10/minute` — WebSocket Rate-Limit (P1.3)
- `RATE_LIMIT_HTTP=30/minute` — HTTP Rate-Limit (P1.3)

**Dateien, die der Gauntlet anlegt (neu):**
- `src/toolkinetik/health.py` — Deep-Health-Check-Endpoint (P1.2)
- `src/toolkinetik/rate_limiter.py` — Rate-Limit-Middleware (P1.3)
- `src/toolkinetik/logging_config.py` — Structured Logging Setup (P1.5)
- `src/toolkinetik/metrics.py` — Prometheus-Metrics-Endpoint (P1.5)
- `src/toolkinetik/skill_runner.py` — Isolated Skill Execution via subprocess (P1.6)
- `src/toolkinetik/version_manager.py` — Skill-Version-Tracking für Rollback (P2.5)
- `src/toolkinetik/skill_loader.py` — SKILL.md-Parser und Skill-Loader (P0.7)
- `src/toolkinetik/skill_executor.py` — Skill-Ausführung via Coding-Agent (P0.7)
- `data/migrations/` — Alembic- oder yoyo-Migrations-Scripts (P2.4)

**Test-Dateien (neu):**
- `tests/integration/test_sandbox_real.py` — P0.1
- `tests/integration/test_wigolo_real.py` — P0.2
- `tests/integration/test_rag_real.py` — P0.3
- `tests/integration/test_llm_smoke.py` — P0.4
- `tests/test_api_key_production.py` — P0.5
- `tests/test_secrets_scan.py` — P0.6
- `tests/test_skill_loader.py` — P0.7
- `tests/test_skill_executor.py` — P0.7
- `tests/test_trusted_skills.py` — P0.7
- `tests/test_deep_health.py` — P1.2
- `tests/test_rate_limit.py` — P1.3
- `tests/test_db_concurrent.py` — P1.4
- `tests/test_observability.py` — P1.5
- `tests/test_skill_isolation.py` — P1.6
- `tests/test_git_commit_race.py` — P1.7
- `tests/integration/test_skill_runner.py` — P1.6
- `tests/test_llm_cost_tracking.py` — P2.1
- `tests/test_skill_cache.py` — P2.2
- `tests/test_ws_connection_limits.py` — P2.3
- `tests/test_db_migration.py` — P2.4
- `tests/test_skill_rollback.py` — P2.5
- `tests/test_resource_warnings.py` — P3.1
- `tests/test_safety_property.py` — P3.8
- `tests/integration/conftest.py` — Integration-test fixtures
- `.github/workflows/ci.yml` — CI-Job für Real-Tests

---

## Phase 1 — P0 (Vor Produktivnahme zwingend)

### P0.1 — Real-Docker-Sandbox-Verifizierung

**Problem:** Sandbox-Härtung (`read_only`, `cap_drop=ALL`, etc.) ist nur spekulativ wirksam — kein Test läuft gegen einen echten Docker-Daemon.

**Failure-Model:**
- Das `tmpfs noexec`-Flag blockiert pytest-Schreibzugriffe auf `/tmp` → alle Skill-Tests schlagen fehl.
- `read_only=True` verhindert notwendige Schreibzugriffe im Container.

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: Real Docker container runs pytest with all hardening flags
    Given ein echter Docker-Daemon verfügbar (Docker-in-Docker CI-Service)
    When tests/integration/test_sandbox_real.py: SandboxRunner.run_tests(...)
    Then exit_code == 0
    And "passed" in stdout

Scenario: Network isolation blocks outbound DNS resolution
    Given SandboxRunner mit network_mode="none"
    When run_code("import socket; socket.gethostbyname('example.com')")
    Then exit_code != 0 (ConnectionError / socket.gaierror)

Scenario: read_only blocks write to /etc/passwd
    Given SandboxRunner mit read_only=True
    When run_code("open('/etc/passwd','a').write('test')")
    Then exit_code != 0 (PermissionError / Read-only file system)

Scenario: cap_drop=ALL blocks setuid
    Given SandboxRunner mit cap_drop=["ALL"]
    When run_code("import os; os.setuid(0)")
    Then exit_code != 0 (PermissionError)
```

**Implementation:** Integrationstest mit `@pytest.mark.integration`, geskipped wenn Docker nicht verfügbar.

**Gauntlet-Layer:** Full suite (integration tests skipped wenn Docker fehlt), Real Docker-Run (CI-Job).

---

### P0.2 — Real wigolo-Server-Verifizierung

**Problem:** `_WigoloClient` Handshake (`initialize`/`notifications/initialized`) ist nur gemockt. Echter wigolo-Server könnte abweichen.

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: Handshake mit echtem wigolo-Server
    Given uvx @KnockOutEZ/wigolo verfügbar (skippe wenn fehlt)
    When WigoloMCPToolkit.research("python test framework")
    Then result ist ein dict mit "results"-Key
    And error-Key ist nicht "wigolo server unavailable"

Scenario: initialize-Response wird akzeptiert
    Given wigolo-Server startet
    When _WigoloClient._handshake()
    Then self._initialized == True
    And initialize-Response enthält protocolVersion

Scenario: Content-Length-Framing von wigolo
    Given wigolo-Server sendet Content-Length-Header
    When _call("research", ...)
    Then JSON-Body korrekt extrahiert
```

**Implementation:** `tests/integration/test_wigolo_real.py` mit `@pytest.mark.integration`. Dokumentation in `docs/wigolo-compat.md`.

**Gauntlet-Layer:** Full suite, Real wigolo-Run (nur wenn uvx verfügbar).

---

### P0.3 — RAG-Pipeline End-to-End-Test

**Problem:** `lancedb` und `sentence-transformers` sind nicht installiert. Schema-Logik ist gemockt. `.encode(...).tolist()[0]` könnte bei neueren Versionen schiefgehen.

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: Indizieren + semantische Suche gegen echten LanceDB
    Given uv sync --extra rag ausgeführt
    When RagManager: 3 Dokumente indizieren, dann search("climate change")
    Then Top-1-Ergebnis ist das Dokument über Klimawandel
    And Vektor-Dimension == 384 (all-MiniLM-L6-v2)

Scenario: Embedding-Format kompatibel
    Given SentenceTransformer("all-MiniLM-L6-v2")
    When encode(["test"])
    Then result ist numpy-Array mit shape (1, 384)
    And .tolist()[0] gibt List[float] der Länge 384 zurück
```

**Implementation:** `uv sync --extra rag` in separatem CI-Job. Versions-Pins in `pyproject.toml`.

**Gauntlet-Layer:** Full suite, Real RAG-Run (CI-Job mit `--extra rag`).

---

### P0.4 — LLM-Endpoint-Smoke-Test gegen echtes Backend

**Problem:** `response_format={"type": "json_object"}` wird nicht von allen Endpoints unterstützt. Timeout-Übergabe unterschiedlich je SDK-Version.

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: Intent-Klassifikation gegen echten Endpoint
    Given ENV TOOLKINETIK_TEST_LLM_BASE=http://ollama:11434/v1
    When IntentEngine.analyze("hello world")
    Then SkillMatch.action ist einer der 4 Intents

Scenario: Skill-Code-Generierung gegen echten Endpoint
    Given konfigurierter LLM-Endpoint
    When SkillWriter._generate_code(spec)
    Then code ist non-empty und ast-valid

Scenario: Revise-Code gegen echten Endpoint
    Given konfigurierter LLM-Endpoint
    When SkillWriter._revise_code(code, error)
    Then revisio ist non-empty
```

**Implementation:** `tests/integration/test_llm_smoke.py` mit `@pytest.mark.llm`, geskipped wenn ENV nicht gesetzt.

**Gauntlet-Layer:** Full suite, LLM-Smoke-Tests (nur wenn ENV gesetzt).

---

### P0.5 — AGNO_API_KEY in Produktion nicht auto-generieren

**Problem:** `config.py:_load_or_generate_api_key` generiert und persistiert einen zufälligen Key. In Produktion führt zu unkontrolliertem Lockout.

**Failure-Model:**
- Neustart mit leerer Key-Datei → neuer Key → alte Clients haben keinen Zugang.
- Operator kennt Key nicht → kann nicht handeln.

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: Produktiv ohne AGNO_API_KEY wirft Startup-Fehler
    Given TOOLKINETIK_DEV nicht gesetzt (Produktion)
    And AGNO_API_KEY nicht in ENV
    And keine Key-Datei existiert
    When Settings() initialisiert
    Then RuntimeError("AGNO_API_KEY is required in production")

Scenario: Dev-Modus erlaubt Auto-Gen
    Given TOOLKINETIK_DEV=1
    And AGNO_API_KEY nicht in ENV
    When Settings() initialisiert
    Then AGNO_API_KEY ist ein token_urlsafe(32)-String
    And Datei data/.api_key mit Mode 0o600 existiert

Scenario: Env-var-Key wird verwendet (Regression)
    Given AGNO_API_KEY=env-secret
    When Settings() initialisiert
    Then settings.AGNO_API_KEY == "env-secret"
    And keine Datei geschrieben
```

**Implementation:** `config.py` modifizieren: `_load_or_generate_api_key` prüft `TOOLKINETIK_DEV`. Ohne Dev-Modus + ohne ENV-Key + ohne Key-Datei → `raise RuntimeError`. `.env.example` um `TOOLKINETIK_DEV` ergänzen.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation (manual: `raise` entfernen → Test failt).

---

### P0.6 — Secrets-Scan des gesamten Repos

**Problem:** Während der 25-Punkte-Arbeit wurde nur der Diff gescannt, nicht die Historie.

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: Kein Secrets in git history
    Given gitleaks (oder trufflehog) installiert
    When Scan über alle Commits
    Then 0 High-Severity-Finds
    And 0 medium-severity secrets (API keys, tokens, passwords)
```

**Implementation:** `gitleaks` über die Historie laufen lassen. Bei Funden: `git filter-repo`.

**Gauntlet-Layer:** gitleaks-scan, Ergebnis gepastet.

---

### P0.7 — Skill-System: Neue Skill-Sammlung integrieren (fundamentale Architektur-Lücke)

**Problem:** Die neue Skill-Sammlung (47 `SKILL.md`-basierte Skills in 7 Kategorien, 55 Python-Scripts in Unterverzeichnissen, Index-Cache-Dateien von Anthropic/OpenAI/LobeHub) wird vom aktuellen `DynamicToolRegistry` **komplett ignoriert**. Die Registry lädt nur die 3 Top-Level `.py`-Dateien (`math_skill.py`, `weather_skill.py`, `__init__.py`). Die gesamte neue Skill-Bibliothek — der Hauptwert des Systems — ist funktionslos.

**Struktur der neuen Skills (Hermes/Anthropic Format):**
```
skills/
├── math_skill.py              # Legacy: top-level Python-Funktion
├── weather_skill.py           # Legacy: top-level Python-Funktion
├── creative/                  # 16 Skills (p5js, comfyui, manim-video, ...)
│   ├── p5js/
│   │   ├── SKILL.md           # Frontmatter: name, description, version
│   │   ├── scripts/           # Ausführbare Helper-Scripts
│   │   ├── references/        # Referenz-Dokumentation
│   │   └── templates/         # Vorlagen
│   └── ...
├── productivity/              # 7 Skills (docx, xlsx, powerpoint, pdf, ...)
├── github/                    # 6 Skills (github-code-review, github-pr-workflow, ...)
├── software-development/      # 11 Skills (TDD, plan, debugging, ...)
├── autonomous-ai-agents/       # 4 Skills (claude-code, codex, opencode, ...)
├── research/                  # 2 Skills (llm-wiki, research-paper-writing)
├── email/                     # 1 Skill (himalaya)
└── index-cache/               # Skill-Indizes (Anthropic, OpenAI, LobeHub)
```

**Failure-Model:**
1. User fragt "Erstelle ein Word-Dokument" → `IntentEngine` kennt den `docx`-Skill nicht (nicht in `available_tools()`) → `create_skill`-Intent → SkillWriter generiert einen neuen (möglicherweise schlechteren) Skill, obwohl ein hochwertiger existiert.
2. Skill-Helper-Scripts (`scripts/*.py`) importieren `os`, `subprocess`, `shutil`, `lxml` — der `SafetyChecker` blockiert diese. Trusted Skills müssen vom Safety-Check ausgenommen werden.
3. Index-Cache-Dateien (`index-cache/*.json`) enthalten Skill-Metadaten, die für Skill-Discovery wichtig sind — werden nicht genutzt.

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: DynamicToolRegistry entdeckt SKILL.md-basierte Skills
    Given skills/ mit 47 SKILL.md-Dateien in 7 Kategorien
    When registry.get_tools() aufgerufen
    Then registry.registered_tools enthält alle 47 Skill-Namen aus Frontmatter
    And math_skill und weather_skill (Legacy) bleiben erhalten (Regression)

Scenario: Skill-Metadaten werden aus Frontmatter extrahiert
    Given skills/productivity/docx/SKILL.md mit name=docx, description="Create, read, edit Word .docx documents"
    When registry die Datei parst
    Then Metadaten enthalten name="docx", description, version="1.0.0"
    And Skill ist aufrufbar (execute oder delegierbar)

Scenario: IntentEngine kennt alle 47 Skills
    Given alle SKILL.md-Skills sind registriert
    When IntentEngine.available_tools()
    Then Rückgabe enthält "docx", "pdf", "powerpoint", "github-code-review", "test-driven-development", ...

Scenario: User fragt "Erstelle ein Word-Dokument" → docx-Skill wird erkannt
    Given docx-Skill registriert mit description="Create, read, edit Word .docx documents"
    When IntentEngine.analyze("Erstelle ein Word-Dokument mit...")
    Then intent == "execute_skill" mit skill_name="docx"
    And nicht "create_skill" (kein unnötiger SkillWriter-Aufruf)

Scenario: Trusted Skills umgehen SafetyChecker
    Given ein Helper-Script in skills/productivity/docx/scripts/ importiert os, subprocess
    When SafetyChecker.check_code(script_content)
    Then passed == True (trusted skill, nicht LLM-generiert)
    # ODER: SafetyChecker hat einen trusted-path für skills_dir/scripts/

Scenario: SafetyChecker blockiert weiterhin LLM-generierten Code
    Given LLM-generierter Code mit "import os"
    When SafetyChecker.check_code(llm_code)
    Then passed == False (untrusted, nicht im skills_dir)

Scenario: Index-Cache wird für Skill-Discovery genutzt
    Given index-cache/anthropics_skills_skills_.json mit Skill-Metadaten
    When registry initialisiert
    Then Skills aus Index-Cache sind discoverable
    And Skill-Beschreibungen aus Index-Cache werden für IntentEngine genutzt

Scenario: Skill-Ausführung delegiert an Coding-Agent
    Given SKILL.md-basierter Skill (z.B. "docx")
    When Skill aufgerufen
    Then Coding-Agent (Claude Code/Codex/OpenCode) erhält SKILL.md als Kontext
    And Agent führt die proceduralen Anweisungen aus
    And Helper-Scripts in scripts/ werden genutzt

Scenario: DynamicToolRegistry-Vertrag bleibt erhalten (Regression)
    Given DynamicToolRegistry mit Legacy *.py + SKILL.md-Skills
    When get_tools()
    Then Rückgabe ist list[Callable]
    And Jeder Eintrag hat __name__-Attribut (str)
    And registered_tools ist dict[str, Callable]
    And Legacy-Skills (math_skill, weather_skill) sind enthalten mit __name__ == Funktionsname
    And SKILL.md-Skills sind enthalten mit __name__ == Frontmatter name
    And Hot-Reload funktioniert (erneutes get_tools erkennt neue Skills)
```

**Implementation:**

1. **`DynamicToolRegistry` erweitern (registry.py) — der kritische Kontrakt:**

   Die bestehende Klasse lädt nur Top-Level `*.py` als Python-Funktionen (`Callable` mit `__name__`). Die neuen `SKILL.md`-Skills sind **keine Python-Funktionen** sondern procedurales Wissen. Der bestehende Kontrakt muss erhalten bleiben:

   - `get_tools()` → `list[Callable]` (Regression: jeder Eintrag hat `__name__`)
   - `registered_tools: dict[str, Callable]` (key = Name, value = aufrufbar)
   - Hot-Reload: `get_tools()` erneut aufgerufen, erkennt neue Dateien
   - Skip `__*` Files (legacy)
   - sys.path Handling unverändert
   - Modul-Prefix unverändert

   **Lösung:** `DynamicToolRegistry` wird erweitert, sodass `get_tools()` zwei Quellen mergt:

   ```python
   class DynamicToolRegistry:
       def __init__(self, skills_dir: str, ...):
           # Bestehende Felder bleiben
           self.registered_tools: dict[str, Callable] = {}
           self.registered_skill_descriptions: dict[str, str] = {}  # NEU: name -> description
           self._skill_loader = SkillLoader(skills_dir)  # NEU

       def get_tools(self) -> list[Callable]:
           self.registered_tools = {}
           # 1. Legacy: Top-Level *.py → Python-Funktionen (unverändert)
           self._load_python_skills()
           # 2. NEU: SKILL.md → SkillTool-Wrapper (Callable mit __name__)
           self._load_skill_md_skills()
           return list(self.registered_tools.values())
   ```

   **`SkillTool` (neue Klasse, aufrufbar):**
   - Implementiert `__call__(*args, **kwargs)` → delegiert an `SkillExecutor`
   - Hat `__name__` (aus Frontmatter `name:`) → kompatibel mit `app.py:47` und `intent.py:65`
   - Hat `__doc__` (aus Frontmatter `description:`) → für IntentEngine-Kontext
   - Hat `_skill_path` (Pfad zum SKILL.md-Verzeichnis) → für SkillExecutor

   Damit bleibt der bestehende Kontrakt (Callable mit `__name__`) erhalten, aber `SkillTool`-Instanzen sind keine rohen Python-Funktionen sondern Wrapper, die die Ausführung an den Coding-Agent delegieren.

2. **`SkillLoader` (neue Klasse in `skill_loader.py`):**
   - Scannt rekursiv `skills/` nach `SKILL.md`-Dateien
   - Extrahiert Metadaten aus YAML-Frontmatter (`name`, `description`, `version`)
   - Lädt Legacy `*.py`-Skills weiterhin (via bestehendem `importlib`-Pfad)
   - Erzeugt `SkillTool`-Wrapper für jedes SKILL.md
   - Registriert Helper-Scripts (`scripts/*.py`) als ausführbare Pfade (nicht als Import)

3. **`SkillExecutor` (neue Klasse in `skill_executor.py`):**
   - Führt `SkillTool`-Aufrufe aus, indem der Coding-Agent das `SKILL.md` als Kontext erhält
   - Helper-Scripts (`scripts/*.py`) werden via `subprocess` ausgeführt
   - Trusted-Skills umgehen den SafetyChecker

4. **SafetyChecker-Erweiterung (safety.py):**
   - Neues Konzept: **trusted skills** (in `skills_dir/scripts/`) vs **untrusted code** (LLM-generiert)
   - `check_code(code, trusted_path=False)` — `trusted_path=True` überspringt Import-Checks
   - Default bleibt `False` (sicher für LLM-generierten Code)

5. **IntentEngine-Erweiterung (intent.py):**
   - `available_tools()` nutzt `registry.registered_skill_descriptions` für LLM-Kontext
   - LLM sieht Skill-Descriptions, nicht nur Namen → bessere Klassifikation
   - Index-Cache-Integration für erweiterte Discovery

6. **Index-Cache-Integration:**
   - `skills/index-cache/*.json` werden in den Skill-Index aufgenommen
   - Skill-Beschreibungen aus Index-Cache ergänzen Frontmatter-Beschreibungen

**Dateien, die geändert werden:**
- `src/toolkinetik/registry.py` — `DynamicToolRegistry` erweitert (`SkillTool`-Integration, `registered_skill_descriptions`); Legacy-Pfad unverändert
- `src/toolkinetik/safety.py` — trusted-path Konzept (`check_code(code, trusted_path=False)`)
- `src/toolkinetik/intent.py` — Skill-Beschreibungen in Intent-Klassifikation (`available_tools()` nutzt `registered_skill_descriptions`)
- `src/toolkinetik/skill_writer.py` — prüft existierende Skills vor `create_skill` (vermeidet Duplikate)
- `src/toolkinetik/app.py` — Skill-Listing-API erweitert (`/api/skills` zeigt SKILL.md-Skills)

**Dateien, die neu erstellt werden:**
- `src/toolkinetik/skill_loader.py` — `SkillLoader`: SKILL.md-Parser, Frontmatter-Extraktion, `SkillTool`-Wrapper
- `src/toolkinetik/skill_executor.py` — `SkillExecutor`: Skill-Ausführung via Coding-Agent + Helper-Scripts
- `tests/test_skill_loader.py` — Tests für Skill-Discovery und Frontmatter-Parsing
- `tests/test_skill_executor.py` — Tests für Skill-Ausführung und Helper-Script-Delegation
- `tests/test_trusted_skills.py` — Tests für SafetyChecker trusted-path
- `tests/test_registry_skill_md.py` — Tests für `DynamicToolRegistry` mit SKILL.md-Integration (Regression: Legacy-Tests bleiben grün)

**Negativ-Invarianten (müssen überleben):**
1. `tests/test_registry.py` (3 Tests) bleibt grün — Legacy `*.py`-Skills werden weiterhin geladen
2. `tests/test_registry_syspath.py` (5 Tests) bleibt grün — sys.path-Handling, Modul-Prefix unverändert
3. `tests/test_app.py` bleibt grün — `registry.registered_tools` enthält noch `Callable`-Werte mit `__name__`
4. `tests/test_intent_engine.py` bleibt grün — `available_tools()` gibt Liste von Namen zurück
5. `tests/test_skill_writer.py` bleibt grün — `SkillWriter`-Pipeline unberührt
6. `create_agent` (app.py:117) registriert weiterhin Tools beim Agno Agent — `SkillTool` ist `Callable`

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, mutation, Real-Execution (Skill-Aufruf gegen echtes SKILL.md), property-test (Frontmatter round-trip).

---

## Phase 2 — P1 (Vor größerem Nutzerkreis)

### P1.1 — NiceGUI-Frontend ist ungetestet (45% Coverage)

**Problem:** UI-Logik ist nur strukturell getestet. WebSocket-Interaktion, Status-Updates, Skill-Monitor sind nicht E2E-getestet.

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: Chat-Nachricht senden → Antwort empfangen
    Given NiceGUI-App läuft (oder gemockt)
    When send_message mit "hello"
    Then WebSocket.send wurde mit Text aufgerufen
    And Response wird im Chat-Container angezeigt

Scenario: Skill-Reload via UI-Button
    Given UI geladen
    When "Skills Neuladen" Button geklickt
    Then POST /api/reload-skills via httpx
    And ui.notify mit geladenen Tools

Scenario: WebSocket-Disconnect behandelt
    Given WebSocket-Verbindung
    When WebSocketDisconnect
    Then reset_status() aufgerufen, keine Exception
```

**Implementation:** Playwright-Tests (falls Browser verfügbar) oder erweiterte Mock-Tests. `@pytest.mark.ui`.

**Gauntlet-Layer:** Full suite, UI-Tests (skipped wenn Playwright nicht verfügbar).

---

### P1.2 — Keine Health-Checks für Sandbox / LLM / RAG

**Problem:** `/api/health` prüft nur Prozess-Liveness. Docker, LLM, RAG-Status nicht geprüft.

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: Deep-Health-Check prüft alle Subsysteme
    Given GET /api/health/deep
    Then Response ist 200 (wenn alles healthy)
    And JSON enthält: status, checks.docker, checks.llm, checks.rag
    And jeder Check hat timeout=2s

Scenario: Degraded-Status bei Docker-down
    Given Docker-Daemon nicht erreichbar
    When GET /api/health/deep
    Then status == "degraded"
    And checks.docker.status == "unhealthy"
    And Andere Checks trotzdem ausgeführt
```

**Implementation:** `src/toolkinetik/health.py` mit `check_docker()`, `check_llm()`, `check_rag()`.

**Gauntlet-Layer:** Full suite, ruff, mypy, Real-Health-Check (wenn Docker verfügbar).

---

### P1.3 — Keine Rate-Limits

**Problem:** Keine Rate-Limits pro API-Key. Kompromittierter Client kann LLM fluten.

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: Rate-Limit pro API-Key
    Given Env mit RATE_LIMIT_HTTP=5/minute
    When 6 POST /api/reload-skills in 1 Minute
    Then 6. Request gibt 429 Too Many Requests

Scenario: WebSocket Rate-Limit
    Given RATE_LIMIT_CHAT=2/minute
    When 3 Nachrichten über WS in 1 Minute
    Then 3. Nachricht → close(1008)
```

**Implementation:** `slowapi` oder `fastapi-limiter` mit Redis oder in-memory-Store.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, Rate-Limit-Tests.

---

### P1.4 — SQLite bei Concurrent Writes

**Problem:** `db.py` öffnet pro Operation eine neue Connection. Parallel-Skill-Promotion kann `database is locked` werfen.

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: WAL-Modus aktiviert
    Given SkillStore initialisiert
    When PRAGMA journal_mode abgefragt
    Then Ergebnis == "wal"

Scenario: 10 parallele Promotions ohne Lock-Fehler
    Given 10 Threads rufen register_skill("skill_N", ...) gleichzeitig auf
    When alle beenden
    Then 0x OperationalError ("database is locked")
    And Alle 10 Skills in DB

Scenario: Retry bei Lock-Error
    Given database ist locked (simuliert)
    When register_skill versucht
    Then max 3 Retries mit Backoff (100ms)
```

**Implementation:** `PRAGMA journal_mode=WAL` in `_init_schema`. Connection-Pool via `check_same_thread=False` + Lock. Retry-Decorator.

**Gauntlet-Layer:** Full suite, ruff, mypy, concurrent-test.

---

### P1.5 — Kein Observability-Stack

**Problem:** Logs gehen nur nach stdout/stderr. Keine strukturierten Logs, keine Metriken, keine Request-ID.

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: Structured JSON Logging
    Given TOOLKINETIK_LOG_LEVEL=DEBUG
    When SkillWriter schlägt fehl
    Then Log-Zeile enthält request_id, timestamp, level, module, message als JSON

Scenario: Request-ID pro WebSocket-Session
    Given WebSocket-Verbindung
    When Nachricht verarbeitet
    Then Alle Logs dieser Session enthalten dieselbe request_id
    And request_id ist in den Logs nachvollziehbar

Scenario: /metrics-Endpoint mit Prometheus-Format
    Given GET /metrics
    Then 200 OK
    And Body enthält "# HELP toolkinetik_" 
    And skill_promote_total, tdd_loop_duration_seconds, llm_call_duration_seconds
```

**Implementation:** `python-json-logger` oder `structlog`. `contextvars`-basiertes Request-ID-Tracking. `prometheus_client` für `/metrics`.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, structured-log-Assertions.

---

### P1.6 — Skill-Code isoliert ausführen, nicht im Hauptprozess

**Problem:** `DynamicToolRegistry` lädt Skills via `importlib` im FastAPI-Prozess. Ein fehlerhafter Skill (Endlosschleife, `os._exit`) bringt den Server down.

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: Skill-Ausführung im isolierten Prozess
    Given DynamicToolRegistry lädt einen Skill
    When Skill wird ausgeführt
    Then Ausführung läuft in einem separaten Worker-Prozess (subprocess/multiprocessing)
    And Timeout=30s pro Aufruf
    And Memory-Limit=256MB via resource.setrlimit

Scenario: Endlosschleife-Skill timeout
    Given Skill mit "while True: pass"
    When Ausführung
    Then Timeout nach 30s
    And Prozess wird getötet
    And Haupt-Server läuft weiter
```

**Implementation:** `src/toolkinetik/skill_runner.py` mit `concurrent.futures.ProcessPoolExecutor` + Timeout. `resource.setrlimit(resource.RLIMIT_AS, ...)` für Memory.

**Gauntlet-Layer:** Full suite, ruff, mypy, isolation-test, Real-Execution (mit feindlichem Skill).

---

### P1.7 — Git-Commit-Race bei parallelen Promotions

**Problem:** `_git_commit` ruft `git add` + `git commit` auf. Bei parallelen Promotions kann `index.lock` fehlschlagen.

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: Parallel-Promotionen ohne index.lock-Fehler
    Given 10 Threads rufen promote() gleichzeitig auf
    When alle beenden
    Dann 0x "index.lock" Fehler in Logs
    And Alle Skills gepromotet

Scenario: Retry bei index.lock
    Given git commit schlägt mit "index.lock" fehl
    When promote()
    Then max 3 Retries mit 100ms Backoff
    And Bei endgültigem Fehlschlag: Warning geloggt, git_committed=False
```

**Implementation:** Prozess-globaler Lock (`threading.Lock`) um `_git_commit`. Retry-Logik für `index.lock`.

**Gauntlet-Layer:** Full suite, ruff, mypy, concurrent-git-test.

---

## Phase 3 — P2 (Vor Skalierung)

### P2.1 — LLM-Cost-Tracking

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: Token-Verbrauch bei jedem LLM-Call geloggt
    Given IntentEngine.sendet Request an LLM
    When Antwort erhalten
    Then usage.prompt_tokens, usage.completion_tokens in Metrics/Logs

Scenario: Daily-Token-Limit
    Given LLM_DAILY_TOKEN_LIMIT=100000
    When Tagesverbrauch > Limit
    Then neue LLM-Requests mit 429 / "limit exceeded" Fehler

Scenario: Kosten pro Skill nachverfolgen
    Given Skill "fibonacci" generiert
    When Cost-Metrik gelesen
    Dann fibonacci_cost_total == Summe aller Token-Kosten
```

**Implementation:** `toolkinetik.metrics` erweitern um `llm_tokens_total`-Counter. `response.usage` aus LLM-Responses extrahieren.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage.

---

### P2.2 — Skill-Caching: Vermeide doppelte LLM-Calls

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: Intent-Engine-Ergebnis-Cached
    Given "berechne fibonacci" 3x hintereinander
    When IntentEngine.analyze
    Dann _ask_llm wird nur 1x aufgerufen (TTL=5min, key=user_request+tool_hash)

Scenario: Existierender Skill vor create_skill
    Given Skill "calculate_fibonacci" existiert
    When IntentEngine.classifiziert "berechne fibonacci"
    Dann intent == "execute_skill" (nicht "create_skill")
```

**Implementation:** `@lru_cache` oder dict-basierter Cache in `IntentEngine` mit 5-Min-TTL.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage.

---

### P2.3 — WebSocket Connection-Limits

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: Max-Connections pro API-Key
    Given MAX_WS_CONNECTIONS_PER_KEY=2
    When 3 WebSocket-Verbindungen mit gleichem Key
    Dann 3. Connection wird mit code 1008 geschlossen
```

**Implementation:** Connection-Tracking via `defaultdict` pro API-Key. Konfigurierbar.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage.

---

### P2.4 — DB-Migration-Strategy

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: Schema-Version in DB
    Given frische SQLite-DB
    When SkillStore initialisiert
    Dann migration_version == 1 in DB

Scenario: Alembic-Migration führt Schema-Änderungen durch
    Given Migration "add_tags_column"
    When alembic upgrade head
    Dann Spalte "tags" in skills-Tabelle existiert
```

**Implementation:** `alembic` integration. `data/migrations/` Verzeichnis. Version-Tabelle.

**Gauntlet-Layer:** Full suite, ruff, mypy, migration-test.

---

### P2.5 — Skill-Rollback in Produktion

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: Version pro Promotion in DB speichern
    Given Skill "fibonacci" promotet (v1.0.0)
    Wenn erneut promotet (v1.1.0)
    Dann DB hat 2 Version-Einträge

Scenario: GET /api/skills/{name}/rollback?version=1.0.0
    Given frühere Version existiert
    When POST /api/skills/fibonacci/rollback?version=1.0.0
    Dann Datei enthält v1.0.0 Code
    Und DB version == "1.0.0"

Scenario: Git-history-basierter Rollback
    Given git Log für skill.py existiert
    Wenn rollback mit version=1.0.0
    Dann git show <sha>:<file> wiederhergestellt
```

**Implementation:** `src/toolkinetik/version_manager.py` + API-Endpoint. Version in DB-Schema als neue Spalte `versions` (JSON oder separate Tabelle).

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage.

---

## Phase 4 — P3 (Qualität / Wartbarkeit)

### P3.1 — Pre-existing ResourceWarnings fixen

**Problem:** 47 ResourceWarnings (ungeclosed sqlite-Connections, asyncio event loops).

**Acceptance Criteria:**
- `SkillStore` verwendet Context-Manager (`with` oder `__enter__`/`__exit__`).
- `test_ui_frontend.py` nutzt `asyncio.new_event_loop()` korrekt.

**Gauntlet-Layer:** Full suite mit `-W error::ResourceWarning`, ruff, mypy.

---

### P3.2 — `setup_mcp.py` Coverage erhöhen (75% → 90%+)

**Problem:** 36 ungedeckte Statements (Popen-Start, Handshake-Timeout, Framing-Edge-Cases).

**Acceptance Criteria:**
- Test: Popen schlägt fehl → `_StubClient` Fallback
- Test: stdout EOF → `ConnectionError`
- Test: malformed JSON-Body → `None` zurück
- Test: Content-Length-Mismatch → korrekte Behandlung
- Property-Test: round-trip JSON-RPC-Request → Response

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage ≥ 90%, hypothesis.

---

### P3.3 — `skill_writer.py` Coverage erhöhen (80% → 90%+)

**Problem:** 34 ungedeckte Statements (`_run_local_tdd`, `_stub_code` Fallback).

**Acceptance Criteria:**
- Test für `_run_local_tdd` mit echtem tempfile + pytest.
- Test für `_llm_classify` bei `json.JSONDecodeError` → `{}` zurück.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage ≥ 90%.

---

### P3.4 — `cli.py` Coverage erhöhen (79% → 90%+)

**Problem:** 15 ungedeckte Statements. `skills create` ist Placeholder. `sandbox status` hat keine echten Assertions.

**Acceptance Criteria:**
- `skills create NAME DESC` ruft SkillWriter oder API auf (nicht nur "Not yet implemented")
- `sandbox status` prüft Docker-Daemon via `docker.from_env().ping()`

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage ≥ 90%.

---

### P3.5 — UI docs / ARIA-Verifizierung

**Acceptance Criteria:**
- `axe-core` oder `pa11y` in Frontend-Tests integriert.
- WCAG-AA-Compliance-Report generiert.

**Gauntlet-Layer:** UI-Tests, Accessibility-Scan (skipped wenn Browser nicht verfügbar).

---

### P3.6 — Production-Dokumentation

**Dateien:**
- `docs/DEPLOYMENT.md` — Docker-Compose, ENV-Variablen, Reverse-Proxy, TLS
- `docs/OPERATIONS.md` — Backup, Restore, Git-Maintenance
- `docs/INCIDENT.md` — Sandbox-Down, LLM-Down, Promotion-Loop
- `docs/wigolo-compat.md` — wigolo-Version kompatibel

**Gauntlet-Layer:** Review der Docs, Inhalt verifiziert.

---

### P3.7 — Dependency-Pinning

**Acceptance Criteria:**
- `agno` ist gepinnt (`>=2.8.6,<3.0`)
- `fastapi`, `nicegui`, `docker`, `openai` sind gepinnt
- `uv lock --frozen` in CI
- RenovateBot/Dependabot für Update-PRs

**Gauntlet-Layer:** `uv lock --frozen` check, ruff, mypy.

---

### P3.8 — Property-Based-Tests für SafetyChecker

**Acceptance Criteria (Gherkin):**

```gherkin
Scenario: check_code ist idempotent
    Given beliebiger Python-Code
    When check_code(code) zweimal aufgerufen
    Dann beide Ergebnisse identisch (same passed, same issues)

Scenario: import os in allen Kontexten geblockt
    Given Code mit "import os" in Kommentar, String, Decorator, echtem Import
    Wenn check_code
    Dann nur echter Import wird flagged (Kommentar/String/Decorator sind safe)
```

**Implementation:** `hypothesis`-Strategien für Python-Source-Code-Fragments.

**Gauntlet-Layer:** Full suite, ruff, mypy, coverage, hypothesis.

---

## Phase 5 — P4 (Nice-to-have / Langfristig)

Items P4.1–P4.5 bleiben im Backlog. Werden erst nach P0–P3 abgeschlossen.

---

## Execution Order (empfohlen)

| Schritt | Items | Tier | Aufwand |
|---|---|---|---|
| **S1** | P0.5, P0.6 | Tier 3 | 1 Tag |
| **S2** | P0.7 | Tier 3 | 3–5 Tage (fundamentale Architektur) |
| **S3** | P0.1, P0.2, P0.3, P0.4 | Tier 3 | 3–4 Tage |
| **S4** | P1.2, P1.7 | Tier 2-3 | 1–2 Tage |
| **S5** | P1.4, P1.3 | Tier 2-3 | 1–2 Tage |
| **S6** | P1.5, P1.1 | Tier 2-3 | 3–4 Tage |
| **S7** | P1.6 | Tier 3 | 3–5 Tage |
| **S8** | P2.1, P2.2, P2.3 | Tier 2 | 2–3 Tage |
| **S9** | P2.4, P2.5 | Tier 2 | 2–3 Tage |
| **S10** | P3.1 – P3.8 | Tier 1-2 | 5–8 Tage |
| **Total** | 32 | | **19–29 Tage** |

## Spec-Approval

```
spec approval: not obtained (autonomous run)
```

---

## Behavious-to-Test-Mapping (vollständig)

Jedes Item hat mindestens einen Test. Siehe Spalte "Test" in den jeweiligen Gherkin-Szenarien.

## Known Limits der Spezifikation

1. **Real-Execution-Tests (P0.1–P0.4)** erfordern Docker-Daemon, uvx/wigolo und LLM-Endpoint — werden via `@pytest.mark.integration` geskipped wenn Umgebung fehlt.
2. **Rate-Limit-Tests (P1.3)** benötigen `slowapi`+`limits` → Dependency muss installiert werden.
3. **Skill-Isolation (P1.6)** erfordert `multiprocessing`/`subprocess`-Integration — Unit-Tests mocken, E2E testen mit Hostile-Skill.
4. **Observability (P1.5)** erfordert `python-json-logger`+`prometheus_client` → Dependencies.
5. **DB-Migration (P2.4)** erfordert `alembic` → Dependency.
6. **Property-Tests (P3.8)** erfordern `hypothesis` → dev-Dependency.

---

*Dieses SPEC ist append-only. Änderungen während der Implementierung werden hier vermerkt.*
