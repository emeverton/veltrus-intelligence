# MASTER PROMPT — VELTRUS INTELLIGENCE + VERTEX

Colar no Cursor antes de qualquer tarefa. Contexto completo do projeto.

**Atualizado:** 2026-06-26 · **Complementa:** [`../AGENTS.md`](../AGENTS.md)

---

## IDENTIDADE DO PROJETO

Everton S. Ferreira — Founder/CTO da Veltrus (Revenue Infrastructure Engineering)

Metodologia: Claude gera briefings → Cursor implementa autonomamente → Everton valida

Dois repositórios em produção:

- veltrus-intelligence → https://github.com/emeverton/veltrus-intelligence
- vertex → https://github.com/emeverton/vertex

---

## INFRAESTRUTURA

### VPS (Docker Swarm)

IP: `76.13.232.175` ← ATENÇÃO: é `.232.` não `.132.`

SSH: `root@76.13.232.175`

Stack: intelligence (4 serviços: api + qdrant + nats + graphdb)

Domínio API: https://intelligence.ehos.com.br

certresolver: **SEMPRE** `letsencryptresolver` — **NUNCA** `letsencrypt`

### VERTEX (Vercel)

URL prod: https://vertex-alpha-sooty.vercel.app

Token Vercel: **SEMPRE** `vcp_` (Full Account) — **NUNCA** `vck_` (Limited, deploys ficam UNKNOWN)

Deploy:

```bash
cd vertex && export VERCEL_TOKEN='vcp_...' && vercel deploy --prod --yes
```

### Supabase (Cloud — não self-hosted)

Projeto: vertex | ref: `hpnopldrskzlhrfgihzf` | Região: São Paulo

URL: https://hpnopldrskzlhrfgihzf.supabase.co
**Site URL Supabase:** sempre `https://vertex-alpha-sooty.vercel.app` — NUNCA `vertex-emevertons-projects.vercel.app` (preview quebra magic link).
**Redirect URLs (só 3):** `/onboarding`, `/dashboard`, `/login` no domínio de produção.


Tabelas: `user_stores`, `store_invites`, `subscriptions` (+ `auth.users` gerenciado pelo Supabase)

### Docker (VPS)

**REGRA CRÍTICA — Swarm não lê `.env` automaticamente:**

```bash
# SEMPRE antes de docker stack deploy:
cd /opt/veltrus-intelligence
set -a && source .env && set +a
docker stack deploy -c docker-compose.yml intelligence
```

- **NUNCA:** `docker stack deploy` sem `source .env` → `DATABASE_URL` vazio → API derruba
- **NUNCA:** `docker compose up` em produção
- **NUNCA:** `docker service update --args` (não existe no Swarm)

---

## STACK TÉCNICO

### veltrus-intelligence (Python/FastAPI)

- Python 3.12 + FastAPI + SQLAlchemy async + Alembic
- PostgreSQL 14 + Apache AGE (container separado: `intelligence_graphdb`)
- Qdrant (vector store) + NATS JetStream + Redis
- fastembed ONNX 384-dim (all-MiniLM-L6-v2)
- LangGraph + dual-mode LLM: Qwen 2.5 7B via vLLM → Claude API (fallback)
- GPU on-demand: Vast.ai RTX 4090 (~$60/mês) — FLUX.1-schnell + Wan 2.1 + Kokoro TTS
- Sentry SDK (`send_default_pii=False`)
- slowapi rate limiting (120/min nos webhooks)
- **pydantic: manter >= 2.10.6** — `svix` (webhook Resend/KAIROS) exige pydantic >= 2.10; downgrade quebra import e derruba a API com 502

### vertex (Next.js 15)

- Next.js 15 App Router + TypeScript + Tailwind v4 + Supabase SSR
- `@supabase/ssr` (**NUNCA** `@supabase/auth-helpers-nextjs` — deprecado)
- Tailwind v4: `@theme inline` em `globals.css` (**NUNCA** `tailwind.config.ts`)
- Stripe billing (checkout + webhook + Customer Portal)
- Resend emails (welcome Pro + convites)
- Proxy seguro: `/api/intelligence/*` → intelligence.ehos.com.br (admin key server-side)
- shadcn/ui + Recharts

---

## BANCO DE DADOS (28 tabelas em produção)

### veltrus-intelligence (Postgres)

`identity_profiles`, `identity_signals`, `identity_events`, `identity_profile_merges`

`attribution_touchpoints`, `attribution_conversions`, `attribution_results`

`creative_assets`, `agent_jobs`, `generation_jobs`, `graph_sync_log`

`shopify_orders`, `shopify_stores`

`tray_orders`, `tray_stores`

`nuvemshop_orders`, `nuvemshop_stores`

`vtex_orders`, `vtex_stores`

`woocommerce_orders`, `woocommerce_stores`

`loja_integrada_orders`, `loja_integrada_stores`

`moovin_orders`, `moovin_stores`

`generic_orders`, `generic_stores`

`alembic_version`

### Supabase (vertex)

- `user_stores` (platform, platform_store_id, shop_domain, is_primary + RLS)
- `store_invites` (inviter_id, shop_domain, invitee_email + RLS)
- `subscriptions` (user_id, stripe_*, plan, status + RLS)

---

## PLATAFORMAS DE E-COMMERCE SUPORTADAS

### Webhook nativo (POST direto ao Intelligence)

| Plataforma | Endpoint | Auth | Status pago |
|------------|----------|------|-------------|
| Shopify | `/webhooks/shopify/orders/paid` | HMAC hex SHA256 | `financial_status=paid` |
| Tray | `/webhooks/tray/orders` | `Authorization: Token token=` | `status_id`: 7 ou 13 |
| Nuvemshop | `/webhooks/nuvemshop/orders` | `Authorization: Token token=` | `payment_status=paid` |
| VTEX | `/webhooks/vtex/orders` | X-VTEX-API-AppKey+AppToken | `payment-approved` |
| WooCommerce | `/webhooks/woocommerce/orders` | HMAC base64 SHA256 | processing/completed |
| Loja Integrada | `/webhooks/loja-integrada/orders` | `Authorization: chave <key>` | `situacao.id`: 2-5 |
| Moovin | `/webhooks/moovin/orders` | X-Store-Key + X-Store-Id | `status=aprovado` |

**WooCommerce HMAC:** base64(HMAC-SHA256) — **DIFERENTE** do Shopify (hex). Nunca reutilizar `verify_shopify_hmac`.

### Via n8n polling (endpoint genérico)

| Plataforma | Endpoint | Auth |
|------------|----------|------|
| Wix | `/webhooks/generic/order` | X-Store-Key |
| Webflow | `/webhooks/generic/order` | X-Store-Key |
| GoDaddy | `/webhooks/generic/order` | X-Store-Key |
| Qualquer API | `/webhooks/generic/order` | X-Store-Key |

Payload normalizado:

```json
{
  "store_id": "...",
  "order_id": "...",
  "platform": "...",
  "email": "...",
  "phone": "...",
  "revenue": 0,
  "currency": "BRL",
  "utm_source": "...",
  "utm_medium": "...",
  "utm_campaign": "...",
  "gclid": "...",
  "fbclid": "..."
}
```

---

## REGRAS CRÍTICAS (NUNCA QUEBRAR)

### Traefik/SSL

- `certresolver=letsencryptresolver` (com `resolver` no final) — NUNCA `letsencrypt`

### Docker

- `docker stack deploy -c docker-compose.yml intelligence`
- NUNCA `docker compose up` em produção
- NUNCA `docker service update --args`

### Vercel

- Token: `vcp_` (Full Account) — NUNCA `vck_` (Limited)
- Webhook Stripe: `await req.text()` + `export const runtime = 'nodejs'` (nunca `req.json()`)

### Supabase

- `@supabase/ssr` (nunca `@supabase/auth-helpers-nextjs`)
- Cookies HttpOnly — nunca localStorage para auth

### Tailwind v4

- `@theme inline` em `globals.css`
- NUNCA `tailwind.config.ts`

### Apache AGE (Cypher)

- MERGE + SET (nunca ON CREATE SET)
- Properties de edge: SET após MERGE
- ORDER BY: expressão direta (nunca alias)
- asyncpg NÃO deserializa agtype — usar psycopg2 via `asyncio.to_thread()` para AGE

### NATS JetStream

- Criar stream com StreamConfig no lifespan ANTES de publish/subscribe

### JSONB em text() queries

- `json.dumps()` obrigatório (asyncpg não aceita dict bruto)

### Modelos de imagem

- FLUX.1-schnell (Apache 2.0) — comercialmente livre
- FLUX.1-dev — BLOQUEADO (non-commercial)

### Shopify

- Webhook via CLI/Partners → secret = Client secret (`shpss_...`)
- Webhook via Admin UI Notifications → Signing secret (diferente, não intercambiável)

### Tray Commerce

- Auth: `Authorization: Token token=<api_key>` (não HMAC)
- Processar apenas `status_id` 7 ou 13

---

## CREDENCIAIS E ENDPOINTS

### Intelligence API

- URL: https://intelligence.ehos.com.br
- Admin Key: `ADMIN_API_KEY` (no `.env` do VPS)
- Health: `GET /health/detailed`
- Swagger: `/docs`

### VERTEX (Vercel env vars)

```text
NEXT_PUBLIC_SUPABASE_URL=https://hpnopldrskzlhrfgihzf.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=[anon key]
SUPABASE_SERVICE_ROLE_KEY=[service role key]
INTELLIGENCE_API_URL=https://intelligence.ehos.com.br
INTELLIGENCE_ADMIN_KEY=[ADMIN_API_KEY do VPS]
NEXT_PUBLIC_APP_URL=https://vertex-alpha-sooty.vercel.app
RESEND_API_KEY=[re_xxxx]
RESEND_FROM_EMAIL=noreply@ehos.com.br
STRIPE_SECRET_KEY=[sk_live_xxx]
STRIPE_WEBHOOK_SECRET=[whsec_xxx]
STRIPE_PRO_PRICE_ID=[price_live_xxx]
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=[pk_live_xxx]
```

### VPS .env (pendentes de configurar)

- `SENTRY_DSN` — criar em sentry.io
- `META_PIXEL_ID` — por loja via admin API
- `META_ACCESS_TOKEN` — por loja
- `GOOGLE_ADS_DEVELOPER_TOKEN` — aprovação pendente Google
- `VASTAI_API_KEY` — Vast.ai

---

## PLANOS VERTEX (`src/lib/features.ts`)

| Plano | Lojas | Ordens/mês | Agente IA |
|-------|-------|------------|-----------|
| free | 1 | 100 | ✗ |
| pro | 10 | ∞ | ✓ |
| enterprise | ∞ | ∞ | ✓ |

---

## ADMIN API (veltrus-intelligence)

Cadastrar lojas por plataforma (header: `X-Admin-Key: ${ADMIN_API_KEY}`):

| Plataforma | Endpoint |
|------------|----------|
| Shopify | `POST /api/v1/admin/stores` |
| Tray | `POST /api/v1/admin/tray-stores` |
| Nuvemshop | `POST /api/v1/admin/nuvemshop-stores` |
| VTEX | `POST /api/v1/admin/vtex-stores` |
| WooCommerce | `POST /api/v1/admin/woocommerce-stores` |
| Loja Integrada | `POST /api/v1/admin/loja-integrada-stores` |
| Moovin | `POST /api/v1/admin/moovin-stores` |
| Genérico (n8n) | `POST /api/v1/admin/generic-stores` |

---

## ONBOARDING VERTEX (8 plataformas + 1 genérica)

**Grupo "Webhook nativo":** Shopify, WooCommerce, Tray, Nuvemshop, VTEX, Loja Integrada, Moovin

**Grupo "Via n8n / Make":** Wix, Outras

| Plataforma | Identifier |
|------------|------------|
| shopify | `shop_domain` (ex: loja.myshopify.com) |
| woocommerce | `platform_store_id` = URL da loja |
| tray | `platform_store_id` = seller_id numérico |
| nuvemshop | `platform_store_id` = store_id numérico |
| vtex | `platform_store_id` = account_name |
| loja_integrada | `platform_store_id` = store_key |
| moovin | `platform_store_id` = UUID da loja |
| wix | `platform_store_id` = store_id em generic-stores |

---

## ESTADO ATUAL DO CHECKLIST DE LAUNCH

- ✅ Supabase magic links configurados
- ✅ Resend domínio ehos.com.br verificado
- ⏳ Supabase SMTP: trocar sender para noreply@ehos.com.br
- ⏳ Vercel: adicionar RESEND_API_KEY + RESEND_FROM_EMAIL → redeploy
- ⏳ Stripe Live: produto + webhook + 4 env vars no Vercel
- ⏳ Sentry DSN no VPS .env
- ⏳ n8n health alert workflow ativo

---

## ARQUITETURA DO PIPELINE (por ordem de execução)

```text
Webhook → verify_auth → json.loads → check_usage_limit (100/mês Free)
→ extract_signals (email, phone, gclid, fbclid)
→ resolve_identity (Union-Find, determinístico)
→ ingest_touchpoint (canal, UTMs)
→ create_conversion (revenue, currency)
→ save_order (idempotente via UNIQUE constraint)
→ commit()
→ [async] compute_attribution (4 modelos síncronos + Shapley via NATS)
→ [async] sync_to_revenue_graph (Apache AGE)
→ [async] Meta CAPI fire-and-forget
→ [async] Google Ads offline conversion (se GCLID presente)
```

---

## PRÓXIMAS TAREFAS PENDENTES

### Launch checklist (2026-06-25)

| # | Item | Status |
|---|------|--------|
| 1 | Supabase Magic Links (`noreply@ehos.com.br`) | ✓ |
| 2 | Resend Vercel | ✓ |
| 3 | Stripe TEST MODE (live pendente para cobrança real) | ~ |
| 4 | Sentry DSN no VPS | ✓ |
| 5 | n8n Health Monitor ativo | ✓ |

**Go-live real:** trocar 4 vars Stripe test → live no Vercel + smoke test 5/5.

### Smoke test end-to-end

1. Aba anônima → https://vertex-alpha-sooty.vercel.app → email → magic link de `noreply@ehos.com.br`
2. Clicar link → `/onboarding` autenticado
3. Onboarding → Shopify → `smoke-test.myshopify.com` → Conectar
4. `/dashboard/settings` → Upgrade Pro → `4242 4242 4242 4242` · 12/26 · 123
5. Verificar: welcome email · Supabase `subscriptions.plan=pro` · banner Pro no dashboard

### Próximos briefings

- Briefing #24-B: relatórios automáticos semanais por loja (n8n + Resend)
- Briefing #25: KAIROS v2 — agente SDR autônomo sobre identity graph

---

## COMANDOS ÚTEIS (VPS)

```bash
# SSH
ssh root@76.13.232.175

# Deploy sem rebuild (recarregar env vars)
cd /opt/veltrus-intelligence
set -a && source .env && set +a
docker stack deploy -c docker-compose.yml intelligence

# Deploy com rebuild
cd /opt/veltrus-intelligence
set -a && source .env && set +a
docker build -t veltrus-intelligence:latest .
docker stack deploy -c docker-compose.yml intelligence

# Migrations
docker exec -it $(docker ps -q -f name=intelligence_intelligence_api) alembic upgrade head

# Logs
docker service logs intelligence_intelligence_api --tail 20 -f

# Health check
curl -s https://intelligence.ehos.com.br/health/detailed | python3 -m json.tool
```

---

## FIGMA BRAND

Arquivo: `pyTEWuc3rNTX8BlMpSZaJQ`

Paleta: Void `#020205` · Copper `#B87333` · Petróleo `#1A6080` · Gelo `#E4EDFF`

Font: Chakra Petch (Google Fonts)

V-mark: braço esquerdo diagonal visível, braço direito inferido por 3 barras de dados

---

## CLIENTES ATIVOS / REFERÊNCIAS

North American Advertising (West Palm Beach, FL) · V4 Company (Caxias do Sul) · Agência AND (Rio de Janeiro)

Malhas e Tramas (Porto Alegre) — Moovin store_id: `a24f51bc-5c08-4b7e-ba3c-51fdd4d5d24b`

Empório Vitório, Bautech, Valutin, Bicchieri, Volnorte Auto Peças

Palmeiras/Allianz Parque, Atlético-MG, Zigtickets

---

## n8n WORKFLOWS DISPONÍVEIS

URL: http://76.13.232.175:5678

Templates em `docs/n8n/`:

- `intelligence-health-monitor.json` — health alert a cada 5min
- `webflow-orders.json` — polling Webflow → `/webhooks/generic/order`
- `generic-order-template.json` — template para qualquer plataforma via poll

---

## MOOVIN (Malhas e Tramas) — NOTA IMPORTANTE

Parser em `src/webhooks/moovin_parser.py` é baseado em inferência estrutural.

Antes do go-live, validar com payload real:

1. Configurar webhook.site no painel Moovin da Malhas e Tramas
2. Fazer ordem de teste
3. Comparar campos reais com o parser (status, customer, total, UTMs)
4. Ajustar se necessário
5. Só então apontar webhook para `https://intelligence.ehos.com.br/webhooks/moovin/orders`
