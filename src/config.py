from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    debug: bool = False
    anthropic_api_key: str
    database_url: str
    qdrant_host: str = "intelligence_qdrant"
    qdrant_port: int = 6333
    nats_url: str = "nats://intelligence_nats:4222"
    attribution_worker_enabled: bool = True
    graph_db_url: str = "postgresql://graphuser:changeme@intelligence_graphdb:5432/revenue_graph"
    vastai_api_key: str = ""
    hf_token: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
