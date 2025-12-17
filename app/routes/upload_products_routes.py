from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import pandas as pd

from app.database import get_db
from app.models.product import Product
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

            if not name:
                continue

            existing = db.query(Product).filter(Product.name == name).first()
            if existing:
                ignored_products += 1
                continue

            product = Product(name=name)
            db.add(product)
            db.commit()
            db.refresh(product)
            added_products += 1

            # Note: Setups are no longer created automatically when a product is created.
            # Setups are now created between ProductionLines (mold + product combinations) and require a machine_id.
            # Setups should be created when ProductionLines are created or via setup matrix upload.

        return {
            "message": "Upload completed.",
            "added_products": added_products,
            "ignored_products": ignored_products
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
