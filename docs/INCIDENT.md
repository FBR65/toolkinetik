# Incident Response Guide — ToolKinetik

## Common Incidents

### Sandbox Down (Docker Unavailable)

**Symptoms:** `/api/health/deep` returns `degraded` or `unhealthy`, skill creation fails.

**Diagnosis:**
```bash
docker info  # Is the daemon running?
docker ps    # Are containers running?
curl http://localhost:8000/api/health/deep
```

**Resolution:**
1. Restart Docker daemon: `sudo systemctl restart docker`
2. If disk full: `docker system prune -a`
3. Check sandbox image: `docker images | grep toolkinetik-sandbox`
4. Rebuild sandbox image: the `SandboxRunner` rebuilds automatically on next use

**Impact:** New skill creation fails; existing skills still work.

---

### LLM Endpoint Down

**Symptoms:** Intent classification degrades to `chat`, skill generation fails.

**Diagnosis:**
```bash
curl $OPENAI_API_BASE/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"
```

**Resolution:**
1. Check LLM service (Ollama, vLLM, OpenAI): is it running?
2. Check `OPENAI_API_BASE` and `OPENAI_API_KEY` in `.env`
3. Check network connectivity to the endpoint
4. If Ollama: `ollama list` — is the model pulled?

**Impact:** All LLM-dependent features fail (intent, codegen, revise). Skills already promoted still work.

---

### Skill Promotion Loop (Repeated Failures)

**Symptoms:** Git history filling with failed promotion commits, skill keeps regenerating.

**Diagnosis:**
```bash
git log --oneline -20 -- skills/
# Check if the same skill is being promoted repeatedly
```

**Resolution:**
1. Check the skill's tests — are they flaky?
2. Increase `max_retries` in SkillWriter
3. Manually rollback the skill: `curl -X POST http://localhost:8000/api/skills/{name}/rollback -H "X-API-Key: $KEY"`
4. If stuck, delete the skill file and let the next request regenerate it

---

### Clogged Git History

**Symptoms:** `git clone` is slow, repo size growing rapidly.

**Resolution:**
```bash
# Squash old skill commits (keeps recent history)
git rebase -i HEAD~100  # squash last 100 commits

# Or use git filter-repo for deep cleanup
pip install git-filter-repo
git filter-repo --path skills/ --force
```

**Prevention:** Run `git gc --prune=now` weekly.

---

### Database Locked

**Symptoms:** `OperationalError: database is locked` in logs.

**Diagnosis:**
```bash
sqlite3 data/toolkinetik.db "PRAGMA journal_mode;"
# Should return "wal"
```

**Resolution:**
1. WAL mode should prevent this (check it's enabled)
2. `PRAGMA busy_timeout=5000` is set — should auto-retry
3. If persistent: stop the server, run `sqlite3 data/toolkinetik.db "PRAGMA wal_checkpoint(TRUNCATE);"`, restart

---

### WebSocket Connection Exhaustion

**Symptoms:** Clients can't connect, `1008 Policy Violation` close code.

**Diagnosis:**
```bash
# Check active connections via metrics
curl http://localhost:8000/metrics | grep ws_connections
```

**Resolution:**
1. Default limit: 5 connections per API key
2. Increase via `set_max_ws_connections(N)` in code
3. Check for clients not closing connections properly