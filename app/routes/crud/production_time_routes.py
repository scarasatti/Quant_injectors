from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models.production_time import ProductionTime
from app.models.machine import Machine
from app.models.product import Product
from app.models.mold import Mold
from app.models.mold_product import MoldProduct
from app.schemas.production_time_schema import (
    ProductionTimeCreate,
    ProductionTimeUpdate,
    ProductionTimeResponse
)

router = APIRouter(prefix="/production-time", tags=["Production Time"])

def validate_product_belongs_to_mold(db: Session, product_id: int, mold_id: int):
    """Validate that the product belongs to the specified mold"""
    mold_product = db.query(MoldProduct).filter(
        MoldProduct.product_id == product_id,
        MoldProduct.mold_id == mold_id
    ).first()
    
    if not mold_product:
        raise HTTPException(
            status_code=400,
            detail=f"Product {product_id} does not belong to mold {mold_id}. "
                   "The product must be associated with the mold before creating production time."
        )

@router.post("", response_model=ProductionTimeResponse)
def create_production_time(production_time: ProductionTimeCreate, db: Session = Depends(get_db)):
    # Validate that machine exists
    machine = db.query(Machine).get(production_time.machine_id)
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    
    # Validate that product exists
    product = db.query(Product).get(production_time.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Validate that mold exists
    mold = db.query(Mold).get(production_time.mold_id)
    if not mold:
        raise HTTPException(status_code=404, detail="Mold not found")
    
    # Validate that product belongs to the mold
    validate_product_belongs_to_mold(db, production_time.product_id, production_time.mold_id)
    
    # Check if this exact combination already exists (unique constraint)
    existing = db.query(ProductionTime).filter(
        ProductionTime.machine_id == production_time.machine_id,
        ProductionTime.product_id == production_time.product_id,
        ProductionTime.mold_id == production_time.mold_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="A production time with this exact combination of machine, product, and mold already exists"
        )
    
    # Create production time
    db_production_time = ProductionTime(**production_time.model_dump())
    db.add(db_production_time)
    db.commit()
    db.refresh(db_production_time)
    
    # Load relations for response
    db_production_time = db.query(ProductionTime).options(
        joinedload(ProductionTime.machine),
        joinedload(ProductionTime.product),
        joinedload(ProductionTime.mold)
    ).filter(ProductionTime.id == db_production_time.id).first()
    
    return ProductionTimeResponse.from_orm_with_relations(db_production_time)

@router.get("/", response_model=list[ProductionTimeResponse])
def list_production_times(db: Session = Depends(get_db)):
    production_times = db.query(ProductionTime).options(
        joinedload(ProductionTime.machine),
        joinedload(ProductionTime.product),
        joinedload(ProductionTime.mold)
    ).all()
    return [ProductionTimeResponse.from_orm_with_relations(pt) for pt in production_times]

@router.get("/{production_time_id}", response_model=ProductionTimeResponse)
def get_production_time(production_time_id: int, db: Session = Depends(get_db)):
    production_time = db.query(ProductionTime).options(
        joinedload(ProductionTime.machine),
        joinedload(ProductionTime.product),
        joinedload(ProductionTime.mold)
    ).filter(ProductionTime.id == production_time_id).first()
    
    if not production_time:
        raise HTTPException(status_code=404, detail="Production time not found")
    
    return ProductionTimeResponse.from_orm_with_relations(production_time)

@router.put("/{production_time_id}", response_model=ProductionTimeResponse)
def update_production_time(
    production_time_id: int,
    production_time: ProductionTimeUpdate,
    db: Session = Depends(get_db)
):
    db_production_time = db.query(ProductionTime).get(production_time_id)
    if not db_production_time:
        raise HTTPException(status_code=404, detail="Production time not found")
    
    # If product or mold is being updated, validate the relationship
    if production_time.product_id is not None or production_time.mold_id is not None:
        product_id = production_time.product_id if production_time.product_id is not None else db_production_time.product_id
        mold_id = production_time.mold_id if production_time.mold_id is not None else db_production_time.mold_id
        validate_product_belongs_to_mold(db, product_id, mold_id)
    
    # Get final values for validation
    final_machine_id = production_time.machine_id if production_time.machine_id is not None else db_production_time.machine_id
    final_product_id = production_time.product_id if production_time.product_id is not None else db_production_time.product_id
    final_mold_id = production_time.mold_id if production_time.mold_id is not None else db_production_time.mold_id
    
    # Check if the new combination already exists (excluding current record)
    existing = db.query(ProductionTime).filter(
        ProductionTime.machine_id == final_machine_id,
        ProductionTime.product_id == final_product_id,
        ProductionTime.mold_id == final_mold_id,
        ProductionTime.id != production_time_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="A production time with this exact combination of machine, product, and mold already exists"
        )
    
    # Update fields
    update_data = production_time.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_production_time, key, value)
    
    db.commit()
    db.refresh(db_production_time)
    
    # Load relations for response
    db_production_time = db.query(ProductionTime).options(
        joinedload(ProductionTime.machine),
        joinedload(ProductionTime.product),
        joinedload(ProductionTime.mold)
    ).filter(ProductionTime.id == production_time_id).first()
    
    return ProductionTimeResponse.from_orm_with_relations(db_production_time)

@router.delete("/{production_time_id}")
def delete_production_time(production_time_id: int, db: Session = Depends(get_db)):
    db_production_time = db.query(ProductionTime).get(production_time_id)
    if not db_production_time:
        raise HTTPException(status_code=404, detail="Production time not found")
    
    db.delete(db_production_time)
    db.commit()
    return {"message": "Production time deleted successfully"}

