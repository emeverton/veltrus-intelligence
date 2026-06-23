# AGENTS.md — veltrus-intelligence

## Stack
- Python 3.12, FastAPI, LangGraph, Qdrant, NATS, PostgreSQL
- Deploy: Docker Swarm no VPS 76.13.232.175

## Deploy
```bash
cd /opt/veltrus-intelligence
set -a && source .env && set +a   # obrigatório antes do stack deploy
docker build -t veltrus-intelligence-graphdb:latest ./infra/postgres-age/  # ~5-8min na 1ª vez
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

## NATS JetStream
- Streams devem ser criados via `ensure_attribution_stream()` com `StreamConfig` no lifespan da aplicação, **antes** de qualquer `publish()` ou `subscribe()`
- NUNCA assumir que o stream existe — `js.publish()` lança `NoStreamResponseError` se o stream não foi criado

## Apache AGE (Revenue + Creative Graph)
- AGE **NÃO** vai no postgres compartilhado (n8n, Evolution API) — container separado `intelligence_graphdb` na stack intelligence
- `asyncpg` **NÃO** funciona com `agtype` (tipo customizado do AGE) — queries AGE usam `psycopg2` síncrono via `asyncio.to_thread()`
- Padrões Cypher obrigatórios: `MERGE + SET` (sem `ON CREATE SET`), props de edge via `SET` após `MERGE`, `ORDER BY sum(...)` (sem alias)
- Build graphdb: `flex` + `bison` obrigatórios; confirmar com `docker build --no-cache` se dúvida de cache
- `intelligence_graphdb` é acesso interno apenas — sem labels Traefik

## Embeddings (Creative Graph)
- `fastembed` ONNX CPU — modelo `all-MiniLM-L6-v2`, 384-dim
- Qdrant collection: `creative_embeddings`
- API memory limit: **768M** (fastembed ~150MB extra sobre base)
- `test_embed_produces_384_dims` roda fastembed **real** — deve passar antes de merge

## Camadas (briefings)
- Briefing #1: Identity Graph (Postgres + Union-Find) — concluído
- Briefing #2: Attribution Engine (4 modelos + Shapley NATS) — concluído
- Briefing #3: Revenue Graph (Apache AGE + graph sync) — concluído
- Briefing #4: Creative Graph + Qdrant embeddings (CPU) — em andamento
- Briefing #5: Agent Layer (LangGraph + Claude API) + GPU Vast.ai
- Briefing #6: AI Modalities (FLUX, Wan2.1, Kokoro, Hunyuan3D via Vast.ai)

## Migrations (produção)
- Rodar **dentro do container** após deploy: `alembic upgrade head`
- NUNCA `docker service update --args` para mudar CMD — usar `docker stack deploy`
- DATABASE_URL no `.env` usa `postgresql://`; engine async usa `postgresql+asyncpg://` via `async_url()`

## Merge order (PRs stacked)
- PR #2 (Identity Graph) → merge em `main` primeiro
- PR #3 (Attribution Engine) → rebase em `main`, depois merge
- NUNCA mergear em ordem inversa quando PR está stacked
