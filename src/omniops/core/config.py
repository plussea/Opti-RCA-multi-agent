"""系统配置"""
from functools import lru_cache
from pathlib import Path
from typing import List

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
    anthropic_max_tokens: int = Field(default=4096)

    # ===================
    # Generic LLM settings (used when provider != anthropic)
    # ===================
    llm_provider: str = Field(default="openrouter", validation_alias="LLM_PROVIDER")
    llm_model: str = Field(default="claude-3-5-sonnet-20241022", validation_alias="LLM_MODEL")

    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", validation_alias="OPENAI_MODEL")

    openrouter_api_key: str = Field(default="", validation_alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(default="anthropic/claude-3-haiku", validation_alias="OPENROUTER_MODEL")

    minimax_api_key: str = Field(default="", validation_alias="MINIMAX_API_KEY")
    minimax_model: str = Field(default="MiniMax-Text-01", validation_alias="MINIMAX_MODEL")
    minimax_group_id: str = Field(default="", validation_alias="MINIMAX_GROUP_ID")

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
    # OCR 配置
    # ===================
    ocr_api_key: str = Field(default="", validation_alias="OCR_API_KEY")
    ocr_model: str = Field(default="baidu/qianfan-ocr-fast:free", validation_alias="OCR_MODEL")
    ocr_confidence_threshold: float = Field(default=0.85)

    # ===================
    # Embedding 配置
    # ===================
    embedding_api_key: str = Field(default="", validation_alias="EMBEDDING_API_KEY")
    embedding_model: str = Field(
        default="nvidia/llama-nemotron-embed-vl-1b-v2:free",
        validation_alias="EMBEDDING_MODEL",
    )
    embedding_dim: int = Field(default=2048)  # nvidia/llama-nemotron-embed-vl-1b-v2:free

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

    # CSV 编码回退
    csv_encoding_fallback: List[str] = Field(
        default=["utf-8", "gbk", "gb2312"]
    )

    # 日志级别
    log_level: str = Field(default="INFO")

    # ===================
    # RabbitMQ 配置
    # ===================
    rabbitmq_url: str = Field(
        default="amqp://omniops:omniops123@localhost:5672/",
        validation_alias="RABBITMQ_URL",
    )
    rabbitmq_management_url: str = Field(
        default="http://localhost:15672",
        validation_alias="RABBITMQ_MANAGEMENT_URL",
    )

    # ===================
    # HITL (Human-in-the-Loop) 配置
    # ===================
    hitl_timeout_seconds: int = Field(default=600, validation_alias="HITL_TIMEOUT_SECONDS")
    hitl_escalation_webhook_url: str = Field(default="", validation_alias="HITL_ESCALATION_WEBHOOK_URL")

    # ===================
    # Agent Consumer 并发数
    # ===================
    diagnosis_consumer_count: int = Field(default=2)
    planning_consumer_count: int = Field(default=1)

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
