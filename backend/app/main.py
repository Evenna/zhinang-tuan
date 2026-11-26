from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.router import api_router
from app.core.config import PROJECT_ROOT, get_settings
from app.db.session import init_db

settings = get_settings()
AGENT_PAGE = PROJECT_ROOT / 'agent.html'

app = FastAPI(
    title=settings.app_name,
    version='1.0.0',
    debug=settings.debug,
    description='Backend API for the AI Think Tank project, including the MR glasses DeepSeek agent.',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.on_event('startup')
def on_startup() -> None:
    init_db()


@app.get('/')
def root() -> dict[str, str]:
    return {
        'name': settings.app_name,
        'docs': '/docs',
        'api_prefix': settings.api_prefix,
        'agent': '/agent',
    }


@app.get('/agent')
def agent_demo() -> FileResponse:
    return FileResponse(AGENT_PAGE)


app.include_router(api_router, prefix=settings.api_prefix)
