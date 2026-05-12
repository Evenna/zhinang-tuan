# AI Think Tank Backend

FastAPI backend for the AI Think Tank project.

## Features

- People directory and detail APIs
- Persona-profile based prompt assembly
- Per-person knowledge retrieval for lightweight RAG
- DeepSeek chat integration through the OpenAI-compatible API
- Import pipeline for `data/people_dataset_v1.json`
- Single advisor and group advisor response APIs

## Quick Start

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

## Environment Variables

- `DATABASE_URL`: Defaults to local SQLite for easy startup.
- `DEEPSEEK_API_KEY`: Required for chat endpoints.
- `DEEPSEEK_MODEL`: Defaults to `deepseek-chat`.

## Common Commands

```bash
# Start server
uvicorn app.main:app --reload --port 8000

# Import people dataset into the database
python -m app.tasks.import_people_data --force-rebuild
```
