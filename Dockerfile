FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
# Copy from the cache instead of linking since it's inside container
ENV UV_LINK_MODE=copy

# Install dependencies first for efficient caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy application code
COPY src ./src
COPY README.md ./

# Install project
RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "investment_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
