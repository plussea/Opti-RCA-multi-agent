"""系统配置"""
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""
    model_config = SettingsConfigDict(
        env_prefix="OMNIOPS_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_debug: bool = False

    # LLM
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-20241022"
    anthropic_max_tokens: int = 1024

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "omniops_knowledge"
    qdrant_api_key: str = ""

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # PostgreSQL
    postgres_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/omniops"

    # Memory TTL (seconds)
    working_memory_ttl: int = 14400  # 4 hours
    short_term_memory_ttl: int = 604800  # 7 days

    # Routing thresholds
    single_agent_threshold: int = 5  # <5 alarms → single agent
    batch_agent_threshold: int = 5  # ≥5 alarms → multi agent
    confidence_conflict_threshold: float = 0.2

    # OCR confidence
    ocr_confidence_threshold: float = 0.85

    # CSV
    csv_encoding_fallback: List[str] = ["utf-8", "gbk", "gb2312"]

    @property
    def project_root(self) -> Path:
        return Path(__file__).parent.parent.parent.parent


@lru_cache
def get_settings() -> Settings:
    return Settings()
