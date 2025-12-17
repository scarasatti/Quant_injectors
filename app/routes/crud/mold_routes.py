from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models.mold import Mold
from app.models.product import Product
from app.models.mold_product import MoldProduct
from app.schemas.mold_schema import MoldCreate, MoldUpdate, MoldResponse

router = APIRouter(prefix="/molds", tags=["Molds"])

@router.post("", response_model=MoldResponse)
def create_mold(mold: MoldCreate, db: Session = Depends(get_db)):
    # Validate that open_cavities is not greater than total_cavities
    if mold.open_cavities > mold.total_cavities:
        raise HTTPException(
            status_code=400,
            detail="Open cavities cannot be greater than total cavities"
        )
    
    # Validate products if provided
    if mold.products:
        product_ids = mold.products
        existing_products = db.query(Product).filter(Product.id.in_(product_ids)).all()
        if len(existing_products) != len(product_ids):
            raise HTTPException(
                status_code=404,
                detail="One or more products not found"
            )
    
    # Create the mold (without products yet)
    mold_data = mold.model_dump(exclude={'products'})
    db_mold = Mold(**mold_data)
    db.add(db_mold)
    db.flush()  # To get the ID
    
    # Associate products
    if mold.products:
        for product_id in mold.products:
            mold_product = MoldProduct(
                mold_id=db_mold.id,
                product_id=product_id
            )
            db.add(mold_product)
    
    db.commit()
    db.refresh(db_mold)
    
    # Load products for response
    db_mold = db.query(Mold).options(
        joinedload(Mold.products).joinedload(MoldProduct.product)
    ).filter(Mold.id == db_mold.id).first()
    
    return MoldResponse.from_orm_with_products(db_mold)

@router.get("/", response_model=list[MoldResponse])
def list_molds(db: Session = Depends(get_db)):
    molds = db.query(Mold).options(
        joinedload(Mold.products).joinedload(MoldProduct.product)
    ).all()
    return [MoldResponse.from_orm_with_products(mold) for mold in molds]

@router.get("/{mold_id}", response_model=MoldResponse)
def get_mold(mold_id: int, db: Session = Depends(get_db)):
    mold = db.query(Mold).options(
        joinedload(Mold.products).joinedload(MoldProduct.product)
    ).filter(Mold.id == mold_id).first()
    if not mold:
        raise HTTPException(status_code=404, detail="Mold not found")
    return MoldResponse.from_orm_with_products(mold)

@router.put("/{mold_id}", response_model=MoldResponse)
def update_mold(mold_id: int, mold: MoldUpdate, db: Session = Depends(get_db)):
    db_mold = db.query(Mold).get(mold_id)
    if not db_mold:
        raise HTTPException(status_code=404, detail="Mold not found")
    
    # Validate that open_cavities is not greater than total_cavities
    if mold.open_cavities > mold.total_cavities:
        raise HTTPException(
            status_code=400,
            detail="Open cavities cannot be greater than total cavities"
        )
    
    # Update mold fields (excluding products)
    mold_data = mold.model_dump(exclude={'products'}, exclude_none=True)
    for key, value in mold_data.items():
        setattr(db_mold, key, value)
    
    # If products were provided, update the relationship
    if mold.products is not None:
        # Remove old products
        db.query(MoldProduct).filter(
            MoldProduct.mold_id == mold_id
        ).delete()
        
        # Validate products if provided
        if len(mold.products) > 0:
            product_ids = mold.products
            existing_products = db.query(Product).filter(Product.id.in_(product_ids)).all()
            if len(existing_products) != len(product_ids):
                raise HTTPException(
                    status_code=404,
                    detail="One or more products not found"
                )
            
            # Add new products
            for product_id in mold.products:
                mold_product = MoldProduct(
                    mold_id=db_mold.id,
                    product_id=product_id
                )
                db.add(mold_product)
    
    db.commit()
    db.refresh(db_mold)
    
    # Load products for response
    db_mold = db.query(Mold).options(
        joinedload(Mold.products).joinedload(MoldProduct.product)
    ).filter(Mold.id == mold_id).first()
    
    return MoldResponse.from_orm_with_products(db_mold)

@router.delete("/{mold_id}")
def delete_mold(mold_id: int, db: Session = Depends(get_db)):
    db_mold = db.query(Mold).get(mold_id)
    if not db_mold:
        raise HTTPException(status_code=404, detail="Mold not found")
    db.delete(db_mold)
    db.commit()
    return {"message": "Mold deleted successfully"}

