# AGENTS.md — veltrus-intelligence

## Stack
- Python 3.12, FastAPI, LangGraph, Qdrant, NATS, PostgreSQL
- Deploy: Docker Swarm no VPS 76.13.232.175

## Deploy
```bash
cd /opt/veltrus-intelligence
set -a && source .env && set +a   # obrigatório antes do stack deploy
docker build -t veltrus-intelligence:latest .
docker stack deploy -c docker-compose.yml intelligence
docker exec -w /app $(docker ps -q -f name=intelligence_intelligence_api) alembic upgrade head
```
- Reverse proxy: Traefik com `certresolver=letsencryptresolver` — NUNCA `letsencrypt`
- NUNCA usar Caddy
- Rede Swarm: `emeverton` (external: true)
- Porta da API: 8001 (8000 é do veltrus-ads-agent)

## Convenções de código
- Todos os imports absolutos a partir de `src/`
- `PYTHONPATH=/app` configurado no Dockerfile
- Configuração via pydantic-settings (não hardcodar valores)
- NUNCA commitar `.env`

## Próximas camadas (não implementar antes do briefing)
- Briefing #1: Identity Graph (Postgres + Union-Find) — **concluído**
- Briefing #2: Attribution Engine (Shapley + PyMC + Meridian)
- Briefing #3: Revenue Graph + Creative Graph (Apache AGE entra aqui)
- Briefing #4: Agent Layer (LangGraph + Claude API)
- Briefing #5: AI Modalities (FLUX, Wan2.1, Kokoro, Hunyuan3D via Vast.ai)

## Migrations (produção)
- Rodar **dentro do container** após deploy: `alembic upgrade head`
- NUNCA `docker service update --args` para mudar CMD — usar `docker stack deploy`
- DATABASE_URL no `.env` usa `postgresql://`; engine async usa `postgresql+asyncpg://` via `async_url()`
