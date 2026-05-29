FROM python:3.12-slim
WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
RUN uv sync --no-dev

COPY revolut_tax_fr/ revolut_tax_fr/
COPY templates/ templates/

ENTRYPOINT ["uv", "run", "revolut-tax"]
