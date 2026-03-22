FROM python:3.10-slim
WORKDIR /app
COPY backend/requirements.txt .
COPY --from=ghcr.io/astral-sh/uv:0.9.2 /uv /bin/
COPY --from=ghcr.io/astral-sh/uv:0.9.2 /uvx /bin/
RUN uv venv && uv pip install -r requirements.txt
# RUN pip install -r requirements.txt

COPY backend/main.py .

RUN mkdir /app/resources

# uvicorn src.main:app
# CMD ["uvx"]
CMD ["uv", "run" , "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]