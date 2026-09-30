from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import base64
import hashlib
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_JWT_SECRET = "change-me-in-production"
# Known placeholder secrets shipped in defaults and .env.template. None of these
# may be used once the service runs outside a development environment.
INSECURE_JWT_SECRETS = frozenset(
    {DEFAULT_JWT_SECRET, "", "change-me", "replace-with-a-random-secret"}
)


class ProductionConfigError(RuntimeError):
    """Raised when a non-development runtime still carries insecure defaults."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
    )

    app_name: str = "knowledge"
    app_env: str = "development"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    database_url: str = "postgresql://knowledge:knowledge@127.0.0.1:5432/knowledge?gssencmode=disable"

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_minutes: int = 60 * 24 * 7
    challenge_ttl_seconds: int = 300
    siwe_domain: str = ""
    siwe_uri: str = ""
    siwe_chain_id: int = 1
    identity_node_url: str = ""
    identity_app_id: str = ""
    identity_redirect_uri: str = ""
    passport_session_ttl_seconds: int = 300

    # Deprecated compatibility switch. Production uses the standard object
    # storage gateway below; keep this only for legacy tests/transitional setups.
    warehouse_gateway_mode: str = ""
    warehouse_base_url: str = "https://webdav.yeying.pub"
    warehouse_webdav_prefix: str = "/dav"
    object_storage_endpoint: str = "http://127.0.0.1:6066"
    object_storage_region: str = "us-east-1"
    # Backward-compatible aliases for existing deployments.
    s3_endpoint_url: str = ""
    s3_region: str = ""
    warehouse_app_id: str = "knowledge.yeying.pub"
    warehouse_apps_prefix: str = "/apps"
    warehouse_mock_root: str = str(Path(__file__).resolve().parents[2] / ".mock_warehouse")
    token_encryption_secret: str = ""

    vector_store_mode: str = "db"
    weaviate_url: str = "http://127.0.0.1:8080"
    weaviate_index_name: str = "KnowledgeChunk"
    # Unit-level vectors (evidence/formal) live in their own class so they never
    # collide with chunk vectors; Postgres unit_embeddings stays the source of truth.
    weaviate_unit_index_name: str = "KnowledgeUnit"
    weaviate_scheme: str = "http"
    weaviate_host: str = ""
    weaviate_port: int = 8080
    weaviate_grpc_port: int = 50051
    weaviate_api_key: str = ""

    model_provider_mode: str = "mock"
    model_gateway_base_url: str = ""
    model_gateway_api_key: str = ""
    analysis_planner_model: str = "gpt-4o-mini"
    analysis_planner_timeout_seconds: int = 30
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 32
    # Cost/stability policy for real embedding calls: bounded latency and a small
    # retry budget (exponential backoff inside the client). Query-time failures
    # still degrade to lexical retrieval; these keep that path from hanging.
    embedding_timeout_seconds: int = 30
    embedding_max_retries: int = 2

    document_parser_mode: str = "local"
    ragflow_parser_chunk_token_num: int = 512
    ragflow_parser_delimiter: str = "\n!?;。；！？"
    document_chunker_mode: str = "local"
    ragflow_chunker_delimiter: str = "\n。；！？"
    source_connector_mode: str = "warehouse"
    local_file_connector_root: str = str(Path(__file__).resolve().parents[2] / ".local_source_files")
    github_connector_access_token: str = ""
    github_connector_api_base_url: str = "https://api.github.com"

    chunk_size: int = 800
    chunk_overlap: int = 120
    retrieval_top_k: int = 6
    # Hybrid retrieval: fuse lexical (token-overlap) and semantic (embedding cosine)
    # signals via Reciprocal Rank Fusion. Effective only with a real embedding
    # provider; the mock provider is skipped so lexical ranking stays deterministic.
    retrieval_hybrid_enabled: bool = True
    retrieval_rrf_k: int = 60
    # Number of unit-level vector candidates recalled (before fusion) to widen the
    # lexical recall set with semantically-relevant units it missed.
    retrieval_vector_top_k: int = 20
    # Rerank: after RRF, re-score the top candidates with a cross-encoder rerank
    # service for precision. Default on; effective only with a real provider, and
    # any failure/timeout degrades to the RRF order. rerank_top_m bounds how many
    # fused candidates are sent to the reranker.
    retrieval_rerank_enabled: bool = True
    rerank_model: str = "rerank-english-v3.0"
    rerank_top_m: int = 20
    rerank_timeout_seconds: int = 10
    # Retries only transport errors and 5xx; 4xx is a configuration problem.
    rerank_max_retries: int = 1
    memory_top_k: int = 4
    auto_memory_short_term_ttl_hours: int = 72
    auto_memory_max_long_terms: int = 3
    auto_memory_max_short_terms: int = 4
    auto_memory_recent_turn_max_chars: int = 600
    worker_poll_interval_seconds: int = 5
    worker_run_lease_ttl_seconds: int = 120
    worker_task_concurrency: int = 2
    worker_max_active_tasks_per_user: int = 1
    worker_task_heartbeat_interval_seconds: int = 15
    worker_name: str = "knowledge-worker-1"

    @field_validator("database_url")
    @classmethod
    def validate_postgresql_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql://"):
            raise ValueError("DATABASE_URL must use the postgresql:// scheme")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    token_secret_explicit = bool(settings.token_encryption_secret)
    if settings.s3_endpoint_url:
        settings.object_storage_endpoint = settings.s3_endpoint_url
    if settings.s3_region:
        settings.object_storage_region = settings.s3_region
    if not settings.token_encryption_secret:
        digest = hashlib.sha256(settings.jwt_secret.encode("utf-8")).digest()
        settings.token_encryption_secret = base64.urlsafe_b64encode(digest).decode("utf-8")
    if (not settings.weaviate_url or settings.weaviate_url == "http://127.0.0.1:8080") and settings.weaviate_host:
        settings.weaviate_url = f"{settings.weaviate_scheme}://{settings.weaviate_host}:{settings.weaviate_port}"
    parsed = urlparse(settings.weaviate_url)
    if parsed.scheme and parsed.hostname:
        settings.weaviate_scheme = parsed.scheme
        settings.weaviate_host = parsed.hostname
        if parsed.port:
            settings.weaviate_port = parsed.port
    validate_runtime_settings(settings, token_secret_explicit=token_secret_explicit)
    return settings


def validate_runtime_settings(settings: Settings, *, token_secret_explicit: bool) -> None:
    """Fail fast when a non-development runtime still uses insecure defaults.

    Development is intentionally exempt so local runs and tests keep working with
    mock providers and placeholder secrets. Every other environment must supply
    real, rotatable secrets and real providers before the process starts.
    """
    if settings.app_env == "development":
        return

    problems: list[str] = []
    if settings.jwt_secret in INSECURE_JWT_SECRETS:
        problems.append("JWT_SECRET must be a long random value, not a default/placeholder")
    if settings.debug:
        problems.append("DEBUG must be false")
    if settings.model_provider_mode == "mock":
        problems.append("MODEL_PROVIDER_MODE must not be 'mock'; connect a real model gateway")
    if settings.warehouse_gateway_mode == "mock":
        problems.append("WAREHOUSE_GATEWAY_MODE must not be 'mock'; use real object storage")
    if not token_secret_explicit:
        problems.append(
            "TOKEN_ENCRYPTION_SECRET must be set explicitly; "
            "deriving it from JWT_SECRET is not allowed outside development"
        )

    if problems:
        joined = "\n  - ".join(problems)
        raise ProductionConfigError(
            f"Insecure configuration for app_env='{settings.app_env}':\n  - {joined}"
        )
