# Public web app only: the shop plus per-visitor database copies. No Playwright, no Chromium, no LLM SDK.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    SHOPGYM_LIVE=1 \
    SHOPGYM_DATA_DIR=/app/data \
    PATH=/app/.venv/bin:$PATH

COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /bin/uv

RUN useradd --create-home --uid 10001 shop
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-package playwright --no-install-package anthropic \
        --no-install-package pillow --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev --no-install-package playwright --no-install-package anthropic \
        --no-install-package pillow

# Build the seed template and the default database once, at image build time, so the first visitor is fast.
RUN python -c "from pathlib import Path; from shopgym.env.episodes import template_path; \
from shopgym.app.web import episode_db_path; d = Path('/app/data'); template_path(d, 7); episode_db_path(d, None)" \
    && chown -R shop:shop /app/data

USER shop
EXPOSE 4200
CMD ["sh", "-c", "exec uvicorn shopgym.app.server:create_app --factory --host 0.0.0.0 --port ${PORT:-4200} --workers 1 --log-level warning"]
