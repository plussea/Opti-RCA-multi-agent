"""系统配置"""
import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""
    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ===================
    # 数据库配置
    # ===================
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/omniops",
        validation_alias="DATABASE_URL",
    )

    # ===================
    # Redis 配置
    # ===================
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias="REDIS_URL",
    )

    # ===================
    # LLM API 配置
    # ===================
    anthropic_api_key: str = Field(
        default="",
        validation_alias="ANTHROPIC_API_KEY",
    )
    anthropic_model: str = Field(
        default="claude-3-5-sonnet-20241022",
    )
    anthropic_max_tokens: int = Field(default=2048)

    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o")

    # ===================
    # 向量数据库配置
    # ===================
    chroma_persistent_path: str = Field(
        default="./data/chroma",
    )
    chroma_collection: str = Field(default="omniops_knowledge")

    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_api_key: str = Field(default="")
    qdrant_collection: str = Field(default="omniops_knowledge")

    # ===================
    # Neo4j 配置
    # ===================
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="password")

    # ===================
    # 应用配置
    # ===================
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_debug: bool = Field(default=False)

    # 文件上传
    upload_dir: str = Field(default="./uploads")
    max_upload_size: int = Field(default=10 * 1024 * 1024)  # 10MB

    # Session TTL
    working_memory_ttl: int = Field(default=14400)  # 4 hours
    short_term_memory_ttl: int = Field(default=604800)  # 7 days

    # Agent 路由阈值
    single_agent_threshold: int = Field(default=5)
    batch_agent_threshold: int = Field(default=5)
    confidence_conflict_threshold: float = Field(default=0.2)

    # OCR 置信度阈值
    ocr_confidence_threshold: float = Field(default=0.85)

    # CSV 编码回退
    csv_encoding_fallback: List[str] = Field(
        default=["utf-8", "gbk", "gb2312"]
    )

    # 日志级别
    log_level: str = Field(default="INFO")

    @property
    def project_root(self) -> Path:
        return Path(__file__).parent.parent.parent.parent

    def get_chroma_path(self) -> Path:
        """获取 Chroma 数据目录"""
        path = Path(self.chroma_persistent_path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_upload_path(self) -> Path:
        """获取上传文件目录"""
        path = Path(self.upload_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()