FROM python:3.10-slim

WORKDIR /app

# 安装依赖
COPY pyproject.toml uv.lock* ./
RUN pip install uv && uv sync --frozen

# 复制代码
COPY src/ ./src/
COPY CLAUDE.md ./
COPY README.md ./

# 创建目录
RUN mkdir -p data/chroma uploads

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uv", "run", "uvicorn", "omniops.api.main:app", "--host", "0.0.0.0", "--port", "8000"]