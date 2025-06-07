from fastapi import FastAPI
from app.routes import user_routes, interprise_routes, auth_routes, password_reset_routes
from app.database import Base, engine
app = FastAPI()
app.include_router(user_routes.router)
app.include_router(interprise_routes.router)
app.include_router(auth_routes.router)
app.include_router(password_reset_routes.router)
