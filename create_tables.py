from app.database import Base, engine
from app.models import user, enterprise, password_reset_token, user_session, client, product, job, setup, predicted_revenue_by_day, production_schedule_run, production_schedule_result

Base.metadata.create_all(bind=engine)
print("🗂️ Tabelas criadas com sucesso!")