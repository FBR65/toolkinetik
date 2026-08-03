# SPEC — Security Hardening & Typing (Tier 3)

Status: **DRAFT — wartet auf Freigabe**
Datum: 2026-08-03
Kontext: Analyse von `safety.py`, `app.py`, `coding_agent.py`, `tdd_loop.py`, `config.py`.
Klasse: Sicherheit/Auth — daher **Tier 3** mit explizitem Failure-Model.

## Ausgangsbefund (Baseline, vor jeder Änderung verifiziert)

- `uv run pytest tests/ -q` → **135 passed** (1 StarletteDeprecationWarning)
- `uv run ruff check src` → All checks passed
- `uv run mypy src` → Success, 0 errors
- Repo: git, Branch `master`, HEAD `d0a91ac`, Arbeitsbaum nur AGENTS.md geändert

## Umfang — Behaviors (append-only, werden bei Bedarf revidiert)

### B1 — SafetyChecker: Whitelist statt unvollständiger Blacklist
Problem: `safety.py` blockt nur `os, subprocess, shutil, ctypes` (Import) bzw. 6 Call-Patterns.
Erlaubt bleiben u.a. `socket`, `urllib`, `requests`, `pathlib` — ein Skill kann damit außerhalb
der Sandbox Netzwerkzugriff aufbauen. Die Sandbox erzwingt `network_mode="none"`, aber
`promotion.py` schreibt den Skill ungefiltert in `skills/`, die der Registry direkt lädt
(`registry.py`). Der Blacklist-Ansatz ist ein falsches Sicherheitsgefühl.

Entscheidung: **Whitelist-basierte Zulassung.** Ein Skill ist nur `passed=True`, wenn
**alle** importierten Top-Level-Module in einer erlaubten Liste stehen UND keine verbotenen
Calls vorkommen. Verbotene Calls (eval/exec/os.system/subprocess.*/compile/__import__)
bleiben hart blockiert.

- Erlaubte Standardbibliothek (Whitelist), initial: `math`, `json`, `re`, `datetime`, `collections`,
  `itertools`, `functools`, `random`, `statistics`, `typing`, `enum`, `decimal`, `fractions`.
- Erlaubte Skill-eigene Module: relative Imports / Module aus dem skills_dir.
- Akzeptanzkriterien:
  - GIVEN Code `import socket` WHEN `check_code` THEN `passed is False` AND `socket` in `forbidden_imports`.
  - GIVEN Code `import json` WHEN `check_code` THEN `passed is True` (Regression, besteht weiterhin).
  - GIVEN Code `import os` THEN `passed is False` (Regression, unverändert).
  - GIVEN Code `def add(a,b): return a+b` THEN `passed is True` (Regression).
  - GIVEN Code `import math; def f(): return math.sqrt(4)` THEN `passed is True`.
  - GIVEN Code `import urllib.request` THEN `passed is False`.
  - Negativ-Invariante: bestehende Tests in `tests/test_safety.py` bleiben grün bis auf neu
    hinzukommende Assertions — keine bestehende Assertion wird abgeschwächt.
- Mutation-Kriterien: (a) Whitelist-Eintrag entfernen → Test der auf `import json` passed=True prüft, fällt;
  (b) Whitelist-Vergleich auf `==` statt `in` umstellen → Whitelist-Submodul-Test fällt; (c) `socket` aus
  Whitelist-Einträgen entfernen → socket-Test fällt.

### B2 — Timing-sicherer API-Key-Vergleich
Problem: `app.py:33` und `app.py:94` vergleichen per `!=` → Timing-Angriff möglich.
- GIVEN `verify_api_key("wrong")` THEN HTTPException 403, aber Vergleich läuft über
  `secrets.compare_digest`.
- Akzeptanz: `secrets` ist stdlib, keine neue Dependency. `tests/test_app.py` bleibt grün
  (403/200-Verhalten unverändert).
- Mutation: `compare_digest` durch `==` ersetzen → neuer Test (der prüft, dass `compare_digest`
  importiert/aufgerufen wird) fällt.

### B3 — Dataclass-Felder typisieren
Problem: `list` (untypisiert) in `safety.SafetyReport`, `coding_agent.QualityResult`,
`coding_agent.SkillSpec`, `tdd_loop.SecurityResult`, `tdd_loop.TDDResult`, `auto_docs.SkillInfo`.
Mypy verliert dadurch Wirkung.
- Akzeptanz: alle Felddeklarationen auf `list[str]` / `list[dict]` / `list[SkillInfo]` präzisiert;
  `mypy src` bleibt bei 0 Fehlern; `ruff` bleibt grün.
- Kein Verhaltensunterschied — bestehende Tests unverändert grün.
- Mutation: ein Feld auf `list` zurücksetzen → `mypy` muss auf `list[...]`-Verletzung hinweisen
  (mypy ist hier das Kill-Nachweismittel).

### B4 — Pfad-Traversal-Schutz in SkillVersionManager
Problem: `_skill_path` (`safety.py:261`) verknüpft `skills_dir / f"{skill_name}.py"` ohne Validierung —
`../` erlaubt Zugriff außerhalb. `bump_version` schreibt sogar (`safety.py:213`).
- GIVEN `skill_name = "../../etc/passwd"` WHEN `_skill_path` THEN Zugriff verweigert / normalisiert.
- Akzeptanz: `_skill_path` löst den Namen innerhalb von `skills_dir` auf und wirft
  `ValueError` (oder returns None), falls das resolved path außerhalb von `skills_dir` liegt.
  `get_version`/`bump_version` geben dann einen sicheren Default zurück bzw. propagieren
  keinen Schreibzugriff nach außen.
- Mutation: Pfad-Check entfernen → Traversal-Test fällt.

### B5 — Kopplung in TDDLoop aufheben
Problem: `tdd_loop.py:162,173` ruft `CodingAgent._debugging_prompt` und `_call_cli`
(private Methoden) auf.
- Akzeptanz: `CodingAgent` bekommt öffentliche Methode `revise_code(code, error_trace) -> str | None`; 
  `TDDLoop._get_revised_code` nutzt diese. Verhalten identisch (Tests in `test_tdd_loop.py` unverändert grün).
- Mutation: `revise_code` so ändern, dass `None` bei leerem Output zurückgegeben wird → Test,
  der den Retry-Pfad deckt, verhält sich wie zuvor (kein Bruch) — hier ist die Mutation eher ein
  Refactoring-Nachweis; primäres Kill-Mittel ist die Testabdeckung des Retry-Pfads.

## Invarianten, die überleben müssen (Negativ-Klauseln)

- Alle 135 Bestandstests bleiben grün (0 NEW failures). Baseline-Warnung (StarletteDeprecation)
  bleibt unangetastet.
- `ruff check src` → 0 neue Warnings.
- `mypy src` → 0 neue Errors (B3 darf nur präzisieren).
- Keine Änderung an öffentlichen Signaturen, die von `tests/` importiert werden.
- README-Testzahl (126 → 135) wird NICHT Teil dieser SPEC — dokumentiert, aber außerhalb Scope.
- `skills/__pycache__/` ist bereits von `.gitignore` (`__pycache__/`) abgedeckt — keine Aktion.

## Failure-Model (Tier 3)

| Failure-Modus | Fängt B? | Mittel |
|---|---|---|
| Skill schreibt Datei / Netzwerkzugriff außerhalb Sandbox | B1, B4 | Whitelist + Traversal-Check, Mutation |
| API-Key-Brute-Force/Timing | B2 | compare_digest + Regressionstests |
| Typfehler in Skill-Metadaten zur Laufzeit | B3 | Mypy als Gate |
| Refactoring-Kopplungsbruch | B5 | volle Suite nach Refactor |
| Whitelist zu restriktiv (echte Skills brechen) | B1 | Real-Execution: `check_skill_file` auf `math_skill.py` & `weather_skill.py` (nur stdlib) → passed=True |
| Nicht behandelte Module brechen Registrierung | B1 | volle Suite (registry lädt skills) |

Nicht abgedeckte Modi (explizit, in EVIDENCE als Known-Limits): keine Änderung am
Docker-Sandbox-Verhalten; die Sandbox bleibt die harte Netzwerk-Grenze — B1 ist Defense-in-Depth,
kein Ersatz.

## Setup-Plan

- **Dependencies:** keine neuen. `secrets`, `pathlib` sind stdlib und bereits importiert.
- **Tools:** vorhanden (pytest, ruff, mypy, uv). Kein neues Tool.
- **Git:** Checkpoint-Commits bei jedem GREEN/REFACTOR unter folgender Freigabe —
  [ ] Checkpoint-Commits erlaubt (Standard-Cadence laut AGENTS.md)
  [ ] KEINE Commits (nur Arbeitsbaum; EVIDENCE identifiziert Zustand per tree-hash)
- **Neue Dateien:** diese SPEC (`docs/SPEC-safety-hardening.md`), später `docs/EVIDENCE.md`.
- **Gauntlet-Skript:** `scripts/gauntlet.sh` (persistiert, führt alle Layer aus) — wird nach Freigabe
  angelegt.
- **Mutation:** manuell (kein Mutation-Tool im Projekt); Mutanten werden in EVIDENCE gelistet
  und per `git diff` zurückgerollt (bei erlaubten Commits) bzw. per Suite-Neulauf (sonst).

## Geplante Testdateien

- Neue Tests in `tests/test_safety.py` (B1, B4) — nur Hinzufügen, keine Bestandsassertions ändern.
- Neue Tests in `tests/test_app.py` (B2).
- Bestehende Tests unverändert (B3, B5) — Nachweis über mypy + volle Suite.

## Offene Fragen für die Freigabe

1. **B1-Whitelist-Umfang:** Soll `pathlib` (Dateisystemzugriff, aber lokal & harmlos in Sandbox)
   in die Whitelist? Vorschlag: NEIN für Skill-Ausführung außerhalb Sandbox, da Skills in der
   Prod-`skills/` laufen. → Empfehlung: `pathlib` NICHT zulassen.
2. **B1-Breite:** Whitelist-Ansatz ändert bestehendes Verhalten für `import json` NICHT (war erlaubt).
   Aber jeder Import außerhalb der Liste wird neu geblockt — auch `numpy`/`pandas`, falls je gebraucht.
   Trade-off akzeptiert? Empfehlung: Ja, explizit erweiterbar.
3. **Git-Cadence** laut obiger Setup-Plan-Frage.

---
## Freigabe

Freigegeben am: _______________  Signatur: _______________
(Ankreuzen der Git-Frage oben ist Teil der Freigabe)
