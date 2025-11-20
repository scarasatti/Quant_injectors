from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.production_line import ProductionLine
from app.models.maquina import Maquina
from app.schemas.production_line_schema import ProductionLineCreate, ProductionLineUpdate, ProductionLineResponse

router = APIRouter(prefix="/production-lines", tags=["Production Lines"])

@router.post("", response_model=ProductionLineResponse)
def create_production_line(production_line: ProductionLineCreate, db: Session = Depends(get_db)):
    # Verificar se a máquina existe
    maquina = db.query(Maquina).get(production_line.fk_id_maquina)
    if not maquina:
        raise HTTPException(status_code=404, detail="Máquina não encontrada")
    
    # Validar que open_cavities não é maior que total_cavities
    if production_line.open_cavities > production_line.total_cavities:
        raise HTTPException(
            status_code=400, 
            detail="Cavidades abertas não podem ser maiores que o total de cavidades"
        )
    
    db_production_line = ProductionLine(**production_line.model_dump())
    db.add(db_production_line)
    db.commit()
    db.refresh(db_production_line)
    return db_production_line

@router.get("/", response_model=list[ProductionLineResponse])
def list_production_lines(db: Session = Depends(get_db)):
    return db.query(ProductionLine).all()

@router.get("/{production_line_id}", response_model=ProductionLineResponse)
def get_production_line(production_line_id: int, db: Session = Depends(get_db)):
    production_line = db.query(ProductionLine).get(production_line_id)
    if not production_line:
        raise HTTPException(status_code=404, detail="Linha de produção não encontrada")
    return production_line

@router.put("/{production_line_id}", response_model=ProductionLineResponse)
def update_production_line(
    production_line_id: int, 
    production_line: ProductionLineUpdate, 
    db: Session = Depends(get_db)
):
    db_production_line = db.query(ProductionLine).get(production_line_id)
    if not db_production_line:
        raise HTTPException(status_code=404, detail="Linha de produção não encontrada")
    
    # Verificar se a máquina existe (se foi alterada)
    if production_line.fk_id_maquina != db_production_line.fk_id_maquina:
        maquina = db.query(Maquina).get(production_line.fk_id_maquina)
        if not maquina:
            raise HTTPException(status_code=404, detail="Máquina não encontrada")
    
    # Validar que open_cavities não é maior que total_cavities
    if production_line.open_cavities > production_line.total_cavities:
        raise HTTPException(
            status_code=400, 
            detail="Cavidades abertas não podem ser maiores que o total de cavidades"
        )
    
    for key, value in production_line.model_dump().items():
        setattr(db_production_line, key, value)
    db.commit()
    db.refresh(db_production_line)
    return db_production_line

@router.delete("/{production_line_id}")
def delete_production_line(production_line_id: int, db: Session = Depends(get_db)):
    db_production_line = db.query(ProductionLine).get(production_line_id)
    if not db_production_line:
        raise HTTPException(status_code=404, detail="Linha de produção não encontrada")
    db.delete(db_production_line)
    db.commit()
    return {"message": "Linha de produção deletada com sucesso"}

