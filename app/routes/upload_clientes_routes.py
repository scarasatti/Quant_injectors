from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import pandas as pd

from app.database import get_db
from app.models.client import Client
from app.auth.auth_bearer import get_current_user
from app.models.user import User

router = APIRouter(prefix="/upload")

@router.post("/clientes-xlsx")
async def upload_clientes_xlsx(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="O arquivo precisa ser .xlsx")

    try:
        contents = await file.read()
        df = pd.read_excel(contents, engine="openpyxl")

        clientes_adicionados = 0
        clientes_ignorados = 0

        for _, row in df.iterrows():
            nome = str(row.get("nome")).strip()
            prioridade = row.get("prioridade")

            if not nome or pd.isna(prioridade):
                continue

            # Evita duplicatas
            if db.query(Client).filter(Client.name == nome).first():
                clientes_ignorados += 1
                continue

            cliente = Client(name=nome, priority=int(prioridade))
            db.add(cliente)
            clientes_adicionados += 1

        db.commit()
        return {
            "message": "Upload de clientes finalizado.",
            "clientes_adicionados": clientes_adicionados,
            "clientes_ignorados": clientes_ignorados
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar o arquivo: {str(e)}")
