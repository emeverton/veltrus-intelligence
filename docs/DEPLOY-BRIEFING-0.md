# Deploy Validation — Briefing #0

**Date:** 2026-06-23  
**VPS:** 76.13.232.175  
**Stack:** `intelligence` (api + qdrant + nats)  
**URL:** https://intelligence.ehos.com.br

## Test Results

| # | Check | Result |
|---|-------|--------|
| 1 | `curl https://intelligence.ehos.com.br/health` | `{"status":"ok","service":"veltrus-intelligence","version":"0.1.0","debug":false}` |
| 2 | `docker stack ps intelligence` | 3/3 Running: `intelligence_api`, `intelligence_qdrant`, `intelligence_nats` |
| 3 | Qdrant internal (`intelligence_qdrant:6333/healthz`) | `healthz check passed` |
| 4 | NATS internal (`intelligence_nats:8222/healthz`) | `{"status":"ok"}` |
| 5 | `pytest tests/ -v` | `test_health_endpoint PASSED` |
| 6 | `veltrus-api.ehos.com.br/health` | **404** — `veltrus_api` service at 0/1 replicas since ~6 days ago (pre-existing, unrelated to intelligence deploy) |
| 7 | Port 8001 (intelligence) | Uvicorn listening inside container; Traefik routes HTTPS |

## Stack Services

```
intelligence_intelligence_api    1/1  veltrus-intelligence:latest
intelligence_intelligence_qdrant 1/1  qdrant/qdrant:v1.11.5
intelligence_intelligence_nats   1/1  nats:2.10-alpine (-js)
```

## Notes

- `.env` on VPS: `ANTHROPIC_API_KEY` copied from `/opt/veltrus/.env`; `DATABASE_URL` points to `postgres:5432/veltrus_intelligence`
- Traefik: `certresolver=letsencryptresolver`, TLS active on `intelligence.ehos.com.br`
- Network: `emeverton` (external overlay)
