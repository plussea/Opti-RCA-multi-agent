"""PostgreSQL 迁移脚本 — 运行 SQL 初始化文件"""
import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_migrations(database_url: str) -> None:
    """运行所有迁移 SQL"""
    engine = create_async_engine(database_url, echo=True)

    migrations_dir = Path(__file__).parent
    sql_file = migrations_dir / "001_init.sql"

    if not sql_file.exists():
        logger.error(f"Migration file not found: {sql_file}")
        sys.exit(1)

    logger.info(f"Running migrations from: {sql_file}")
    sql_content = sql_file.read_text(encoding="utf-8")

    async with engine.begin() as conn:
        # 逐条执行语句（排除 DO $$ ... $$ 块外的语句，因为需要分块执行）
        # SQLAlchemy 的 text() 不支持多语句 DO blocks，需拆分处理
        statements = sql_content.split(";")

        for stmt in statements:
            stmt = stmt.strip()
            if not stmt or stmt.startswith("--"):
                continue
            # 跳过包含 $$ 的 DO 块（单独处理）
            if "$$" in stmt:
                # DO 块整块执行
                try:
                    await conn.execute(text(stmt + ";"))
                    logger.info("  ✓ Executed DO block")
                except Exception as e:
                    logger.warning(f"  ! Skipped DO block: {e}")
                continue
            try:
                await conn.execute(text(stmt))
                logger.info(f"  ✓ {stmt[:60]}...")
            except Exception as e:
                logger.warning(f"  ! Skipped: {stmt[:40]}... ({e})")

    await engine.dispose()
    logger.info("Migrations complete.")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "postgresql+asyncpg://postgres:postgres@localhost:5432/omniops"
    asyncio.run(run_migrations(url))