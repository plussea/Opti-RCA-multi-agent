-- PostgreSQL + pgvector 初始化脚本
-- 运行方式: psql -h localhost -U postgres -d omniops -f tools/migrations/001_init.sql
-- 或者在 docker-compose 中通过 command 或 init script 运行

-- 1. 启用 pgvector 扩展（单个数据库执行一次即可）
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. 在 knowledge_embeddings 表上创建 HNSW 索引
-- 这在 SQLAlchemy create_all 之后运行，因为 vector 列在迁移中添加
-- 注意：如果列不存在则跳过

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'knowledge_embeddings'
        AND column_name = 'embedding'
    ) THEN
        -- 添加 vector 列（1536 维度，与 OpenAI ada-002 兼容）
        ALTER TABLE knowledge_embeddings ADD COLUMN embedding vector(1536);
    END IF;
EXCEPTION
    WHEN undefined_column THEN
        RAISE NOTICE 'Embedding column already exists or table not yet created';
END $$;

-- 3. 创建 HNSW 索引（比 IVFFlat 更快，索引构建时间更长但查询更快）
-- 使用 cosine 距离（最适合语义相似度）
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_indexes WHERE indexname = 'ix_knowledge_embeddings_embedding'
    ) THEN
        RAISE NOTICE 'HNSW index already exists';
    ELSE
        CREATE INDEX ix_knowledge_embeddings_embedding
        ON knowledge_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    END IF;
EXCEPTION
    WHEN undefined_table THEN
        RAISE NOTICE 'Table knowledge_embeddings not yet created, run SQLAlchemy first';
END $$;

-- 4. Agent 对话记录表（通常由 SQLAlchemy create_all 自动创建，但可手动补充）
-- 此迁移确保 agent_conversations 表存在
-- 注意：sessions 表必须先存在（外键约束）

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'agent_conversations'
    ) THEN
        CREATE TABLE agent_conversations (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(50) NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            agent_name VARCHAR(50) NOT NULL,
            step_order INTEGER NOT NULL,
            llm_input JSONB,
            llm_output JSONB,
            cognitive_summary JSONB,
            tokens_used INTEGER,
            model_name VARCHAR(100),
            duration_ms INTEGER,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX ix_agent_conversations_session ON agent_conversations(session_id);
        CREATE INDEX ix_agent_conversations_agent ON agent_conversations(agent_name);
    END IF;
EXCEPTION
    WHEN duplicate_table THEN
        RAISE NOTICE 'agent_conversations table already exists';
END $$;

-- 5. 创建视图：按根因统计知识库命中率（运维分析用）
CREATE OR REPLACE VIEW knowledge_stats AS
SELECT
    root_cause,
    COUNT(*) as total_entries,
    SUM(hit_count) as total_hits,
    AVG(effectiveness_rate) as avg_effectiveness,
    MAX(hit_count) as max_hits
FROM knowledge_embeddings
GROUP BY root_cause
ORDER BY total_hits DESC;