# Operations Guide — ToolKinetik

## Backup

### SQLite Database
```bash
# Backup (uses sqlite3 .backup for consistent snapshot)
sqlite3 data/toolkinetik.db ".backup data/backup_$(date +%Y%m%d).db"

# Or simple file copy (stop the server first for consistency)
cp data/toolkinetik.db data/backup_$(date +%Y%m%d).db
```

### Skills Directory
```bash
# Skills are tracked in git — push to a remote for backup
git add skills/
git commit -m "backup: skills snapshot"
git push origin master
```

### Restore
```bash
# Stop the server
docker compose down

# Restore DB
cp data/backup_20260805.db data/toolkinetik.db

# Restore skills from git
git checkout <commit-sha> -- skills/

# Restart
docker compose up -d
```

## Git History Maintenance

Skill promotions create git commits. Over time the history grows:
```bash
# Check history size
git count-objects -vH

# Garbage collect (safe, run periodically)
git gc --prune=now

# If history is too large (thousands of skill commits):
# Consider squashing old history with git filter-repo
```

## Monitoring

### Log Format
Logs are structured JSON to stdout:
```json
{"time": "2026-08-05T...", "level": "INFO", "module": "toolkinetik.app", "request_id": "abc123", "message": "..."}
```

### Key Metrics
- `skill_promote_total` — skill promotion count (by success/failure)
- `llm_call_total` — LLM API call count
- `ws_connections_active` — active WebSocket connections

### Alerting Recommendations
- Alert on `/api/health/deep` returning `unhealthy`
- Alert on `skill_promote_total{success="false"}` rate > 50%
- Alert on LLM call latency > `LLM_TIMEOUT` seconds

## Database Maintenance

### WAL Checkpoint
WAL mode is enabled by default. SQLite auto-checkpoints, but for busy servers:
```bash
sqlite3 data/toolkinetik.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

### Schema Version
```bash
sqlite3 data/toolkinetik.db "SELECT * FROM schema_version;"
```