from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.schemas.user_schema import UserCreate, UserOut
from passlib.context import CryptContext
from app.models.access_token import AccessToken
from app.auth.auth_bearer import get_current_user

router = APIRouter(prefix="/users", tags=["Users"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@router.post("/", response_model=UserOut)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    token_entry = db.query(AccessToken).filter_by(token=user.token, used=False).first()
    if not token_entry:
        raise HTTPException(status_code=401, detail="Token inválido ou já utilizado.")
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email já cadastrado.")
    hashed_password = pwd_context.hash(user.password)
    new_user = User(
        name=user.name,
        email=user.email,
        hashed_password=hashed_password,
        enterprise_id=int(token_entry.enterprise_id)
    )
    db.add(new_user)
    token_entry.used = True
    db.commit()
    db.refresh(new_user)
    return new_user

@router.get("/", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db)
):
    return db.query(User).all()

@router.get("/me", response_model=UserOut)
def get_logged_user(current_user: User = Depends(get_current_user)):
    return current_user

@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return user

@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    db.delete(user)
    db.commit()
    return {"message": "Usuário removido com sucesso."}

