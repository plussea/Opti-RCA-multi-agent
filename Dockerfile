FROM python:3.9-slim

WORKDIR /app

# 1. 先复制所有源代码（需在 uv sync 之前）
COPY src/ ./src/
COPY demo.py ./

# 2. 再复制包配置（uv sync 依赖 pyproject.toml + src/）
COPY pyproject.toml uv.lock ./

# 3. 安装依赖
RUN pip install uv && uv sync --frozen

# 4. 文档（不影响构建）
COPY CLAUDE.md README.md ./

# 5. 创建目录
RUN mkdir -p data/chroma uploads

# 6. 非 root 用户
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# 7. 暴露端口
EXPOSE 8000

# 8. 启动命令
CMD ["uv", "run", "uvicorn", "omniops.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
