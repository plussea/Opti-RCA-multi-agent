"""SQLite 向量存储和 RAG 检索（带 OpenRouter Embedding）"""
import json
import logging
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from omniops.core.config import get_settings

logger = logging.getLogger(__name__)


class SQLiteVectorStore:
    """基于 SQLite 的简单向量存储（Demo 级）"""

    def __init__(self) -> None:
        settings = get_settings()
        self.db_path = settings.get_chroma_path() / "vector_store.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_entries (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                alarm_codes TEXT,
                root_cause TEXT,
                metadata TEXT,
                embedding TEXT,
                created_at TEXT,
                hit_count INTEGER DEFAULT 0,
                effectiveness_rate REAL DEFAULT 0.0
            )
        """)

        # 简单文本索引（LIKE）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS text_index (
                entry_id TEXT,
                keyword TEXT,
                FOREIGN KEY (entry_id) REFERENCES knowledge_entries(id)
            )
        """)

        conn.commit()
        conn.close()
        logger.info(f"SQLite vector store initialized at {self.db_path}")

    def reset(self) -> None:
        """重置向量存储"""
        if self.db_path.exists():
            self.db_path.unlink()
        self._init_db()

    def add_knowledge(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None,
        embedding: Optional[List[float]] = None,
    ) -> str:
        """添加知识条目（可选 embedding 向量）"""
        if doc_id is None:
            doc_id = f"know_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        metadata = metadata or {}
        alarm_codes = metadata.get("alarm_codes", [])
        root_cause = metadata.get("root_cause", "")

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO knowledge_entries
            (id, content, alarm_codes, root_cause, metadata, embedding, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                text,
                json.dumps(alarm_codes),
                root_cause,
                json.dumps(metadata),
                json.dumps(embedding) if embedding is not None else None,
                datetime.utcnow().isoformat(),
            ),
        )

        # 索引关键词
        keywords = self._extract_keywords(text, alarm_codes)
        for keyword in keywords:
            cursor.execute(
                "INSERT INTO text_index (entry_id, keyword) VALUES (?, ?)",
                (doc_id, keyword),
            )

        conn.commit()
        conn.close()

        logger.info(f"Added knowledge entry: {doc_id}" + (", embedding stored" if embedding else ""))
        return doc_id

    def _extract_keywords(self, text: str, alarm_codes: List[str]) -> List[str]:
        """提取关键词用于索引"""
        keywords = []

        # 添加告警码
        keywords.extend(alarm_codes)

        # 提取常见关键词
        important_words = [
            "光模块", "光纤", "光功率", "链路", "板卡", "电源",
            "故障", "告警", "根因", "修复", "更换",
        ]
        for word in important_words:
            if word in text:
                keywords.append(word)

        return list(set(keywords))

    def add_knowledge_batch(self, entries: List[Dict[str, Any]]) -> List[str]:
        """批量添加知识条目"""
        ids = []
        for entry in entries:
            doc_id = entry.get("id")
            ids.append(
                self.add_knowledge(
                    text=entry["text"],
                    metadata=entry.get("metadata"),
                    doc_id=doc_id,
                )
            )
        logger.info(f"Batch added {len(entries)} knowledge entries")
        return ids

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """文本检索相似案例"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # 提取查询关键词
        query_keywords = self._extract_keywords(query, query.split())

        if not query_keywords:
            # 无关键词，使用通用查询
            cursor.execute(
                """
                SELECT id, content, alarm_codes, root_cause, metadata, hit_count, effectiveness_rate
                FROM knowledge_entries
                ORDER BY hit_count DESC, effectiveness_rate DESC
                LIMIT ?
                """,
                (top_k,),
            )
        else:
            # 构建 OR 查询
            conditions = " OR ".join(["keyword LIKE ?" for _ in query_keywords])
            params = [f"%{kw}%" for kw in query_keywords]

            cursor.execute(
                f"""
                SELECT e.id, e.content, e.alarm_codes, e.root_cause, e.metadata, e.hit_count, e.effectiveness_rate,
                       COUNT(DISTINCT i.keyword) as match_count
                FROM knowledge_entries e
                LEFT JOIN text_index i ON e.id = i.entry_id AND ({conditions})
                GROUP BY e.id
                ORDER BY match_count DESC, e.hit_count DESC
                LIMIT ?
                """,
                params + [top_k],
            )

        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "content": row[1],
                "alarm_codes": json.loads(row[2]) if row[2] else [],
                "root_cause": row[3],
                "metadata": json.loads(row[4]) if row[4] else {},
                "hit_count": row[5],
                "effectiveness_rate": row[6],
                "similarity": 0.8,  # 简化相似度
            })

        conn.close()
        return results

    def search_by_alarm_code(
        self,
        alarm_codes: List[str],
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """按告警码精确检索"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        results = []
        for code in alarm_codes:
            cursor.execute(
                """
                SELECT id, content, alarm_codes, root_cause, metadata, hit_count, effectiveness_rate
                FROM knowledge_entries
                WHERE alarm_codes LIKE ?
                ORDER BY hit_count DESC, effectiveness_rate DESC
                LIMIT ?
                """,
                (f"%{code}%", top_k),
            )

            for row in cursor.fetchall():
                entry = {
                    "id": row[0],
                    "content": row[1],
                    "alarm_codes": json.loads(row[2]) if row[2] else [],
                    "root_cause": row[3],
                    "metadata": json.loads(row[4]) if row[4] else {},
                    "hit_count": row[5],
                    "effectiveness_rate": row[6],
                    "similarity": 0.9,  # 精确匹配更高相似度
                }
                if entry not in results:
                    results.append(entry)

        conn.close()
        return results[:top_k]

    def search_by_embedding(
        self,
        query_embedding: List[float],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """基于 embedding 向量的余弦相似度检索"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, content, alarm_codes, root_cause, metadata, embedding, hit_count, effectiveness_rate "
            "FROM knowledge_entries WHERE embedding IS NOT NULL"
        )

        scored: List[tuple[float, tuple]] = []
        for row in cursor.fetchall():
            emb_str = row[5]
            if not emb_str:
                continue
            try:
                emb = json.loads(emb_str)
            except Exception:
                continue
            # 余弦相似度（两个向量均已归一化）
            sim = sum(a * b for a, b in zip(query_embedding, emb))
            scored.append((sim, row))

        conn.close()

        # 按相似度降序排列
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for sim, row in scored[:top_k]:
            results.append({
                "id": row[0],
                "content": row[1],
                "alarm_codes": json.loads(row[2]) if row[2] else [],
                "root_cause": row[3],
                "metadata": json.loads(row[4]) if row[4] else {},
                "hit_count": row[6],
                "effectiveness_rate": row[7],
                "similarity": round(sim, 4),
            })
        return results

    def update_knowledge(self, doc_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """更新知识条目"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE knowledge_entries
                SET content = ?, metadata = ?
                WHERE id = ?
                """,
                (text, json.dumps(metadata or {}), doc_id),
            )

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Failed to update knowledge {doc_id}: {e}")
            return False

    def delete_knowledge(self, doc_id: str) -> bool:
        """删除知识条目"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("DELETE FROM text_index WHERE entry_id = ?", (doc_id,))
            cursor.execute("DELETE FROM knowledge_entries WHERE id = ?", (doc_id,))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Failed to delete knowledge {doc_id}: {e}")
            return False

    def increment_hit_count(self, doc_id: str) -> None:
        """增加命中计数"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE knowledge_entries SET hit_count = hit_count + 1 WHERE id = ?",
            (doc_id,),
        )
        conn.commit()
        conn.close()

    def get_count(self) -> int:
        """获取知识库条目数量"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM knowledge_entries")
        count = cursor.fetchone()[0]
        conn.close()
        return int(count)


# 全局单例
_vector_store: Optional[SQLiteVectorStore] = None


def get_vector_store() -> SQLiteVectorStore:
    """获取向量存储单例"""
    global _vector_store
    if _vector_store is None:
        _vector_store = SQLiteVectorStore()
    return _vector_store


# RAG 检索函数
async def search_similar_cases(
    query: str,
    alarm_codes: Optional[List[str]] = None,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """搜索相似案例（优先 embedding 语义检索，降级为文本匹配）"""
    vector_store = get_vector_store()
    results: List[Dict[str, Any]] = []

    # 1. 语义 embedding 检索（优先）
    try:
        from omniops.core.embeddings import get_embedding
        settings = get_settings()
        if settings.embedding_api_key:
            query_emb = await get_embedding(query)
            emb_results = vector_store.search_by_embedding(query_emb, top_k=top_k)
            results.extend(emb_results)
            logger.info(f"[RAG] embedding search: {len(emb_results)} results")
        else:
            logger.warning("[RAG] embedding disabled — EMBEDDING_API_KEY not set")
    except Exception as emb_err:
        logger.warning(f"[RAG] embedding search failed, falling back to text: {emb_err}")

    # 2. 降级：文本语义检索
    try:
        semantic_results = vector_store.search(query=query, top_k=top_k)
        results.extend(semantic_results)
    except Exception as e:
        logger.warning(f"[RAG] text search failed: {e}")

    # 3. 精确告警码匹配
    if alarm_codes:
        exact_results = vector_store.search_by_alarm_code(
            alarm_codes=alarm_codes,
            top_k=top_k,
        )
        results.extend(exact_results)

    # 去重 + 按相似度排序
    seen_ids: set = set()
    fused_results: List[Dict[str, Any]] = []
    for r in sorted(results, key=lambda x: x.get("similarity", 0), reverse=True):
        if r["id"] not in seen_ids:
            seen_ids.add(r["id"])
            fused_results.append(r)
            vector_store.increment_hit_count(r["id"])

    return fused_results[:top_k]


async def ingest_knowledge(
    root_cause: str,
    alarm_codes: List[str],
    suggested_actions: List[Dict[str, Any]],
    source_session: str,
) -> str:
    """将诊断结果摄入知识库（同时存储 embedding 向量）"""
    vector_store = get_vector_store()

    # alarm_codes 参数实际传入的是 alarm_names（语义一致，内部用 alarm_codes 列名存储）
    alarm_names = alarm_codes

    actions_text = "\n".join([
        f"{i+1}. {a.get('action', '')}（{a.get('estimated_time', '')}）"
        for i, a in enumerate(suggested_actions)
    ])

    text = f"""根因：{root_cause}
告警模式：{', '.join(alarm_names)}
修复步骤：
{actions_text}
"""

    metadata = {
        "alarm_codes": alarm_names,
        "root_cause": root_cause,
        "source_session": source_session,
        "created_at": datetime.utcnow().isoformat(),
    }

    # 计算 embedding 并存储
    embedding = None
    try:
        from omniops.core.embeddings import get_embedding
        settings = get_settings()
        if settings.embedding_api_key:
            embedding = await get_embedding(text)
            logger.info(f"[RAG] computed embedding for new entry, dim={len(embedding)}")
    except Exception as emb_err:
        logger.warning(f"[RAG] failed to compute embedding: {emb_err}")

    doc_id = vector_store.add_knowledge(text=text, metadata=metadata, embedding=embedding)
    return doc_id


async def init_seed_knowledge() -> None:
    """初始化种子知识库"""
    vector_store = get_vector_store()

    seed_entries = [
        {
            "text": """根因：K1SL64 光模块老化导致收光功率不足
告警模式：LINK_FAIL, POWER_LOW, BER_HIGH
修复步骤：
1. 使用光功率计测量收光功率（-28dBm 低于阈值）（5min）
2. 清洁光纤端面（10min）
3. 若清洁无效，更换 K1SL64 光模块（30min，brief_interrupt）""",
            "metadata": {
                "alarm_codes": ["LINK_FAIL", "POWER_LOW", "BER_HIGH"],
                "root_cause": "光模块老化",
                "ne_type": "K1SL64",
                "risk_level": "medium",
            },
        },
        {
            "text": """根因：光纤中断导致链路失效
告警模式：LINK_FAIL, OTU_LOF
修复步骤：
1. 使用 OTDR 测试光纤长度和损耗（15min）
2. 定位断点并更换光纤段（30min，brief_interrupt）
3. 验证光功率恢复正常""",
            "metadata": {
                "alarm_codes": ["LINK_FAIL", "OTU_LOF"],
                "root_cause": "光纤中断",
                "risk_level": "high",
            },
        },
        {
            "text": """根因：电源模块故障导致供电不足
告警模式：POWER_LOW, BD_STATUS
修复步骤：
1. 检查电源模块指示灯状态（5min）
2. 测量输入电压确认是否在正常范围（10min）
3. 若电源模块故障，联系供应商更换（60min，requires_planned）""",
            "metadata": {
                "alarm_codes": ["POWER_LOW", "BD_STATUS"],
                "root_cause": "电源模块故障",
                "risk_level": "high",
            },
        },
        {
            "text": """根因：板卡软件故障导致状态异常
告警模式：BD_STATUS, COMM_FAIL
修复步骤：
1. 收集板卡日志（10min）
2. 尝试重启板卡（需确认是否有备板）（15min，requires_planned）
3. 若重启无效，联系备件支持""",
            "metadata": {
                "alarm_codes": ["BD_STATUS", "COMM_FAIL"],
                "root_cause": "板卡软件故障",
                "risk_level": "medium",
            },
        },
    ]

    vector_store.add_knowledge_batch(seed_entries)
    logger.info(f"Seeded {len(seed_entries)} knowledge entries")
