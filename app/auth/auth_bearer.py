from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.user_session import UserSession
import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY não configurada no ..env")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não autorizado",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = int(payload.get("sub"))
        token_version: int = payload.get("token_version")
        if user_id is None or token_version is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).get(user_id)
    if user is None or user.token_version != token_version:
        raise credentials_exception

    # Verifica se a sessão do token ainda está ativa
    session = db.query(UserSession).filter_by(
        user_id=user.id,
        token=token,
        is_active=True
    ).first()

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada ou inválida",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
