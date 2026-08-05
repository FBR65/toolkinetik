# Roadmap zur Produktionsreife — ToolKinetik

Datum: 2026-08-04
Stand: nach Merge der 25 Verbesserungspunkte (Commit `cf6ea04` auf `master`).
350 Tests grün, Ruff clean, Mypy clean.

Diese MD listet alle noch offenen Punkte, die vor einem Produktivbetrieb
von ToolKinetik adressiert werden müssen — geordnet nach Risiko und
Aufwand. Sie basiert auf den während der 25-Punkte-Arbeit identifizierten
Known Limits (siehe `docs/EVIDENCE-25-improvements.md`) und einer
zusätzlichen Review-Runde auf dem jetztigen Stand.

## P0 — Vor Produktivnahme zwingend (Sicherheit / Datenverlust)

### P0.1 — Real-Docker-Sandbox-Verifizierung
- **Status:** #3, #6, #17 sind Mock-only getestet. Kein einziger Test
  läuft gegen einen echten Docker-Daemon.
- **Risiko:** Die Härtung (`read_only`, `cap_drop=ALL`, `tmpfs noexec`,
  `pids_limit`) ist nur spekulativ wirksam. Ein Real-Docker-Run könnte
  zeigen, dass die Kombination der Flags mit dem verwendeten Image
  inkompatibel ist oder dass pytest im Container `/tmp` Schreibzugriffe
  braucht, die `tmpfs noexec` blockt (dann schlägt jeder Skill-Test fehl).
- **Aufgabe:**
  1. CI-Job mit Docker-in-Docker-Service einrichten.
  2. Integrationstest `tests/integration/test_sandbox_real.py` schreiben:
     echtes Python-Image, echter `pytest`-Lauf, Assert Exit-Code.
  3. Test mit `network_mode="none"`: ein Skill, der `socket.gethostbyname`
     aufruft, muss fehlschlagen.
  4. Test mit `read_only=True`: Schreibversuch nach `/etc/passwd` muss
     fehlschlagen.
  5. Test mit `cap_drop=ALL`: `os.setuid`-Aufruf muss PermissionError werfen.
- **Aufwand:** 1–2 Tage (CI-Setup + Tests).

### P0.2 — Real-wigolo-Server-Verifizierung
- **Status:** #16 ist Mock-only. Der echte wigolo-Server via
  `uvx @KnockOutEZ/wigolo` wurde nie live getestet.
- **Risiko:** Der Handshake (`initialize`/`notifications/initialized`)
  und das Content-Length-Framing basieren auf der JSON-RPC-2.0-Spec und
  der MCP-Protokollform — die echte wigolo-Implementierung könnte
  abweichen (z.B. erst `initialize`-Response, dann erst `initialized`-
  Notification, oder andere Felder im `initialize`-Result, die wir
  ignorieren).
- **Aufgabe:**
  1. Manuelles `uvx @KnockOutEZ/wigolo` starten, `_WigoloClient` dagegen
     laufen lassen, Handshake verifizieren.
  2. `tests/integration/test_wigolo_real.py` schreiben (markiert als
     `@pytest.mark.integration`, skip wenn `uvx`/wigolo fehlt).
  3. Dokumentation: welche wigolo-Version getestet wurde, im `README`
     oder `docs/wigolo-compat.md` festhalten.
- **Aufwand:** 0,5–1 Tag.

### P0.3 — RAG-Pipeline-End-to-End-Test
- **Status:** #15 hat nur die Schema-Logik gemockt. `lancedb` und
  `sentence-transformers` sind nicht installiert, kein Real-Index-Test.
- **Risiko:** LanceDB-Schema ist möglicherweise API-inkompatibel mit
  der verwendeten `lancedb`-Version. `SentenceTransformer.encode` gibt
  numpy-Arrays zurück — `.tolist()[0]` könnte bei neueren Versionen
  schiefgehen.
- **Aufgabe:**
  1. `uv sync --extra rag` in einer CI-Variante.
  2. `tests/integration/test_rag_real.py`:
     - kleines Dokumenten-Set indizieren,
     - semantische Suche mit erwartetem Top-1-Treffer,
     - Dimensions-Kompatibilität (384) verifizieren.
  3. `pyproject.toml`: `lancedb` und `sentence-transformers` mit
     Versions-Pins versehen (z.Zt. unpinned).
- **Aufwand:** 1–2 Tage.

### P0.4 — LLM-Endpoint-Smoke-Test gegen echtes Backend
- **Status:** #7, #24, #25 sind Mock-only. Kein Test ruft einen echten
  OpenAI-kompatiblen Endpoint auf.
- **Risiko:** `response_format={"type": "json_object"}` wird nicht von
  allen Endpoints unterstützt (z.B. Ollama, vLLM ohne JSON-Mode). Die
  Timeout-Übergabe (`timeout=`-kwarg) ist je nach `openai`-SDK-Version
  unterschiedlich.
- **Aufgabe:**
  1. Integrationstest mit konfigurierbarem Endpoint
     (`TOOLKINETIK_TEST_LLM_BASE`-ENV).
  2. Test-Suite: Intent-Klassifikation, Skill-Code-Generierung, Revise-Code.
  3. Tests mit `@pytest.mark.llm` markieren, skip wenn ENV fehlt.
- **Aufwand:** 0,5–1 Tag.

### P0.5 — AGNO_API_KEY in Produktion nicht auto-generieren
- **Status:** `config.py` auto-generiert einen Key und persistiert ihn
  in `data/.api_key` mit 0o600 (#2 verbessert). Für Produktion ist das
  ein Anti-Pattern: ein zufälliger Key wird erzeugt, ohne dass der
  Operator ihn erfährt — bei einem Neustart mit leerer Datei entsteht
  ein neuer Key, alte Clients haben keinen Zugang mehr.
- **Risiko:** Unangekündigter Lockout, schwer debuggbar.
- **Aufgabe:**
  1. In Produktion MUSS `AGNO_API_KEY` als ENV var gesetzt sein.
  2. `_load_or_generate_api_key` bei fehlendem ENV + fehlendem Dev-Modus
     einen Startup-Fehler werfen statt zu generieren.
  3. Dev-Modus via `TOOLKINETIK_DEV=1` kennzeichnen, nur dann Auto-Gen.
  4. Doku: `.env.example` um `TOOLKINETIK_DEV` ergänzen.
- **Aufwand:** 0,5 Tag.

### P0.6 — Secrets-Scan des gesamten Repos
- **Status:** Während der 25-Punkte-Arbeit wurde der Diff gescannt,
  nicht der gesamte Repo-Historie.
- **Risiko:** Frühere Commits könnten Secrets enthalten (wenn auch
  unwahrscheinlich).
- **Aufgabe:**
  1. `gitleaks` oder `trufflehog` über die gesamte Repo-Historie laufen lassen.
  2. Bei Funden: `git filter-repo` oder BFG-Repo-Cleaner, dann Force-Push
     (koordinieren mit allen Klones).
- **Aufwand:** 0,5 Tag.

## P1 — Vor größerem Nutzerkreis (Robustheit / Skalierung)

### P1.1 — NiceGUI-Frontend ist ungetestet (45% Coverage)
- **Status:** `ui.py` hat 45% Coverage. Die WebSocket-Interaktion, die
  Status-Updates und das Skill-Monitor-UI sind nur strukturell getestet.
- **Risiko:** UI-Fehler in Produktion sind schwer reproduzierbar,
  fehlerhafte WebSocket-Nachrichten-Handlers (z.B. bei langen
  Skill-Creation-Loops) können den Browser freeze.
- **Aufgabe:**
  1. Playwright- oder Selenium-Test-Suite für das NiceGUI-Dashboard.
  2. Critical-Path: Chat-Nachricht senden, Skill-Reload klicken,
     Status-Update empfangen.
  3. Fehlerpfade: WebSocket-Disconnect, API-Key-Invalid.
- **Aufwand:** 2–3 Tage.

### P1.2 — Keine Health-Checks für Sandbox / LLM / RAG
- **Status:** `/api/health` prüft nur, dass der FastAPI-Prozess lebt.
- **Risiko:** Ein Health-Check, der "healthy" zurückgibt, während
  Docker unavailable ist oder der LLM-Endpoint down ist, verleitet
  Load-Balancer, Traffic auf eine kaputte Instanz zu routen.
- **Aufgabe:**
  1. `/api/health/deep`: prüft Docker-Daemon, LLM-Endpoint (Ping),
     RAG-Initialisierbarkeit.
  2. Health-Status als `{"status": "healthy"|"degraded"|"unhealthy",
     "checks": {...}}`.
  3. Timeout für jeden Sub-Check (max 2s), damit der Endpoint nicht hängt.
- **Aufwand:** 0,5–1 Tag.

### P1.3 — Keine Rate-Limits
- **Status:** FastAPI bietet keine Rate-Limits. WebSocket-Endpoint
  ist nur durch API-Key geschützt.
- **Risiko:** Ein kompromittierter Client kann den LLM-Endpoint
  fluten (Kosten-Explosion) oder die Sandbox (Ressourcen-Exhaustion).
- **Aufgabe:**
  1. `slowapi` oder `fastapi-limiter` integrieren.
  2. Limit pro API-Key: z.B. 10 Requests/Minute für `/ws/chat`,
     5/Minute für `/api/reload-skills`.
  3. Konfigurierbar via ENV (`RATE_LIMIT_CHAT`, etc.).
- **Aufwand:** 0,5–1 Tag.

### P1.4 — SQLite bei Concurrent Writes
- **Status:** `db.py` öffnet pro Operation eine neue Connection. Bei
  vielen parallelen Skill-Promotions kann SQLite `database is locked`
  werfen.
- **Risiko:** Skill-Promotion schlägt fehl, keine Retry-Logik in
  `SkillPromoter.promote` für DB-Locks.
- **Aufgabe:**
  1. Connection-Pool oder singleton-Connection mit `WAL`-Mode
     (`PRAGMA journal_mode=WAL`).
  2. Retry-Logik bei `OperationalError: database is locked` (max 3
     Retries mit Backoff).
  3. Integrationstest mit 10 parallelen Promotions.
- **Aufwand:** 0,5–1 Tag.

### P1.5 — Kein Observability-Stack
- **Status:** #23 hat `logging` eingeführt, aber Logs gehen nur nach
  stdout/stderr. Keine strukturierte Log-Aggregation, keine Metriken.
- **Risiko:** In Produktion sind Fehler schwer korrelierbar (welcher
  Skill-Creation-Loop gehört zu welchem User?).
- **Aufgabe:**
  1. Structured-JSON-Logging (`python-json-logger` oder `structlog`).
  2. Request-ID pro WebSocket-Session, durch alle Logger propagieren
     (via `contextvars`).
  3. Metriken: Promote-Erfolgsrate, TDD-Loop-Dauer, LLM-Latenz.
     `/metrics`-Endpoint (Prometheus-Format).
- **Aufwand:** 2–3 Tage.

### P1.6 — Skill-Code isoliert ausführen, nicht im Hauptprozess
- **Status:** `DynamicToolRegistry` lädt Skills via `importlib` direkt
  in den FastAPI-Prozess. Ein Skill mit einem Bug (Endlosschleife,
  `os._exit`, Speicherleck) bringt den ganzen Server down.
- **Risiko:** Ein fehlerhafter Skill killt den Server. #3 härtet die
  *TDD-Sandbox*, aber nach dem Promoten läuft der Skill im Hauptprozess.
- **Aufgabe:**
  1. Skill-Ausführung in einen Worker-Prozess auslagern (multiprocessing
     oder subprocess-pool).
  2. Timeout pro Skill-Aufruf (z.B. 30s).
  3. Memory-Limit für Worker (z.B. 256MB via `resource.setrlimit`).
  4. Oder: Skills nur noch in der Sandbox ausführen, Hauptprozess
     koordiniert nur.
- **Aufwand:** 3–5 Tage.

### P1.7 — Git-Commit-Race bei parallelen Promotions
- **Status:** `SkillPromoter._git_commit` ruft `git add` + `git commit`
  auf. Bei parallelen Promotions kann `git commit` konkurrieren und
  mit "index.lock" fehlschlagen.
- **Risiko:** Promotions schlagen still fehl (`git_committed=False`),
  Skill-Code steht nicht im Git, Recovery schwer.
- **Aufgabe:**
  1. Lock um `_git_commit` (prozessglobal).
  2. Retry bei `index.lock`-Fehler (max 3, Backoff 100ms).
  3. Bei wiederholtem Fehlschlag: Warning loggen, Promotion trotzdem
     als Erfolg werten (Skill-Datei ist da, nur Git fehlt).
- **Aufwand:** 0,5 Tag.

## P2 — Vor Skalierung auf viele Nutzer (Performance / Kosten)

### P2.1 — LLM-Cost-Tracking
- **Status:** Kein Tracking von Token-Verbrauch oder Kosten.
- **Risiko:** Kosten-Explosion unbemerkt.
- **Aufgabe:**
  1. Bei jedem LLM-Call: `usage` aus dem Response extrahieren.
  2. In DB oder Metrik-System loggen (pro Skill, pro User, pro Intent).
  3. Optional: Hard-Limit pro Tag (`LLM_DAILY_TOKEN_LIMIT`).
- **Aufwand:** 1–2 Tage.

### P2.2 — Skill-Caching: avoid re-generating known skills
- **Status:** `IntentEngine` klassifiziert jede Anfrage via LLM. Ein
  User, der 10x "berechne Fibonacci" fragt, triggert 10x
  `create_skill`, obwohl der Skill schon existiert.
- **Risiko:** Verschwendete LLM-Calls, Sandbox-Zeit, Git-Historie
  voller Duplikate.
- **Aufgabe:**
  1. Cache für `IntentEngine.analyze`-Ergebnisse (key = user_request +
     Tool-List-Hash, TTL 5min).
  2. Vor `create_skill`: in `registry.registered_tools` prüfen, ob ein
     passender Skill schon da ist (semantisch oder Name).
- **Aufwand:** 1 Tag.

### P2.3 — WebSocket-Connection-Limits
- **Status:** Kein Limit für offene WebSocket-Verbindungen pro API-Key.
- **Risiko:** Ressourcen-Exhaustion, langsamer DoS.
- **Aufgabe:**
  1. Max-Connections-per-Key (konfigurierbar, default 5).
  2. Bei Überschreitung: Close mit Code 1008 (Policy Violation).
- **Aufwand:** 0,5 Tag.

### P2.4 — DB-Migration-Strategy
- **Status:** `db.py` hat nur `CREATE TABLE IF NOT EXISTS`. Keine
  Schema-Migrationen.
- **Risiko:** Bei Schema-Erweiterung (z.B. neue Spalte `tags` in
  `skills`) brechen alte Skills.
- **Aufgabe:**
  1. `alembic` oder `yoyo-migrations` integrieren.
  2. Schema-Version in DB speichern, bei Start migrieren.
  3. Erste Migration: aktuelle Schema-Version initialisieren.
- **Aufwand:** 1–2 Tage.

### P2.5 — Skill-Rollback in Produktion
- **Status:** `SkillPromoter.rollback` löscht die Datei und markiert
  sie in der DB als deleted. Es gibt keinen Weg, eine ältere Version
  eines Skills wiederherzustellen (nur der neueste Git-Stand ist da).
- **Risiko:** Ein fehlerhafter Skill wird promotet, User klagen, man
  kann nicht zur letzten funktionierenden Version zurückkehren ohne
  `git revert`-Akrobatik.
- **Aufgabe:**
  1. Bei jedem Promote: Version in DB speichern (via `SkillVersionManager`).
  2. `rollback` akzeptiert `version`-Parameter: alte Version aus
     Git-Historie (`git show <sha>:<file>`) wiederherstellen.
  3. API-Endpoint `POST /api/skills/{name}/rollback?version=X.Y.Z`.
- **Aufwand:** 1–2 Tage.

## P3 — Qualitäts- / Wartbarkeits-Verbesserungen

### P3.1 — Pre-existing ResourceWarnings fixen
- **Status:** Suite wirft 47 ResourceWarnings (ungeclosed sqlite-
  Connections, asyncio event loop). Nicht durch diese 25-Punkte-Arbeit
  verursacht, aber in Produktion relevant (File-Handle-Lecks).
- **Aufgabe:**
  1. `SkillStore` mit Context-Manager oder explizitem `conn.close()`.
  2. `test_ui_frontend.py` async event loop via `asyncio.new_event_loop()`.
- **Aufwand:** 0,5 Tag.

### P3.2 — `setup_mcp.py` Code-Coverage (75%) erhöhen
- **Status:** 36 von 144 Statements ungedeckt. Die echten
  `_WigoloClient`-Methoden (Popen-Start, Handshake-Timeout, Framing-
  Edge-Cases) sind teils ungetestet.
- **Aufgabe:**
  1. Edge-Case-Tests: Popen schlägt fehl, stdout EOF, malformed JSON-
  Body, Content-Length-Mismatch.
  2. Property-Test: round-trip JSON-RPC-Request → Response.
- **Aufwand:** 1 Tag.

### P3.3 — `skill_writer.py` Coverage (80%) erhöhen
- **Status:** 34 Statements ungedeckt, hauptsächlich
  `_run_local_tdd`-Pfad und `_stub_code`-Fallback-Pfade.
- **Aufgabe:**
  1. Test für `_run_local_tdd` mit echtem tempfile + pytest.
  2. Test für `_llm_classify`-Fallback bei `json.JSONDecodeError`.
- **Aufwand:** 0,5 Tag.

### P3.4 — `cli.py` Coverage (79%) erhöhen
- **Status:** 15 Statements ungedeckt. `skills_create` ist nur
  Placeholder ("Not yet implemented"), die `sandbox status`-Command
  hat keine echten Assertions.
- **Aufgabe:**
  1. `skills create` implementieren (triggert `SkillWriter.write_skill`
     via API oder direkt).
  2. `sandbox status` um Docker-Daemon-Check ergänzen.
- **Aufwand:** 1 Tag.

### P3.5 — `ui.py` Docs / ARIA-Verifizierung
- **Status:** ARIA-Attribute sind im Code, aber nicht automatisiert
  verifiziert.
- **Aufgabe:**
  1. axe-core oder pa11y in Frontend-Tests integrieren.
  2. WCAG-AA-Compliance-Report.
- **Aufwand:** 1–2 Tage.

### P3.6 — README-Doku für Produktion
- **Status:** README ist Dev-orientiert. Keine Doku für Deployment,
  Monitoring, Backup, Incident-Response.
- **Aufgabe:**
  1. `docs/DEPLOYMENT.md`: Docker-Compose-Setup, ENV-Variablen,
     Reverse-Proxy, TLS.
  2. `docs/OPERATIONS.md`: Backup der SQLite-DB und Skill-Dateien,
     Restore, Git-Historie-Maintenance.
  3. `docs/INCIDENT.md`: Was tun bei: Sandbox-Down, LLM-Down,
     Skill-Promotion-Loop, verstopfte Git-Historie.
- **Aufwand:** 2–3 Tage.

### P3.7 — Dependency-Pinning der übrigen Pakete
- **Status:** Nur `agno` ist gepinnt (#21). `fastapi`, `nicegui`,
  `docker`, `openai` etc. sind unpinned.
- **Risiko:** Breaking-Changes bei `uv sync` auf neuem System.
- **Aufgabe:**
  1. `uv lock --frozen` in CI nutzen.
  2. RenovateBot / Dependabot für Update-PRs.
  3. Bei Major-Update: manuelle Verifikation.
- **Aufwand:** 0,5 Tag Setup, dann kontinuierlich.

### P3.8 — Property-based Tests für SafetyChecker
- **Status:** `safety.py` ist 100% covered, aber ohne property-
  based Tests. Adversarial Inputs (Kommentare, dekoratoren,
  verschachtelte Attribute) könnten den Parser überlisten.
- **Aufgabe:**
  1. `hypothesis`-Strategien für Python-Source-Code-Fragments.
  2. Invariante: `check_code` ist idempotent.
  3. Invariante: `import os` in jedem Kontext (auch in Kommentaren?
     in Strings? in decorators?) wird klassifiziert als
     `forbidden_imports` ODER nicht (je nach Entscheidung).
- **Aufwand:** 1–2 Tage.

## P4 — Nice-to-have / Langfristig

### P4.1 — Mehrere Skill-Repositories
- **Status:** Nur ein `skills_dir`. Verschiedene Teams können nicht
  isoliert Skills verwalten.
- **Aufgabe:** Multi-Registry mit Prefixen (`team_a.weather`,
  `team_b.weather`).
- **Aufwand:** 2–3 Tage.

### P4.2 — Skill-Marktplatz (Share / Discover)
- **Status:** Skills leben nur lokal. Kein Sharing zwischen
  ToolKinetik-Instanzen.
- **Aufgabe:** Skill-Export/Import (Tarball + Metadaten), optional
  zentrales Repo.
- **Aufwand:** 1 Woche+.

### P4.3 — Fine-Tuning des Intent-Models
- **Status:** Intent-Klassifikation via generischem LLM. Spezialisiertes
  kleineres Modell wäre billiger und schneller.
- **Aufgabe:** Fine-tuned MiniLM für Intent-Klassifikation,
  Fallback auf LLM.
- **Aufwand:** 1 Woche+ (Daten sammeln, trainieren, eval).

### P4.4 — WebUI: Skill-Historie und Diff-View
- **Status:** NiceGUI zeigt nur geladene Skills, keine Historie.
- **Aufgabe:** Git-Log-View in UI, Diff zwischen Versionen, Rollback-
  Button.
- **Aufwand:** 2–3 Tage.

### P4.5 — Multi-Tenancy
- **Status:** Eine ToolKinetik-Instanz = ein Skill-Pool, ein LLM-Key.
- **Aufgabe:** Tenant-Isolation im FastAPI-Layer (Tenant-ID pro
  API-Key, separate DB, separate Skills-Dir).
- **Aufwand:** 1–2 Wochen.

## Zusammenfassung

| Priority | Items | Aufwand (Schätzung) |
|---|---|---|
| **P0 — Vor Produktivnahme** | 6 | 3–5 Tage |
| **P1 — Vor größerem Nutzerkreis** | 7 | 8–12 Tage |
| **P2 — Vor Skalierung** | 5 | 5–9 Tage |
| **P3 — Qualität / Wartbarkeit** | 8 | 7–11 Tage |
| **P4 — Nice-to-have** | 5 | 2–4 Wochen |
| **Total** | 31 | 6–9 Wochen (P0–P3) |

## Empfehlung

1. **P0 sofort:** P0.1 (Real-Docker-Test), P0.5 (API-Key-Policy),
   P0.6 (Secrets-Scan). Diese sind klein und kritisch.
2. **P0 dann:** P0.2–P0.4 (Real-Endpoint-Tests). Können parallel.
3. **P1 vor Pilot:** P1.1 (Frontend-Tests), P1.5 (Observability),
   P1.6 (Skill-Isolation).
4. **P2 bei Wachstum:** Wenn >10 aktive User.
5. **P3 kontinuierlich:** In Slack-Zeiten abarbeiten.

Kein Produktivbetrieb ohne P0. Pilotbetrieb mit P0+P1. Skalierung erst
mit P2.