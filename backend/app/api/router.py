from fastapi import APIRouter

from app.api.routers import admin, chat, health, people, recommend

api_router = APIRouter()
api_router.include_router(health.router, tags=['health'])
api_router.include_router(people.router, prefix='/people', tags=['people'])
api_router.include_router(recommend.router, prefix='/recommend', tags=['recommend'])
api_router.include_router(chat.router, prefix='/chat', tags=['chat'])
api_router.include_router(admin.router, prefix='/admin', tags=['admin'])
