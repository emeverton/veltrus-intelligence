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

## Shopify Webhooks (Briefing #8)
- Endpoint: `POST /webhooks/shopify/orders/paid` — HMAC sobre **bytes crus** (`await request.body()` antes de `json.loads`)
- Idempotência: `ON CONFLICT (shopify_order_id) DO NOTHING` — Shopify retenta 3x sem 200
- **`SHOPIFY_WEBHOOK_SECRET` vazio aceita requests sem verificação (dev/smoke test)**
- **Em produção o secret é OBRIGATÓRIO** — sem ele, qualquer POST no endpoint é aceito
- Processamento async via `asyncio.create_task` — responder 200 em < 1s
- Setup loja: `scripts/setup-shopify-webhook.sh` (Shopify CLI → ORDERS_PAID webhook)

## Observability (Briefing #9)
- Sentry: `sentry_sdk.init()` só se `SENTRY_DSN` preenchido — `send_default_pii=False`
- Health: `GET /health/detailed` — Postgres, Qdrant, NATS, GraphDB, schema (12 tabelas)
- Alerta n8n: ping `/health/detailed` a cada 5 min (workflow manual no VPS)

## Meta CAPI (Briefing #9)
- `send_purchase_event()` — SHA256 de email/phone, fire-and-forget após conversão Shopify
- `event_id`: `shopify_{order_id}` para deduplicação browser ↔ server
- `META_TEST_EVENT_CODE` obrigatório em testes — sem ele Meta computa conversão real
- **Nunca logar PII em texto claro** — mascarar (`email[:3] + "***"`)

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
- API memory limit: **768M** → **1G** (Briefing #5: Prophet + pandas)
- `test_embed_produces_384_dims` roda fastembed **real** — deve passar antes de merge

## Camadas (briefings)
- Briefing #1: Identity Graph (Postgres + Union-Find) — concluído
- Briefing #2: Attribution Engine (4 modelos + Shapley NATS) — concluído
- Briefing #3: Revenue Graph (Apache AGE + graph sync) — concluído
- Briefing #4: Creative Graph + Qdrant embeddings (CPU) — em andamento
- Briefing #5: Agent Layer (LangGraph + Claude API) + GPU Vast.ai
- Briefing #6: AI Modalities (FLUX, Wan2.1, Kokoro, Hunyuan3D via Vast.ai)
- Briefing #7: Lazy loading + Vast.ai + Qwen dual-mode LLM
- Briefing #8: Shopify webhook ingestion (orders/paid → identity → attribution → graph)

## Migrations (produção)
- Rodar **dentro do container** após deploy: `alembic upgrade head`
- NUNCA `docker service update --args` para mudar CMD — usar `docker stack deploy`
- DATABASE_URL no `.env` usa `postgresql://`; engine async usa `postgresql+asyncpg://` via `async_url()`

## Merge order (PRs stacked)
- PR #2 (Identity Graph) → merge em `main` primeiro
- PR #3 (Attribution Engine) → rebase em `main`, depois merge
- NUNCA mergear em ordem inversa quando PR está stacked
