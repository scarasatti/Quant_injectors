from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.user import User
from app.models.password_reset_token import PasswordResetToken
from app.schemas.password_reset_schema import PasswordResetRequest
from uuid import uuid4
from datetime import datetime, timedelta
from app.utils.email_sender import send_password_reset_email
from app.schemas.password_reset_schema import PasswordResetConfirm
from passlib.context import CryptContext
router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/password-reset/request")
def request_password_reset(data: PasswordResetRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    # Gera token e expiração
    token = str(uuid4())
    expires_at = datetime.utcnow() + timedelta(minutes=30)

    # Salva no banco
    reset_token = PasswordResetToken(
        user_id=user.id,
        token=token,
        expires_at=expires_at,
    )

    db.add(reset_token)
    db.commit()

    # Envia o e-mail
    email_enviado = send_password_reset_email(user.email, token)

    if not email_enviado:
        raise HTTPException(status_code=500, detail="Erro ao enviar o e-mail de recuperação.")

    return {"message": "Se o e-mail existir, você receberá instruções para redefinir a senha."}

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@router.post("/password-reset/confirm")
def confirm_password_reset(data: PasswordResetConfirm, db: Session = Depends(get_db)):
    reset_token = db.query(PasswordResetToken).filter(PasswordResetToken.token == data.token).first()

    if not reset_token:
        raise HTTPException(status_code=404, detail="Token inválido.")

    if reset_token.used:
        raise HTTPException(status_code=400, detail="Este token já foi utilizado.")

    if reset_token.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Token expirado.")

    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    user.hashed_password = pwd_context.hash(data.new_password)

    reset_token.used = True

    db.commit()

    return {"message": "Senha atualizada com sucesso."}