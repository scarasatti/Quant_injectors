from fastapi import FastAPI
from app.routes import (
    user_routes,
    interprise_routes,
    auth_routes,
    password_reset_routes,
    client_routes,
    product_routes,
    job_routes,
    setup_routes,
    upload_products_routes,
    upload_jobs_routes,
    upload_clientes_routes,
    setup_template_routes,
    upload_setup_matrix_routes,
    solver,
    inputs,
    production_schedule
)
app = FastAPI()

app.include_router(user_routes.router)
app.include_router(interprise_routes.router)
app.include_router(auth_routes.router)
app.include_router(password_reset_routes.router)
app.include_router(client_routes.router)
app.include_router(product_routes.router)
app.include_router(job_routes.router)
app.include_router(setup_routes.router)
app.include_router(upload_products_routes.router)
app.include_router(upload_clientes_routes.router)
app.include_router(upload_jobs_routes.router)
app.include_router(upload_setup_matrix_routes.router)
app.include_router(setup_template_routes.router)
app.include_router(solver.router, prefix="/sequenciamento", tags=["sequenciamento"])
app.include_router(inputs.router)

app.include_router(production_schedule.router)