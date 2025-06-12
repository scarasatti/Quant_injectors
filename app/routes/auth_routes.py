from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.database import SessionLocal
from app.models.user import User
from app.models.user_session import UserSession
from app.auth.jwt_handler import create_access_token
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/Criador de tabelas", tags=["Banco de Dados"])
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

    # Verifica sessões ativas
    active_sessions = db.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.is_active == True
    ).count()

    if active_sessions >= MAX_SESSIONS:
        raise HTTPException(status_code=403, detail="Limite de sessões simultâneas atingido.")

    # Gera e salva nova sessão
    token = create_access_token({"sub": str(user.id)})

    db.add(UserSession(user_id=user.id, token=token))
    db.commit()

    return {"access_token": token, "token_type": "bearer"}


@router.post("/logout")
def logout(
    request: Request,
    payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=400, detail="Token não encontrado ou mal formatado.")

    token = auth_header.replace("Bearer ", "").strip()

    session = db.query(UserSession).filter_by(token=token, is_active=True).first()
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    session.is_active = False
    db.commit()

    return {"message": "Logout realizado com sucesso."}
