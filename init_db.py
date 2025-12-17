# init_db.py

from app.database import Base, engine
from app.models import (
    user,
    enterprise,
    access_token,
    password_reset_token,
    user_session,
    client,
    product,
    job,
    setup,
    machine,
    production_line,
    composition_line,
    composition_line_machine,
    predicted_revenue_by_day,
    production_schedule_run,
    production_schedule_result,
    access_token,
    raw_material,
    product_composition,
    regular_shift,
    holiday,
    mold,
    mold_product,
    production_time,
)

def init():
    print("Criando todas as tabelas no banco de dados...")
    Base.metadata.create_all(bind=engine)
    print("Tabelas criadas com sucesso!")

if __name__ == "__main__":
    init()
