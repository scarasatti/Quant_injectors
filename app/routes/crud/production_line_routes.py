from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models.production_line import ProductionLine
from app.models.composition_line import CompositionLine
from app.schemas.production_line_schema import (
    ProductionLineCreate,
    ProductionLineUpdate,
    ProductionLineResponse,
    CompositionLineInfo
)

router = APIRouter(prefix="/production-lines", tags=["Production Lines"])

@router.post("", response_model=ProductionLineResponse)
def create_production_line(production_line: ProductionLineCreate, db: Session = Depends(get_db)):
    # Create the production line
    db_production_line = ProductionLine(
        name=production_line.name
    )
    db.add(db_production_line)
    db.commit()
    db.refresh(db_production_line)
    
    # Load composition lines for response
    db_production_line = db.query(ProductionLine).options(
        joinedload(ProductionLine.composition_lines).joinedload(CompositionLine.mold),
        joinedload(ProductionLine.composition_lines).joinedload(CompositionLine.product)
    ).filter(ProductionLine.id == db_production_line.id).first()
    
    return _build_response(db_production_line)

@router.get("/", response_model=list[ProductionLineResponse])
def list_production_lines(db: Session = Depends(get_db)):
    production_lines = db.query(ProductionLine).options(
        joinedload(ProductionLine.composition_lines).joinedload(CompositionLine.mold),
        joinedload(ProductionLine.composition_lines).joinedload(CompositionLine.product)
    ).all()
    return [_build_response(pl) for pl in production_lines]

@router.get("/{production_line_id}", response_model=ProductionLineResponse)
def get_production_line(production_line_id: int, db: Session = Depends(get_db)):
    production_line = db.query(ProductionLine).options(
        joinedload(ProductionLine.composition_lines).joinedload(CompositionLine.mold),
        joinedload(ProductionLine.composition_lines).joinedload(CompositionLine.product)
    ).filter(ProductionLine.id == production_line_id).first()
    
    if not production_line:
        raise HTTPException(status_code=404, detail="Production line not found")
    
    return _build_response(production_line)

@router.put("/{production_line_id}", response_model=ProductionLineResponse)
def update_production_line(
    production_line_id: int,
    production_line: ProductionLineUpdate,
    db: Session = Depends(get_db)
):
    db_production_line = db.query(ProductionLine).get(production_line_id)
    if not db_production_line:
        raise HTTPException(status_code=404, detail="Production line not found")
    
    # Update production line fields
    update_data = production_line.model_dump(exclude_none=True)
    for key, value in update_data.items():
        setattr(db_production_line, key, value)
    
    db.commit()
    db.refresh(db_production_line)
    
    # Load composition lines for response
    db_production_line = db.query(ProductionLine).options(
        joinedload(ProductionLine.composition_lines).joinedload(CompositionLine.mold),
        joinedload(ProductionLine.composition_lines).joinedload(CompositionLine.product)
    ).filter(ProductionLine.id == production_line_id).first()
    
    return _build_response(db_production_line)

@router.delete("/{production_line_id}")
def delete_production_line(production_line_id: int, db: Session = Depends(get_db)):
    db_production_line = db.query(ProductionLine).get(production_line_id)
    if not db_production_line:
        raise HTTPException(status_code=404, detail="Production line not found")
    
    # Cascade delete will handle CompositionLines
    db.delete(db_production_line)
    db.commit()
    return {"message": "Production line deleted successfully"}

def _build_response(production_line_obj: ProductionLine) -> ProductionLineResponse:
    """Helper method to build response with composition lines"""
    composition_lines = [
        CompositionLineInfo(
            id=cl.id,
            mold_id=cl.mold_id,
            product_id=cl.product_id,
            mold_name=cl.mold.name,
            product_name=cl.product.name
        ) for cl in production_line_obj.composition_lines
    ]
    
    return ProductionLineResponse(
        id=production_line_obj.id,
        name=production_line_obj.name,
        composition_lines=composition_lines
    )
