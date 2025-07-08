from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from decimal import Decimal
import pandas as pd

from app.database import get_db
from app.models.product import Product
from app.models.setup import Setup
from app.auth.auth_bearer import get_current_user

router = APIRouter(prefix="/upload")

@router.post("/products-xlsx")
async def upload_products_xlsx(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="The file must be a .xlsx format.")

    try:
        contents = await file.read()
        df = pd.read_excel(contents, engine="openpyxl")

        # Normalize column names (strip leading/trailing whitespace)
        df.columns = df.columns.str.strip()

        added_products = 0
        ignored_products = 0

        for _, row in df.iterrows():
            name = str(row.get("produto")).strip()
            cycle = row.get("ciclo")
            bottleneck = row.get("Tempo de Produção Pós Gargalo")
            scrap = row.get("refugo")

            if not name or pd.isna(cycle) or pd.isna(bottleneck):
                continue

            existing = db.query(Product).filter(Product.name == name).first()
            if existing:
                ignored_products += 1
                continue

            product = Product(
                name=name,
                cycle=int(cycle),
                bottleneck=int(bottleneck),
                scrap=Decimal(scrap) if not pd.isna(scrap) else Decimal(0)
            )
            db.add(product)
            db.commit()
            db.refresh(product)
            added_products += 1

            # Create setups for the new product
            all_others = db.query(Product).filter(Product.id != product.id).all()

            # Self-setup
            db.add(Setup(from_product=product.id, to_product=product.id, setup_time=0))

            for other in all_others:
                db.add(Setup(from_product=product.id, to_product=other.id, setup_time=0))
                db.add(Setup(from_product=other.id, to_product=product.id, setup_time=0))

            db.commit()

        return {
            "message": "Upload completed.",
            "added_products": added_products,
            "ignored_products": ignored_products
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
