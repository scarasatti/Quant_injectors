from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.database import SessionLocal
from app.models.user import User
from app.models.user_session import UserSession
from app.auth.auth_bearer import get_current_user, oauth2_scheme
from app.auth.jwt_handler import create_access_token, create_refresh_token

from jose import jwt, ExpiredSignatureError, JWTError
from app.auth.jwt_handler import SECRET_KEY, ALGORITHM

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
MAX_SESSIONS = 10000000


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

    # Expira sessões antigas
    sessions = db.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.is_active == True
    ).all()

    for s in sessions:
        try:
            jwt.decode(s.token, SECRET_KEY, algorithms=[ALGORITHM])
        except (ExpiredSignatureError, JWTError):
            s.is_active = False

    db.commit()

    active_sessions = db.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.is_active == True
    ).count()

    if active_sessions >= MAX_SESSIONS:
        raise HTTPException(status_code=403, detail="Número máximo de sessões ativas atingido.")

    user.token_version += 1
    db.commit()
    db.refresh(user)

    access_token = create_access_token({
        "sub": str(user.id),
        "token_version": user.token_version
    })

    refresh_token = create_refresh_token({
        "sub": str(user.id)
    })

    new_session = UserSession(user_id=user.id, token=access_token)
    db.add(new_session)
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "enterprise_id": user.enterprise_id
        }
    }

@router.post("/logout")
def logout(
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    current_user.token_version += 1
    db.commit()

    session = db.query(UserSession).filter_by(
        user_id=current_user.id,
        token=token,
        is_active=True
    ).first()
    if session:
        session.is_active = False
        db.commit()

    return {"msg": "Logout realizado com sucesso"}

@router.post("/refresh")
def refresh_token(
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):

    session = db.query(UserSession).filter_by(
        user_id=current_user.id,
        token=token,
        is_active=True
    ).first()

    if not session:
        raise HTTPException(status_code=401, detail="Sessão inativa ou token inválido")

    # Gera novo token
    new_token = create_access_token({"sub": str(current_user.id)})

    # Atualiza a sessão no banco
    session.token = new_token
    db.commit()

    return {
        "access_token": new_token,
        "token_type": "bearer"
    }


