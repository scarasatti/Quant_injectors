from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.product import Product
from app.schemas.product_schema import ProductCreate, ProductUpdate, ProductResponse
from app.auth.auth_bearer import get_current_user
from app.models.user import User
from app.models.setup import Setup
from app.models.job import Job
router = APIRouter(prefix="/products", tags=["Products"])

@router.post("", response_model=ProductResponse)
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    
    db_product = Product(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)

    existing_products = db.query(Product).filter(Product.id != db_product.id).all()

    if existing_products:
        for other in existing_products:

            setup_1 = Setup(from_product=db_product.id, to_product=other.id, setup_time=0)
            db.add(setup_1)

            setup_2 = Setup(from_product=other.id, to_product=db_product.id, setup_time=0)
            db.add(setup_2)

        db.commit()

    return db_product

@router.get("/", response_model=list[ProductResponse])
def list_products(db: Session = Depends(get_db)):
    return db.query(Product).all()

@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@router.put("/{product_id}", response_model=ProductResponse)
def update_product(product_id: int, product: ProductUpdate, db: Session = Depends(get_db)):
    db_product = db.query(Product).get(product_id)
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    for key, value in product.model_dump().items():
        setattr(db_product, key, value)
    db.commit()
    db.refresh(db_product)
    return db_product

@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    # Busca o produto
    db_product = db.query(Product).get(product_id)
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Deleta setups relacionados
    db.query(Setup).filter(
        (Setup.from_product == product_id) | (Setup.to_product == product_id)
    ).delete(synchronize_session=False)

    # Deleta jobs relacionados (opcional, depende da regra de negócio)
    db.query(Job).filter(Job.fk_id_product == product_id).delete(synchronize_session=False)

    # Deleta o produto
    db.delete(db_product)
    db.commit()

    return {"message": "Product and related setups deleted"}
