from fastapi import APIRouter

from app.api.routers import admin, agent, agora, chat, health, people, recommend, stories

api_router = APIRouter()
api_router.include_router(health.router, tags=['health'])
api_router.include_router(people.router, prefix='/people', tags=['people'])
api_router.include_router(recommend.router, prefix='/recommend', tags=['recommend'])
api_router.include_router(chat.router, prefix='/chat', tags=['chat'])
api_router.include_router(agent.router, prefix='/agent', tags=['agent'])
api_router.include_router(admin.router, prefix='/admin', tags=['admin'])
api_router.include_router(stories.router, prefix='/stories', tags=['stories'])
api_router.include_router(agora.router, prefix='/agora', tags=['agora'])
