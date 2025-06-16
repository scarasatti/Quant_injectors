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
    predicted_revenue_by_day,
    production_schedule_run,
    production_schedule_result,
    access_token
)

def init():
    print("🧱 Criando todas as tabelas no banco de dados...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tabelas criadas com sucesso!")

if __name__ == "__main__":
    init()
