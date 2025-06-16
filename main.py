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
    production_schedule,
    db_setup
)

app = FastAPI()

# 📦 Rotas organizadas com tags (visíveis no Swagger)
app.include_router(user_routes.router, tags=["Users"])
app.include_router(interprise_routes.router, tags=["Enterprises"])
app.include_router(auth_routes.router, tags=["Auth"])
app.include_router(password_reset_routes.router, tags=["Password Reset"])
app.include_router(client_routes.router, tags=["Clients"])
app.include_router(product_routes.router, tags=["Products"])
app.include_router(job_routes.router, tags=["Jobs"])
app.include_router(setup_routes.router, tags=["Setups"])
app.include_router(upload_products_routes.router, tags=["Uploads"])
app.include_router(upload_clientes_routes.router, tags=["Uploads"])
app.include_router(upload_jobs_routes.router, tags=["Uploads"])
app.include_router(upload_setup_matrix_routes.router, tags=["Uploads"])
app.include_router(setup_template_routes.router, tags=["Download Setup Template"])
app.include_router(solver.router, prefix="/sequenciamento", tags=["Sequenciamento"])
app.include_router(inputs.router, tags=["Inputs"])
app.include_router(production_schedule.router, tags=["Production Schedule"])
app.include_router(db_setup.router, tags=["DB Setup"])

@app.get("/")
def root():
    return {"message": "API rodando com sucesso!"}
