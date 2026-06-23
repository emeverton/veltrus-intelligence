# veltrus-intelligence

Backend de ML/Identity/Attribution/Agents do Veltrus SaaS.

## Stack

- Python 3.12 + FastAPI + LangGraph
- Qdrant (vector store) + NATS JetStream (message queue)
- PostgreSQL (stack `postgres` na rede Swarm `emeverton`)
- Deploy: Docker Swarm + Traefik no VPS `76.13.232.175`

## API

- Production: https://intelligence.ehos.com.br
- Health: `GET /health`
- Placeholders: `/api/v1/identity`, `/api/v1/attribution`, `/api/v1/agents`, `/api/v1/generate`

## Deploy

```bash
cp .env.example .env   # preencher ANTHROPIC_API_KEY e DATABASE_URL
docker build -t veltrus-intelligence:latest .
docker stack deploy -c docker-compose.yml intelligence
```

## Testes locais

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=test DATABASE_URL=postgresql://test:test@localhost/test
pytest tests/ -v
```

Ver `AGENTS.md` para regras de deploy e roadmap de briefings.
