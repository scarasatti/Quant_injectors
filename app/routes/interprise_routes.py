from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.enterprise import Enterprise
from app.models.access_token import AccessToken
from app.schemas.enterprise_schema import EnterpriseCreate, EnterpriseOut
from app.utils.token_generator import generate_unique_token
from app.utils.email_sender import send_access_token_email
from app.auth.auth_bearer import get_current_user
from app.models.user import User

router = APIRouter(prefix="/enterprises")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/", response_model=EnterpriseOut)
def create_enterprise(data: EnterpriseCreate, db: Session = Depends(get_db)):
    if db.query(Enterprise).filter_by(name=data.name).first():
        raise HTTPException(status_code=400, detail="Empresa já cadastrada.")

    new_enterprise = Enterprise(
        name=data.name,
        representative_email=data.representative_email,
        access_count=data.access_count,
        model_type = data.model_type
    )
    db.add(new_enterprise)
    db.commit()
    db.refresh(new_enterprise)

    for _ in range(data.access_count):
        token = generate_unique_token()
        token_entry = AccessToken(
            token=token,
            email=data.representative_email,
            enterprise_id=new_enterprise.id
        )
        db.add(token_entry)
        send_access_token_email(data.representative_email, token)

    db.commit()
    return new_enterprise

@router.get("/", response_model=list[EnterpriseOut])
def list_enterprises(db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    return db.query(Enterprise).all()


@router.get("/{enterprise_id}", response_model=EnterpriseOut)
def get_enterprise(enterprise_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)
                   ):
    enterprise = db.query(Enterprise).get(enterprise_id)
    if not enterprise:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return enterprise

@router.put("/{enterprise_id}", response_model=EnterpriseOut)
def update_enterprise(enterprise_id: int, data: EnterpriseCreate, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    enterprise = db.query(Enterprise).get(enterprise_id)
    if not enterprise:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")

    enterprise.name = data.name
    enterprise.representative_email = data.representative_email
    enterprise.access_count = data.access_count
    db.commit()
    db.refresh(enterprise)
    return enterprise


@router.delete("/{enterprise_id}")
def delete_enterprise(enterprise_id: int, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    enterprise = db.query(Enterprise).get(enterprise_id)
    if not enterprise:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    db.delete(enterprise)
    db.commit()
    return {"message": "Empresa removida com sucesso."}
