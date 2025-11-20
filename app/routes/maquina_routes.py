from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.maquina import Maquina
from app.schemas.maquina_schema import MaquinaCreate, MaquinaUpdate, MaquinaResponse

router = APIRouter(prefix="/maquinas", tags=["Maquinas"])

@router.post("", response_model=MaquinaResponse)
def create_maquina(maquina: MaquinaCreate, db: Session = Depends(get_db)):
    db_maquina = Maquina(**maquina.model_dump())
    db.add(db_maquina)
    db.commit()
    db.refresh(db_maquina)
    return db_maquina

@router.get("/", response_model=list[MaquinaResponse])
def list_maquinas(db: Session = Depends(get_db)):
    return db.query(Maquina).all()

@router.get("/{maquina_id}", response_model=MaquinaResponse)
def get_maquina(maquina_id: int, db: Session = Depends(get_db)):
    maquina = db.query(Maquina).get(maquina_id)
    if not maquina:
        raise HTTPException(status_code=404, detail="Máquina não encontrada")
    return maquina

@router.put("/{maquina_id}", response_model=MaquinaResponse)
def update_maquina(maquina_id: int, maquina: MaquinaUpdate, db: Session = Depends(get_db)):
    db_maquina = db.query(Maquina).get(maquina_id)
    if not db_maquina:
        raise HTTPException(status_code=404, detail="Máquina não encontrada")
    for key, value in maquina.model_dump().items():
        setattr(db_maquina, key, value)
    db.commit()
    db.refresh(db_maquina)
    return db_maquina

@router.delete("/{maquina_id}")
def delete_maquina(maquina_id: int, db: Session = Depends(get_db)):
    db_maquina = db.query(Maquina).get(maquina_id)
    if not db_maquina:
        raise HTTPException(status_code=404, detail="Máquina não encontrada")
    db.delete(db_maquina)
    db.commit()
    return {"message": "Máquina deletada com sucesso"}

