from fastapi import APIRouter, Depends
from app.database import Base, engine
from app.models import (
    user, enterprise, password_reset_token, user_session,
    client, product, job, setup,
    predicted_revenue_by_day, production_schedule_run, production_schedule_result
)

from app.auth.auth_bearer import get_current_user
from app.models.user import User

router = APIRouter()

@router.get("/init-db", tags=["Dev"])
def create_tables(current_user: User = Depends(get_current_user)):
    Base.metadata.create_all(bind=engine)
    return {"message": "🗂️ Tabelas criadas com sucesso!"}
