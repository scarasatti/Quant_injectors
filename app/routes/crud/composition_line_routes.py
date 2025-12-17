from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models.composition_line import CompositionLine
from app.models.composition_line_machine import CompositionLineMachine
from app.models.production_line import ProductionLine
from app.models.mold import Mold
from app.models.product import Product
from app.models.mold_product import MoldProduct
from app.models.machine import Machine
from app.models.production_time import ProductionTime
from app.schemas.composition_line_schema import (
    CompositionLineCreate,
    CompositionLineUpdate,
    CompositionLineResponse
)

router = APIRouter(prefix="/composition-lines", tags=["Composition Lines"])

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
                   "The product must be associated with the mold before creating a composition line."
        )

@router.post("", response_model=CompositionLineResponse)
def create_composition_line(composition_line: CompositionLineCreate, db: Session = Depends(get_db)):
    # Validate that production line exists
    production_line = db.query(ProductionLine).get(composition_line.production_line_id)
    if not production_line:
        raise HTTPException(status_code=404, detail="Production line not found")
    
    # Validate that mold exists
    mold = db.query(Mold).get(composition_line.mold_id)
    if not mold:
        raise HTTPException(status_code=404, detail="Mold not found")
    
    # Validate that product exists
    product = db.query(Product).get(composition_line.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Validate that product belongs to the mold (via MoldProduct relationship)
    validate_product_belongs_to_mold(db, composition_line.product_id, composition_line.mold_id)
    
    # Validate that at least one machine was provided
    if not composition_line.machines or len(composition_line.machines) == 0:
        raise HTTPException(
            status_code=400,
            detail="A composition line must have at least one machine"
        )
    
    # Check if all machines exist
    machine_ids = composition_line.machines
    existing_machines = db.query(Machine).filter(Machine.id.in_(machine_ids)).all()
    if len(existing_machines) != len(machine_ids):
        raise HTTPException(
            status_code=404,
            detail="One or more machines not found"
        )
    
    # Validate that ProductionTime exists for each machine
    for machine_id in machine_ids:
        production_time = db.query(ProductionTime).filter(
            ProductionTime.machine_id == machine_id,
            ProductionTime.product_id == composition_line.product_id,
            ProductionTime.mold_id == composition_line.mold_id
        ).first()
        if not production_time:
            raise HTTPException(
                status_code=400,
                detail=f"ProductionTime not found for machine {machine_id}, "
                       f"product {composition_line.product_id}, and mold {composition_line.mold_id}. "
                       "Please create a ProductionTime entry first."
            )
    
    # Create the composition line
    composition_line_data = composition_line.model_dump(exclude={'machines'})
    db_composition_line = CompositionLine(**composition_line_data)
    db.add(db_composition_line)
    db.flush()  # To get the ID
    
    # Associate machines (cycle time will be retrieved from ProductionTime)
    for machine_id in machine_ids:
        composition_line_machine = CompositionLineMachine(
            composition_line_id=db_composition_line.id,
            machine_id=machine_id
        )
        db.add(composition_line_machine)
    
    db.commit()
    db.refresh(db_composition_line)
    
    # Load relations for response
    db_composition_line = db.query(CompositionLine).options(
        joinedload(CompositionLine.production_line),
        joinedload(CompositionLine.mold),
        joinedload(CompositionLine.product),
        joinedload(CompositionLine.machines).joinedload(CompositionLineMachine.machine)
    ).filter(CompositionLine.id == db_composition_line.id).first()
    
    return CompositionLineResponse.from_orm_with_relations(db_composition_line, db)

@router.get("/", response_model=list[CompositionLineResponse])
def list_composition_lines(db: Session = Depends(get_db)):
    composition_lines = db.query(CompositionLine).options(
        joinedload(CompositionLine.production_line),
        joinedload(CompositionLine.mold),
        joinedload(CompositionLine.product),
        joinedload(CompositionLine.machines).joinedload(CompositionLineMachine.machine)
    ).all()
    return [CompositionLineResponse.from_orm_with_relations(cl, db) for cl in composition_lines]

@router.get("/{composition_line_id}", response_model=CompositionLineResponse)
def get_composition_line(composition_line_id: int, db: Session = Depends(get_db)):
    composition_line = db.query(CompositionLine).options(
        joinedload(CompositionLine.production_line),
        joinedload(CompositionLine.mold),
        joinedload(CompositionLine.product),
        joinedload(CompositionLine.machines).joinedload(CompositionLineMachine.machine)
    ).filter(CompositionLine.id == composition_line_id).first()
    
    if not composition_line:
        raise HTTPException(status_code=404, detail="Composition line not found")
    
    return CompositionLineResponse.from_orm_with_relations(composition_line, db)

@router.put("/{composition_line_id}", response_model=CompositionLineResponse)
def update_composition_line(
    composition_line_id: int,
    composition_line: CompositionLineUpdate,
    db: Session = Depends(get_db)
):
    db_composition_line = db.query(CompositionLine).get(composition_line_id)
    if not db_composition_line:
        raise HTTPException(status_code=404, detail="Composition line not found")
    
    # Get final values for validation
    final_mold_id = composition_line.mold_id if composition_line.mold_id is not None else db_composition_line.mold_id
    final_product_id = composition_line.product_id if composition_line.product_id is not None else db_composition_line.product_id
    final_production_line_id = composition_line.production_line_id if composition_line.production_line_id is not None else db_composition_line.production_line_id
    
    # If product or mold is being updated, validate the relationship
    if composition_line.product_id is not None or composition_line.mold_id is not None:
        validate_product_belongs_to_mold(db, final_product_id, final_mold_id)
    
    # If production line is being updated, validate it exists
    if composition_line.production_line_id is not None:
        production_line = db.query(ProductionLine).get(composition_line.production_line_id)
        if not production_line:
            raise HTTPException(status_code=404, detail="Production line not found")
    
    # Update composition line fields (excluding machines)
    composition_line_data = composition_line.model_dump(exclude={'machines'}, exclude_none=True)
    for key, value in composition_line_data.items():
        setattr(db_composition_line, key, value)
    
    # If machines were provided, update the relationship
    if composition_line.machines is not None:
        # Validate that at least one machine was provided
        if len(composition_line.machines) == 0:
            raise HTTPException(
                status_code=400,
                detail="A composition line must have at least one machine"
            )
        
        # Check if all machines exist
        machine_ids = composition_line.machines
        existing_machines = db.query(Machine).filter(Machine.id.in_(machine_ids)).all()
        if len(existing_machines) != len(machine_ids):
            raise HTTPException(
                status_code=404,
                detail="One or more machines not found"
            )
        
        # Validate that ProductionTime exists for each machine
        for machine_id in machine_ids:
            production_time = db.query(ProductionTime).filter(
                ProductionTime.machine_id == machine_id,
                ProductionTime.product_id == final_product_id,
                ProductionTime.mold_id == final_mold_id
            ).first()
            if not production_time:
                raise HTTPException(
                    status_code=400,
                    detail=f"ProductionTime not found for machine {machine_id}, "
                           f"product {final_product_id}, and mold {final_mold_id}. "
                           "Please create a ProductionTime entry first."
                )
        
        # Remove old machines
        db.query(CompositionLineMachine).filter(
            CompositionLineMachine.composition_line_id == composition_line_id
        ).delete()
        
        # Add new machines (cycle time will be retrieved from ProductionTime)
        for machine_id in machine_ids:
            composition_line_machine = CompositionLineMachine(
                composition_line_id=db_composition_line.id,
                machine_id=machine_id
            )
            db.add(composition_line_machine)
    
    db.commit()
    db.refresh(db_composition_line)
    
    # Load relations for response
    db_composition_line = db.query(CompositionLine).options(
        joinedload(CompositionLine.production_line),
        joinedload(CompositionLine.mold),
        joinedload(CompositionLine.product),
        joinedload(CompositionLine.machines).joinedload(CompositionLineMachine.machine)
    ).filter(CompositionLine.id == composition_line_id).first()
    
    return CompositionLineResponse.from_orm_with_relations(db_composition_line, db)

@router.delete("/{composition_line_id}")
def delete_composition_line(composition_line_id: int, db: Session = Depends(get_db)):
    db_composition_line = db.query(CompositionLine).get(composition_line_id)
    if not db_composition_line:
        raise HTTPException(status_code=404, detail="Composition line not found")
    
    # Cascade delete will handle CompositionLineMachine
    db.delete(db_composition_line)
    db.commit()
    return {"message": "Composition line deleted successfully"}


