"""Centralized configuration via Pydantic Settings.

Every default here MUST match .env.example AND docker-compose.yml environment blocks.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- LLM (Ollama) ---
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "qwen3.5:2b"
    OLLAMA_TIMEOUT: int = 180
    OLLAMA_THINK: bool = False

    # --- Vector DB (Qdrant) ---
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333

    # --- Redis ---
    REDIS_URL: str = "redis://redis:6379/0"

    # --- Embedding ---
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # --- Feature flags ---
    RASA_ENABLED: bool = False
    RERANKER_ENABLED: bool = False
    RASA_URL: str = "http://rasa:5005"
    RASA_TIMEOUT: int = 5
    RASA_CONFIDENCE_THRESHOLD: float = 0.6
    RASA_SHADOW_MODE: bool = False
    RASA_CIRCUIT_OPEN_SECONDS: int = 60

    # --- App Store API ---
    MOCK_API_URL: str = "http://mock-api:9000"
    HEDGE_API_URL: str = ""

    # --- Ingestion ---
    INGEST_INTERVAL_SECONDS: int = 7200

    # --- Service ports ---
    GATEWAY_PORT: int = 8000
    CHAT_INTENT_PORT: int = 8001
    EXPERT_RECOMMEND_PORT: int = 8002
    DISCOVERY_RANKING_PORT: int = 8003
    METADATA_INGEST_PORT: int = 8004
    MOCK_API_PORT: int = 9000

    # --- General ---
    LOG_LEVEL: str = "INFO"
    APP_VERSION: str = "0.1.0"

    # --- Security ---
    GATEWAY_API_KEY: str = ""
    CORS_ALLOWED_ORIGINS: str = "*"
    TRUST_PROXY_HEADERS: bool = False
    ENABLE_HSTS: bool = False
    ENABLE_RBAC: bool = False

    # --- OAuth / OIDC ---
    OAUTH_ENABLED: bool = False
    OAUTH_ISSUER: str = ""
    OAUTH_AUDIENCE: str = "hedge-expert-api"
    OAUTH_CLIENT_ID: str = "hedge-expert-api"
    OAUTH_JWKS_URL: str = ""
    OAUTH_SHARED_SECRET: str = ""
    OAUTH_JWT_ALGORITHMS: str = "RS256"
    RBAC_ADMIN_ROLES: str = "admin,administrator"
    RBAC_ANALYST_ROLES: str = "analyst,admin"

    # --- TLS edge / local auth tooling ---
    TLS_SERVER_NAME: str = "localhost"
    TLS_SELF_SIGNED_DAYS: int = 30
    TLS_CERT_PATH: str = ""
    TLS_KEY_PATH: str = ""
    KEYCLOAK_PORT: int = 8081

    # --- Service URLs (for inter-service calls) ---
    CHAT_INTENT_URL: str = "http://chat-intent:8001"
    EXPERT_RECOMMEND_URL: str = "http://expert-recommend:8002"
    DISCOVERY_RANKING_URL: str = "http://discovery-ranking:8003"
    METADATA_INGEST_URL: str = "http://metadata-ingest:8004"

    @property
    def app_store_url(self) -> str:
        """Return the real HEDGE API URL if set, otherwise fall back to mock."""
        return self.HEDGE_API_URL or self.MOCK_API_URL

    model_config = {"env_prefix": "", "case_sensitive": True}


settings = Settings()
