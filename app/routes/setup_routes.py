from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.setup import Setup
from app.schemas.setup_schema import SetupTrocaCreate, SetupTrocaUpdate, SetupTrocaResponse

router = APIRouter(prefix="/setup_trocas", tags=["SetupTrocas"])

@router.post("/", response_model=SetupTrocaResponse)
def create_setup(setup: SetupTrocaCreate, db: Session = Depends(get_db)):
    existing = db.query(Setup).filter_by(
        produto_de=setup.produto_de,
        produto_para=setup.produto_para
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Setup já cadastrado")

    db_setup = Setup(**setup.model_dump())
    db.add(db_setup)
    db.commit()
    db.refresh(db_setup)

    return db_setup

@router.get("/", response_model=list[SetupTrocaResponse])
def list_setups(db: Session = Depends(get_db)):
    return db.query(Setup).all()

@router.get("/{setup_id}", response_model=SetupTrocaResponse)
def get_setup(setup_id: int, db: Session = Depends(get_db)):
    setup = db.query(Setup).get(setup_id)
    if not setup:
        raise HTTPException(status_code=404, detail="Setup not found")
    return setup

@router.put("/{setup_id}", response_model=SetupTrocaResponse)
def update_setup(setup_id: int, setup: SetupTrocaUpdate, db: Session = Depends(get_db)):
    db_setup = db.query(Setup).get(setup_id)
    if not db_setup:
        raise HTTPException(status_code=404, detail="Setup not found")
    for key, value in setup.model_dump().items():
        setattr(db_setup, key, value)
    db.commit()
    db.refresh(db_setup)
    return db_setup

@router.delete("/{setup_id}")
def delete_setup(setup_id: int, db: Session = Depends(get_db)):
    db_setup = db.query(Setup).get(setup_id)
    if not db_setup:
        raise HTTPException(status_code=404, detail="Setup not found")
    db.delete(db_setup)
    db.commit()
    return {"message": "Setup deleted"}
