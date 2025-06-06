from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.enterprise import Enterprise
from app.schemas.enterprise_schema import EnterpriseCreate, EnterpriseOut

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/enterprises", response_model=EnterpriseOut)
def create_enterprise(data: EnterpriseCreate, db: Session = Depends(get_db)):
    new_enterprise = Enterprise(name=data.name)
    db.add(new_enterprise)
    db.commit()
    db.refresh(new_enterprise)
    return new_enterprise
