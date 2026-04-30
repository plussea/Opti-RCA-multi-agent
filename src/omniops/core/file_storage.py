"""文件存储服务"""
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from omniops.core.config import get_settings

logger = logging.getLogger(__name__)


class FileStorage:
    """本地文件存储服务"""

    def __init__(self) -> None:
        settings = get_settings()
        self.upload_dir = settings.get_upload_path()
        self.max_size = settings.max_upload_size

    async def save_upload(
        self,
        content: bytes,
        filename: str,
        session_id: Optional[str] = None,
    ) -> str:
        """保存上传文件

        Args:
            content: 文件内容
            filename: 原始文件名
            session_id: 会话 ID（用于组织目录）

        Returns:
            保存后的文件路径
        """
        # 验证文件大小
        if len(content) > self.max_size:
            raise ValueError(f"File too large: {len(content)} > {self.max_size}")

        # 生成唯一文件名
        ext = Path(filename).suffix.lower()
        unique_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"

        # 确定目录
        subdir = self.upload_dir / session_id if session_id else self.upload_dir / "unknown"

        subdir.mkdir(parents=True, exist_ok=True)

        # 保存文件
        file_path = subdir / unique_name
        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(f"File saved: {file_path}")
        return str(file_path)

    async def get_file(self, file_path: str) -> Optional[bytes]:
        """读取文件内容"""
        path = Path(file_path)
        if not path.exists():
            return None

        with open(path, "rb") as f:
            return f.read()

    async def delete_file(self, file_path: str) -> bool:
        """删除文件"""
        path = Path(file_path)
        if path.exists():
            path.unlink()
            logger.info(f"File deleted: {file_path}")
            return True
        return False

    async def delete_session_files(self, session_id: str) -> int:
        """删除会话关联的所有文件"""
        session_dir = self.upload_dir / session_id
        if not session_dir.exists():
            return 0

        count = 0
        for file_path in session_dir.iterdir():
            file_path.unlink()
            count += 1

        session_dir.rmdir()
        logger.info(f"Deleted {count} files for session {session_id}")
        return count

    async def list_session_files(self, session_id: str) -> list:
        """列出会话关联的文件"""
        session_dir = self.upload_dir / session_id
        if not session_dir.exists():
            return []

        return [
            {"name": f.name, "path": str(f), "size": f.stat().st_size}
            for f in session_dir.iterdir()
        ]


# 全局单例
_storage: Optional[FileStorage] = None


def get_file_storage() -> FileStorage:
    """获取文件存储单例"""
    global _storage
    if _storage is None:
        _storage = FileStorage()
    return _storage
