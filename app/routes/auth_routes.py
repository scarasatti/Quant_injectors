from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.database import SessionLocal
from app.models.user import User
from app.models.user_session import UserSession
from app.auth.jwt_handler import create_access_token


router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
MAX_SESSIONS = 1


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == form_data.username).first()

    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    # 🔒 Finaliza sessões antigas automaticamente
    db.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.is_active == True
    ).update({"is_active": False})
    db.commit()

    # 🔐 Gera novo token e cria nova sessão
    token = create_access_token({"sub": str(user.id)})
    new_session = UserSession(user_id=user.id, token=token)
    db.add(new_session)
    db.flush()
    db.commit()

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "enterprise_id": user.enterprise_id
        }
    }
