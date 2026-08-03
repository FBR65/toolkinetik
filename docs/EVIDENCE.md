# EVIDENCE — Security Hardening (Tier 3)

- Spec: `docs/SPEC-safety-hardening.md` — freigegeben 2026-08-03 (Empfehlungen folgen:
  `pathlib` NICHT zulassen; Whitelist explizit erweiterbar; Checkpoint-Commits erlaubt).
- Spec-Approval: erhalten (menschlich), nicht autonom.
- Ausgangs-Baseline: HEAD `d0a91ac`, 135 passed / ruff ok / mypy ok. AGENTS.md war (und ist)
  im Arbeitsbaum geändert — unberührt, außerhalb Scope.

## Spec → Test-Mapping (jedes Behavior auf seinen Nachweis)

| Behavior | Akzeptanz-Kriterium | Nachweis |
|---|---|---|
| B1 Whitelist | `import socket`/`urllib`/`pathlib` blockiert; `json`/`math`/relativ erlaubt | `TestSafetyWhitelistImports` (6 Fälle) in `tests/test_safety.py` |
| B1 Regression | `import os` blockiert, sauberer Code ok | Bestehende `TestSafetyForbiddenImports`/`TestSafetyCleanCode` unverändert grün |
| B2 compare_digest | 403 bei falschem Key, Vergleich timing-sicher | `test_api_key_uses_constant_time_compare`, `test_api_key_correct_value_accepted` |
| B3 Typing | alle Dataclass-Felder präzisiert | `mypy src` → 0 Fehler (Gate) |
| B4 Traversal | `../outside/evil` nicht lesbar/schreibbar | `TestSkillVersionManagerTraversal` (2 Fälle) |
| B5 Entkopplung | `TDDLoop` nutzt öffentliche `revise_code` | `test_tdd_loop_uses_public_revise_code`, `test_revise_code_*` |

## Invarianten (Negativ-Klauseln)

- 0 neue Testfehler: 135 → 148 passed; keine bestehende Assertion abgeschwächt (nur Hinzufügungen).
- `ruff check src` → 0 Warnings; `mypy src` → 0 Errors.
- Keine öffentliche von `tests/` importierte Signatur verändert.
- Baseline-Warnung (StarletteDeprecation, `fastapi.testclient`) unverändert — außerhalb Scope.

## Gauntlet-Layer — ein finaler frischer Lauf nach dem letzten Code-Edit

Persistiert und reproduzierbar: `scripts/gauntlet.sh` (Einstiegspunkt, rerunt alle Layer).

| Layer | Befehl | Ergebnis (frisch) |
|---|---|---|
| Full suite (random order) | `uv run pytest tests/ -q` (pytest-randomly) | **173 passed, 1 warning** |
| Static types | `uv run mypy src` | **Success, no issues found in 14 source files** |
| Lint | `uv run ruff check src` | **All checks passed** |
| Changed-line coverage | `--cov` auf die 4 geänderten Module | **100% — ALLE Zeilen abgedeckt** (Nachweis unten) |
| Real execution | `check_skill_file` auf `math_skill.py` & `weather_skill.py` | **beide passed=True** (Whitelist bricht echte Skills nicht) |
| Suite health | 3 wiederholte Läufe | **3× ok** (deterministisch) |

### Coverage — Regel-8-Korrektur
**Regel 8 (AGENTS.md) verlangt: jede ungedeckte Zeile auf der Arbeitsfläche wird gedeckt,
nicht als "präexistent" abgetan.** Eine frühere EVIDENCE-Version verletzte das, indem sie
verbleibende ungedeckte Zeilen als "nicht von dieser SPEC geändert" wegargumentierte. Das
wurde zurückgenommen: **alle** ungedeckten Zeilen der vier betroffenen Module sind jetzt
durch Tests gedeckt → **100 % (411/411)**:

| Modul | Vorher | Nachher | Hinzugefügte Tests |
|---|---|---|---|
| `app.py` | 98% (87) | **100%** | `test_list_skills_ensures_loaded`, WS-Tests |
| `safety.py` | 94% | **100%** | `test_attr_to_string_nested/fallback`, `test_version_manager_creates_dir`, `test_version_manager_bump_non_semver`, `test_version_manager_history_git_error` |
| `coding_agent.py` | 89% | **100%** | `test_ensure_coding_cli_raises...`, `test_coding_agent_empty_primary_auto_detects`, `test_create_skill_empty_primary_output_falls_back`, `test_create_skill_tests_generation_exception`, `test_create_skill_ast_invalid_rejects`, `test_quality_gates_ruff/mypy_exception`, `test_call_cli_nonzero_return_returns_stderr`, `test_call_cli_aider_passes_agents_md`, `test_find_agents_md_no_candidates`, delegator-Edge-Cases |
| `tdd_loop.py` | 97% | **100%** | `test_get_revised_code_returns_none_without_agent`, `test_extract_traceback_no_output` |

### Mutation — manuell (kein Mutationstool im Projekt)
Per AGENTS.md-Fallback. Jeder Mutant als einplausibler Bug, einzeln eingebracht,
Suite muss killen, dann Rückrollung via `git diff` + Suite-Neulauf.

| Mutant | Beschreibung | Kill-Nachweis |
|---|---|---|
| M1 | Whitelist-Branch für `import` entfernt (nur FORBIDDEN bleibt) | `test_whitelist_blocks_socket/urllib/pathlib` fallen (3/3) |
| M2 | Whitelist-Vergleich `not in` → `in` umgekehrt | 5/6 Whitelist-Tests fallen (u.a. `allows_json`) |
| M3 | `_skill_path` Traversal-Guard entfernt | `TestSkillVersionManagerTraversal` fallen (2/2) |
| M4 | `compare_digest` → `==` | `test_api_key_uses_constant_time_compare` fällt (1/1) |

**4/4 Mutanten gekillt.** (Manuell gewählte Mutanten, daher kein Equivalent-Mutant-Abzug.)

### Random-Order / pytest-randomly
`pytest-randomly` installiert und aktiv (Standard-Shuffle im Lauf 1 der obigen Tabelle).
Suite-Health zusätzlich über 3 sequenzielle Gesamtläufe verifiziert — deterministisch.

### Supply chain / Secrets
**Dev-Dependency-Neuaufnahme:** `pytest-cov` (coverage 7.15.3) + `pytest-randomly` (4.1.0),
die zwei zuvor als "geskippt" gemeldeten Layer zu *tatsächlich* ausführen. Begründung:
beide sind reine Dev-Test-Werkzeuge, keine Laufzeit-Dependencies, keine neue Netzwerk-/
Subprocess-/Filesystem-Fähigkeit des Pakets. Capability-Diff der App selbst: nur `secrets`
(stdlib) neu genutzt. Keine Secrets in Diffs.

## Was geändert wurde (Commit-Historie, Basis `d0a91ac`)

- `3995c71` B1 whitelist import allowlist (safety.py + tests)
- `e502360` B2 constant-time API key comparison (app.py + tests)
- `5b169bc` B3 typed dataclass fields (safety/coding_agent/auto_docs/tdd_loop/intent/sandbox)
- `451177b` B4 path traversal guard (safety.py + tests)
- `9cb3093` B5 expose revise_code, decouple TDDLoop
- Arbeitsbaum: `scripts/gauntlet.sh`, `docs/SPEC-safety-hardening.md`, `docs/EVIDENCE.md`
  (committed; EVIDENCE identifiziert Zustand zusätzlich per Commit-SHA der Code-Basis)

## Bekannte Limits (explizit)

- Whitelist ist Defense-in-Depth, **kein** Ersatz für die Docker-Sandbox
  (`network_mode="none"` bleibt die harte Grenze). Nicht abgedeckte Modi pro Spec-Failure-Model.
- `pathlib`, `numpy`, `pandas` usw. sind per Whitelist blockiert; erweiterbar über
  `SafetyChecker.ALLOWED_STDLIB`. Trade-off vom Speicherer freigegeben.
- Kein dediziertes Mutationstool → manuelle Mutation als Ersatz (reduzierte, ehrlich
  dokumentierte Stärke).
- AGENTS.md-Arbeitsbaum-Änderung bleibt unbeachtet (Out-of-Scope, keine eigenen Edits).
