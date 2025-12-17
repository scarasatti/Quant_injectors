from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.raw_material import RawMaterial
from app.schemas.materia_prima_schema import MateriaPrimaCreate, MateriaPrimaUpdate, MateriaPrimaResponse
from app.models.product_composition import ProductComposition

router = APIRouter(prefix="/materia-prima", tags=["Matéria Prima"])

@router.post("", response_model=MateriaPrimaResponse)
def create_materia_prima(materia_prima: MateriaPrimaCreate, db: Session = Depends(get_db)):
    db_materia_prima = RawMaterial(**materia_prima.model_dump())
    db.add(db_materia_prima)
    db.commit()
    db.refresh(db_materia_prima)
    return db_materia_prima

@router.get("/", response_model=list[MateriaPrimaResponse])
def list_materia_prima(db: Session = Depends(get_db)):
    return db.query(RawMaterial).all()

@router.get("/{materia_prima_id}", response_model=MateriaPrimaResponse)
def get_materia_prima(materia_prima_id: int, db: Session = Depends(get_db)):
    materia_prima = db.query(RawMaterial).get(materia_prima_id)
    if not materia_prima:
        raise HTTPException(status_code=404, detail="Matéria prima não encontrada")
    return materia_prima

@router.put("/{materia_prima_id}", response_model=MateriaPrimaResponse)
def update_materia_prima(materia_prima_id: int, materia_prima: MateriaPrimaUpdate, db: Session = Depends(get_db)):
    db_materia_prima = db.query(RawMaterial).get(materia_prima_id)
    if not db_materia_prima:
        raise HTTPException(status_code=404, detail="Matéria prima não encontrada")
    for key, value in materia_prima.model_dump().items():
        setattr(db_materia_prima, key, value)
    db.commit()
    db.refresh(db_materia_prima)
    return db_materia_prima

@router.delete("/{materia_prima_id}")
def delete_materia_prima(materia_prima_id: int, db: Session = Depends(get_db)):
    db_materia_prima = db.query(RawMaterial).get(materia_prima_id)
    if not db_materia_prima:
        raise HTTPException(status_code=404, detail="Matéria prima não encontrada")
    
    # Verificar se há composições usando esta matéria prima
    composicoes = db.query(ProductComposition).filter(ProductComposition.materia_prima_id == materia_prima_id).all()
    if composicoes:
        raise HTTPException(
            status_code=400, 
            detail="Não é possível deletar matéria prima que está sendo usada em composições de produtos"
        )
    
    db.delete(db_materia_prima)
    db.commit()
    return {"message": "Matéria prima deletada com sucesso"}




