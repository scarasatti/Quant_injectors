from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models.product import Product
from app.models.mold_product import MoldProduct
from app.models.product_composition import ProductComposition
from app.schemas.product_schema import ProductCreate, ProductUpdate, ProductResponse
from app.auth.auth_bearer import get_current_user
from app.models.user import User
from app.models.job import Job
router = APIRouter(prefix="/products", tags=["Products"])

@router.post("", response_model=ProductResponse)
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    
    db_product = Product(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)

    # Note: Setups are no longer created automatically when a product is created.
    # Setups are now created between ProductionLines (mold + product combinations) and require a machine_id.
    # Setups should be created when ProductionLines are created or via setup matrix upload.
    
    # Load molds and compositions for response
    db_product = db.query(Product).options(
        joinedload(Product.molds).joinedload(MoldProduct.mold),
        joinedload(Product.compositions).joinedload(ProductComposition.materia_prima)
    ).filter(Product.id == db_product.id).first()

    return ProductResponse.from_orm_with_relations(db_product)

@router.get("/", response_model=list[ProductResponse])
def list_products(db: Session = Depends(get_db)):
    products = db.query(Product).options(
        joinedload(Product.molds).joinedload(MoldProduct.mold),
        joinedload(Product.compositions).joinedload(ProductComposition.materia_prima)
    ).all()
    return [ProductResponse.from_orm_with_relations(product) for product in products]

@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).options(
        joinedload(Product.molds).joinedload(MoldProduct.mold),
        joinedload(Product.compositions).joinedload(ProductComposition.materia_prima)
    ).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductResponse.from_orm_with_relations(product)

@router.put("/{product_id}", response_model=ProductResponse)
def update_product(product_id: int, product: ProductUpdate, db: Session = Depends(get_db)):
    db_product = db.query(Product).get(product_id)
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    for key, value in product.model_dump().items():
        setattr(db_product, key, value)
    db.commit()
    
    # Load molds and compositions for response
    db_product = db.query(Product).options(
        joinedload(Product.molds).joinedload(MoldProduct.mold),
        joinedload(Product.compositions).joinedload(ProductComposition.materia_prima)
    ).filter(Product.id == product_id).first()
    
    return ProductResponse.from_orm_with_relations(db_product)

@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    """
    Delete a product. Only ProductComposition will be deleted automatically (cascade).
    Other relationships (Setup, Job, MoldProduct) will remain and may cause foreign key errors.
    Consider deleting related data manually if needed.
    """
    db_product = db.query(Product).get(product_id)
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Cascade delete will handle:
    # - ProductComposition (via relationship cascade="all, delete-orphan" and ForeignKey ondelete="CASCADE")
    
    # Note: Setup, Job, and MoldProduct will NOT be deleted automatically
    # If there are references to this product in these tables, the delete may fail
    
    db.delete(db_product)
    db.commit()

    return {"message": "Product and its compositions deleted successfully"}

