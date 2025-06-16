from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, time
import pandas as pd

from app.database import get_db
from app.models.client import Client
from app.models.product import Product
from app.models.job import Job

router = APIRouter(prefix="/upload")

@router.post("/jobs-xlsx")
async def upload_jobs_xlsx(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="O arquivo precisa ser .xlsx")

    try:
        contents = await file.read()
        df = pd.read_excel(contents, engine="openpyxl")

        jobs_criados = 0
        jobs_ignorados = 0

        for _, row in df.iterrows():
            cliente_nome = str(row.get("Cliente")).strip()
            produto_nome = str(row.get("Produto")).strip()
            demanda = row.get("Demanda")
            data_prometida = row.get("Data Prometida")
            horario_prometido = row.get("Horário Prometido")
            valor_unitario = row.get("Valor Unitário")

            if pd.isna(cliente_nome) or pd.isna(produto_nome) or pd.isna(demanda):
                jobs_ignorados += 1
                continue

            cliente = db.query(Client).filter(Client.name == cliente_nome).first()
            produto = db.query(Product).filter(Product.name == produto_nome).first()

            if not cliente or not produto:
                jobs_ignorados += 1
                continue

            # Converte a data
            if isinstance(data_prometida, str):
                data_prometida = datetime.strptime(data_prometida.strip(), "%d/%m/%Y")
            elif isinstance(data_prometida, pd.Timestamp):
                data_prometida = data_prometida.to_pydatetime().date()

            # Converte o horário
            if isinstance(horario_prometido, str):
                horario_prometido = datetime.strptime(horario_prometido.strip(), "%H:%M:%S").time()
            elif isinstance(horario_prometido, pd.Timestamp):
                horario_prometido = horario_prometido.to_pydatetime().time()
            elif isinstance(horario_prometido, datetime):
                horario_prometido = horario_prometido.time()
            elif isinstance(horario_prometido, (int, float)):
                horario_str = f"{int(horario_prometido):06d}"
                horario_prometido = time(
                    hour=int(horario_str[0:2]),
                    minute=int(horario_str[2:4]),
                    second=int(horario_str[4:6])
                )
            elif not isinstance(horario_prometido, time):
                raise HTTPException(status_code=400, detail="Formato de horário inválido")

            promised_datetime = datetime.combine(data_prometida, horario_prometido)

            job = Job(
                name=f"{cliente.name} - {produto.name}",
                promised_date=promised_datetime,
                demand=int(demanda),
                product_value=float(valor_unitario),
                fk_id_client=cliente.id,
                fk_id_product=produto.id
            )
            db.add(job)
            jobs_criados += 1

        db.commit()
        return {
            "message": "Upload finalizado.",
            "jobs_criados": jobs_criados,
            "jobs_ignorados": jobs_ignorados
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar o arquivo: {str(e)}")
