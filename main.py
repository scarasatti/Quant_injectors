from fastapi import FastAPI
from app.routes import user_routes, interprise_routes, auth_routes

app = FastAPI()

# Inclui as rotas de usuário
app.include_router(user_routes.router)
app.include_router(interprise_routes.router)
app.include_router(auth_routes.router)