from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.schemas.user_schema import UserCreate, UserOut
from app.models.user import User
from app.database import SessionLocal
from passlib.context import CryptContext
from app.auth.dependencies import get_current_user
from fastapi import Depends

router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Dependência para obter sessão com o banco
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/me")
def read_current_user(current_user: dict = Depends(get_current_user)):
    return {"user_id": current_user.get("sub")}

@router.post("/users", response_model=UserOut)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    # Verifica se já existe usuário com esse e-mail
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email já cadastrado.")

    # Criptografa a senha
    hashed_password = pwd_context.hash(user.password)

    # Cria o usuário
    new_user = User(
        name=user.name,
        email=user.email,
        hashed_password=hashed_password,
        enterprise_id=user.enterprise_id,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user
