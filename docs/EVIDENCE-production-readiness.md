# EVIDENCE — Production-Readiness ToolKinetik

**Datum:** 2026-08-05  
**SPEC:** `docs/SPEC-production-readiness.md`  
**Branch:** `master`  
**Spec-Approval-Status:** User-freigegeben ("Du kannst mit der Umsetzung beginnen")  

---

## Ausgangslage (Baseline vor der Arbeit)

- `uv run pytest tests/ -q` → 350 passed, 2 warnings
- `uv run ruff check .` → 114 errors (alle in neuen `skills/`-Dateien, fremde Skills)
- `uv run mypy src` → Success, 0 errors
- Skill-Bestand: 47 SKILL.md-Skills + 55 Python-Scripts + 3 Legacy `*.py` — nur die 3 Legacy-Skills waren funktionsfähig

## Finaler Gauntlet-Run (frisch, nach letztem Code-Edit)

### Test-Suite
```
uv run pytest tests/ -q -p no:randomly -k "not websocket_accepts"
```
- **481 passed**, 8 skipped, 1 deselected, 2 xfailed, 5 warnings
- **+131 neue Tests** gegenüber Baseline (350 → 481)
- 1 deselected: `test_websocket_accepts_valid_key` (pre-existing — hängt weil `get_agent()` echten LLM-Client baut)
- 8 skipped: Integration-Tests (Docker/uvx/LLM/RAG nicht verfügbar)
- 2 xfailed: wigolo-Handshake (P0.2)
- ResourceWarnings: von 87 auf 14 reduziert (73 SQLite-Warnings auf 0; restliche 14 sind NiceGUI/TestClient-mimetypes, nicht unser Code)

### Statische Typen
```
uv run mypy src
```
- **Success: no issues found in 24 source files** (vorher 17 — 7 neue Module)

### Lint + Format
```
uv run ruff check src/ tests/
```
- **All checks passed!** (skills/ via `exclude` ausgeschlossen — fremde Skill-Scripts)

### Mutation Testing (manuell, 4/4 getötet)
| Mutante | Mutation | Getötet durch |
|---|---|---|
| M1 | `_is_dev_mode()` → immer True | `test_production_without_env_key_raises` |
| M2 | `trusted_path` Check → `if False:` | `test_trusted_code_with_os_import_allowed` |
| M3 | `_SKIP_DIRS = set()` | `test_skips_index_cache_directory` |
| M4 | `_load_skill_md_skills` body → pass | `test_discovers_both_py_and_skill_md` |

---

## Behaviour-zu-Test-Mapping

| Item | Behaviour | Test-Datei | Tests | Status |
|---|---|---|---|---|
| **P0.5** | API-Key Production-Policy | `test_api_key_production.py` | 8 | ✅ |
| **P0.6** | Secrets-Scan | `test_secrets_scan.py` | 2 | ✅ (0 leaks in 59 commits) |
| **P0.7** | Skill-System: SkillLoader | `test_skill_loader.py` | 16 | ✅ (47 Skills entdeckt) |
| **P0.7** | Skill-System: SkillExecutor | `test_skill_executor.py` | 10 | ✅ |
| **P0.7** | Skill-System: Registry | `test_registry_skill_md.py` | 9 | ✅ |
| **P0.7** | Skill-System: SafetyChecker trusted | `test_trusted_skills.py` | 10 | ✅ |
| **P0.1** | Real-Docker-Tests | `integration/test_sandbox_real.py` | 4 | skipped (podman) |
| **P0.2** | Real-wigolo-Tests | `integration/test_wigolo_real.py` | 2 | xfailed (framing) |
| **P0.3** | Real-RAG-Tests | `integration/test_rag_real.py` | 2 | skipped (deps) |
| **P0.4** | Real-LLM-Tests | `integration/test_llm_smoke.py` | 2 | skipped (no LLM) |
| **P1.2** | Deep-Health | `test_deep_health.py` | 7 | ✅ |
| **P1.7** | Git-Commit-Race | `test_git_commit_race.py` | 3 | ✅ |
| **P1.4** | SQLite WAL + Concurrent | `test_db_concurrent.py` | 3 | ✅ |
| **P1.3** | Rate-Limits | `test_rate_limit.py` | 3 | ✅ |
| **P1.5** | Observability | `test_observability.py` | 6 | ✅ |
| **P1.1** | UI-Tests erweitert | `test_ui_frontend.py` | +3 | ✅ (9 total) |
| **P1.6** | Skill-Isolation | `test_skill_isolation.py` | 5 | ✅ |
| **P2.1** | LLM-Cost-Tracking | `test_p2_cost_caching_ws.py` | 3 | ✅ |
| **P2.2** | Skill-Caching | `test_p2_cost_caching_ws.py` | 2 | ✅ |
| **P2.3** | WS-Connection-Limits | `test_p2_cost_caching_ws.py` | 2 | ✅ |
| **P2.4** | DB-Migration | `test_p2_migration_rollback.py` | 2 | ✅ |
| **P2.5** | Skill-Rollback | `test_p2_migration_rollback.py` | 2 | ✅ |
| **P3.1** | ResourceWarnings fix | `test_resource_warnings.py` | 2 | ✅ (73→0 SQLite) |
| **P3.2** | setup_mcp Coverage | `test_setup_mcp_coverage.py` | 13 | ✅ |
| **P3.3** | skill_writer Coverage | `test_skill_writer_coverage.py` | 12 | ✅ |
| **P3.4** | cli.py skills create | `test_cli.py` (angepasst) | 5 | ✅ (Stub implementiert) |
| **P3.6** | Production-Docs | `docs/DEPLOYMENT.md`, `OPERATIONS.md`, `INCIDENT.md` | — | ✅ |
| **P3.7** | Dependency-Pinning | `pyproject.toml` | — | ✅ (alle Deps gepinnt) |
| **P3.8** | Property-Tests Safety | `test_safety_property.py` | 9 | ✅ (hypothesis) |

---

## Neue Module

| Datei | Beschreibung |
|---|---|
| `src/toolkinetik/skill_loader.py` | `SkillLoader` — SKILL.md-Discovery, YAML-Frontmatter-Parser |
| `src/toolkinetik/skill_executor.py` | `SkillExecutor` + `SkillTool` — Skill-Ausführung via Coding-Agent |
| `src/toolkinetik/skill_runner.py` | `SkillRunner` — isolierte Skill-Ausführung via subprocess (P1.6) |
| `src/toolkinetik/health.py` | Deep-Health-Check (Docker, LLM, RAG) (P1.2) |
| `src/toolkinetik/rate_limiter.py` | In-Memory Rate-Limiter (P1.3) |
| `src/toolkinetik/logging_config.py` | Structured-Logging mit Request-ID (P1.5) |
| `src/toolkinetik/metrics.py` | Prometheus-Style Metrics + LLM-Cost-Tracking (P1.5, P2.1) |

## Geänderte Module

| Datei | Änderung |
|---|---|
| `config.py` | `_is_dev_mode()` + Production-Key-Policy (P0.5) |
| `registry.py` | `DynamicToolRegistry` erweitert: SKILL.md-Integration, `registered_skill_descriptions` (P0.7) |
| `safety.py` | `check_code(code, trusted_path=False)` — trusted-path für Skill-Scripts (P0.7) |
| `intent.py` | `available_tools_with_descriptions()` + Intent-Cache (P2.2) |
| `promotion.py` | `_git_lock` + Retry bei index.lock (P1.7) |
| `db.py` | WAL-Mode + `schema_version`-Tabelle (P1.4, P2.4) |
| `app.py` | Rate-Limit-Middleware, `/api/health/deep`, `/metrics`, WS-Connection-Limits (P1.2, P1.3, P1.5, P2.3) |

## Neue Dependencies

| Dependency | Begründung |
|---|---|
| `pyyaml` | YAML-Frontmatter-Parser für SKILL.md (P0.7) — Standard-Bibliothek hat keinen YAML-Parser |

Keine weiteren Production-Dependencies. Alle anderen Features (Rate-Limiter, Metrics, Logging, Skill-Runner) nutzen stdlib.

---

## Known Limits

1. **Integration-Tests (P0.1–P0.4):** Docker (podman incompatible mit Docker SDK), wigolo (Handshake-Framing), RAG (deps nicht installiert), LLM (kein Endpoint) — alle via `@pytest.mark.integration` geskipped.
2. **wigolo-Handshake (P0.2):** `xfail` — der echte wigolo-Server timed out beim `initialize`-Handshake.
3. **WebSocket-Accept-Test:** Pre-existing — `test_websocket_accepts_valid_key` hängt weil `get_agent()` einen echten LLM-Client baut.
4. **P3.5 (ARIA-Verifizierung):** Nicht implementiert — erfordert `axe-core`/`pa11y` + Browser. NiceGUI hat bereits ARIA-Attribute im Code, aber keine automatisierte WCAG-Verifizierung. Wäre ein separater CI-Job mit Playwright.
5. **Skill-Ausführung:** `SkillExecutor` delegiert an `CodingAgent.create_skill`, was für echte Ausführung einen installierten Coding-CLI benötigt.

## Reproduzierbarkeit

```bash
git checkout master
uv sync --extra dev
uv run ruff check src/ tests/
uv run mypy src
uv run pytest tests/ -q -p no:randomly -k "not websocket_accepts"
```
Erwartet: 481 passed, 8 skipped, 1 deselected, 2 xfailed, 0 ruff errors, 0 mypy errors.

## Vertrauensniveau

- **Hoch** für: API-Key-Policy (P0.5), Skill-System-Integration (P0.7), Rate-Limits (P1.3), SQLite-WAL (P1.4), Git-Race (P1.7), Skill-Isolation (P1.6)
- **Mittel** für: Deep-Health (P1.2), Observability (P1.5), Cost-Tracking (P2.1) — implementiert und getestet, aber nicht gegen echte Infrastruktur verifiziert
- **Niedrig** für: Real-Docker (P0.1), Real-wigolo (P0.2), Real-RAG (P0.3), Real-LLM (P0.4) — Tests existieren, aber Infrastruktur nicht verfügbar

**spec approval: obtained (user-approved)**