from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.database import get_db
from app.models.user import User
from app.schemas.user_schema import UserCreate, UserOut
from passlib.context import CryptContext
from app.models.access_token import AccessToken
from app.auth.auth_bearer import get_current_user

from app.auth.auth_bearer import get_current_user
from app.models.user import User

router = APIRouter(prefix="/users", tags=["Users"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.post("/", response_model=UserOut)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    # 🔒 Verifica se o token existe e está válido
    token_entry = db.query(AccessToken).filter_by(token=user.token, used=False).first()
    if not token_entry:
        raise HTTPException(status_code=401, detail="Token inválido ou já utilizado.")

    # 📧 Verifica se o e-mail já está em uso
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email já cadastrado.")

    try:
        # 👤 Cria o usuário associado à empresa do token
        hashed_password = pwd_context.hash(user.password)
        db_user = User(
            name=user.name,
            email=user.email,
            hashed_password=hashed_password,
            enterprise_id=int(token_entry.enterprise_id)  # força tipo int
        )
        db.add(db_user)

        # 🔐 Marca o token como usado
        token_entry.used = True
        db.commit()
        db.refresh(db_user)
        return db_user

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao criar usuário. Tente novamente.")


@router.get("/", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)

):
    return db.query(User).all()


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)

):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return user


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)

):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    db.delete(user)
    db.commit()
    return {"message": "Usuário removido com sucesso."}


@router.get("/me", response_model=UserOut)
def get_logged_user(current_user: User = Depends(get_current_user)):
    return current_user

@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return user