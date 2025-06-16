from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from decimal import Decimal
import pandas as pd

from app.database import get_db
from app.models.product import Product

router = APIRouter(prefix="/upload")

@router.post("/products-xlsx")
async def upload_products_xlsx(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="O arquivo precisa ser .xlsx")

    try:
        contents = await file.read()
        df = pd.read_excel(contents, engine="openpyxl")

        # Normaliza nomes de colunas (remove espaços invisíveis)
        df.columns = df.columns.str.strip()

        produtos_adicionados = 0
        produtos_ignorados = 0

        for _, row in df.iterrows():
            nome = str(row.get("produto")).strip()
            ciclo = row.get("ciclo")
            gargalo = row.get("Tempo de Produção Pós Gargalo")
            refugo = row.get("refugo")

            # Ignora linhas incompletas
            if not nome or pd.isna(ciclo) or pd.isna(gargalo):
                continue

            # Verifica se já existe um produto com o mesmo nome
            produto_existente = db.query(Product).filter(Product.name == nome).first()

            if produto_existente:
                produtos_ignorados += 1
                continue

            # Cria novo produto
            produto = Product(
                name=nome,
                cycle=int(ciclo),
                bottleneck=int(gargalo),
                scrap=Decimal(refugo) if not pd.isna(refugo) else Decimal(0)
            )

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
