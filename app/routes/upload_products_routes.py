from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import pandas as pd
from app.database import get_db
from app.models.product import Product

router = APIRouter(prefix="/upload", tags=["Upload products"])

@router.post("/products-xlsx")
async def upload_products_xlsx(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="O arquivo precisa ser .xlsx")

    try:
        contents = await file.read()
        df = pd.read_excel(contents, engine="openpyxl")

        produtos_adicionados = 0
        produtos_ignorados = 0

        for _, row in df.iterrows():
            nome = str(row.get("produto")).strip()
            ciclo = row.get("ciclo")

            if not nome or pd.isna(ciclo):
                continue

            # Verifica se o produto já existe
            if db.query(Product).filter(Product.name == nome).first():
                produtos_ignorados += 1
                continue

            produto = Product(name=nome, ciclo=int(ciclo))
            db.add(produto)
            produtos_adicionados += 1

        db.commit()
        return {
            "message": "Upload finalizado.",
            "produtos_adicionados": produtos_adicionados,
            "produtos_ignorados": produtos_ignorados
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar o arquivo: {str(e)}")
