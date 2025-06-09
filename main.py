
from fastapi import FastAPI
from app.routes import user_routes, interprise_routes, auth_routes, password_reset_routes, client_routes, product_routes,job_routes, setup_routes

app = FastAPI()
app.include_router(user_routes.router)
app.include_router(interprise_routes.router)
app.include_router(auth_routes.router)
app.include_router(password_reset_routes.router)
app.include_router(client_routes.router)
app.include_router(product_routes.router)
app.include_router(job_routes.router)
app.include_router(setup_routes.router)
