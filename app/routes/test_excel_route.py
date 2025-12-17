from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Depends
from fastapi.responses import FileResponse
from datetime import datetime
import os
import json
import pandas as pd
from io import BytesIO
from sqlalchemy.orm import Session

from app.database import get_db
from algorithm.injection.excel_reader import process_excel_file
from algorithm.injection.calculate_processing_time import calculate_processing_time

router = APIRouter(prefix="/test", tags=["Test"])


@router.post("/excel-read")
async def test_read_excel(
    file: UploadFile = File(..., description="Arquivo XLSX com os dados"),
    sequencing_date: datetime = Form(
        ..., description="Data e hora de início do sequenciamento (formato: YYYY-MM-DDTHH:MM:SS)"
    ),
    default_billing_deadline_time: str = Form(
        default="16:59:00", description="Hora limite padrão do faturamento (formato: HH:MM:SS)"
    ),
    next_saturday_is_working: bool = Form(
        default=False, description="Indica se o próximo sábado é dia útil"
    ),
    machine_states_json: str = Form(
        default="[]", description="JSON com estados das máquinas (formato: array de objetos)"
    ),
    programmed_stops_json: str = Form(
        default="[]", description="JSON com paradas programadas (formato: array de objetos)"
    ),
    db: Session = Depends(get_db),
):
    """Rota de teste para ler uma planilha Excel, rodar `calculate_processing_time`
    (incluindo deadlines considerando turnos) e gerar logs detalhados.
    """

    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="O arquivo precisa ser .xlsx")

    try:
        contents = await file.read()

        # Processar machine_states se fornecido (apenas para log)
        machine_states = []
        if machine_states_json and machine_states_json != "[]":
            try:
                machine_states = json.loads(machine_states_json)
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Erro ao parsear JSON de machine_states: {str(e)}",
                )

        # Processar programmed_stops se fornecido (apenas para log)
        programmed_stops = []
        if programmed_stops_json and programmed_stops_json != "[]":
            try:
                programmed_stops = json.loads(programmed_stops_json)
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Erro ao parsear JSON de programmed_stops: {str(e)}",
                )

        # Ler Excel em DataFrame
        df = pd.read_excel(BytesIO(contents), engine="openpyxl")
        df.columns = df.columns.str.strip()
        excel_rows = df.to_dict("records")

        # Calcular tempos / prazos / gargalos
        processing_result = calculate_processing_time(
            excel_rows=excel_rows,
            sequencing_date=sequencing_date,
            next_saturday_is_working=next_saturday_is_working,
            db=db,
            machine_states=machine_states or None,
            programmed_stops=programmed_stops or None,
        )

        # Gerar logs completos (planilha + machine_states + programmed_stops + cálculos)
        result = await process_excel_file(
            file_contents=contents,
            filename=file.filename,
            sequencing_date=sequencing_date,
            default_billing_deadline_time=default_billing_deadline_time,
            next_saturday_is_working=next_saturday_is_working,
            machine_states=machine_states or None,
            programmed_stops=programmed_stops or None,
            processing_calculation=processing_result,
        )

        # Resumo de quantos itens extras chegaram
        if machine_states:
            result["machine_states"] = {"total_recebidos": len(machine_states)}
        if programmed_stops:
            result["programmed_stops"] = {"total_recebidos": len(programmed_stops)}

        # Anexar o resumo dos cálculos ao retorno
        result["processing_calculation"] = {
            "total_jobs": processing_result["total_jobs"],
            "total_lines": processing_result["total_lines"],
            "errors": processing_result["errors"],
            "jobs_by_line": processing_result["jobs_by_line"],
        }

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar arquivo: {str(e)}")


@router.get("/logs/list")
async def list_logs():
    """Lista todos os logs gerados em `logs/` (excel_read_*.json / state_machines_*.json)."""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        return {"logs": []}

    logs = []
    for filename in os.listdir(log_dir):
        if (filename.startswith("excel_read_") or filename.startswith("state_machines_")) and filename.endswith(
            ".json"
        ):
            filepath = os.path.join(log_dir, filename)
            file_stat = os.stat(filepath)
            log_type = "excel_read" if filename.startswith("excel_read_") else "state_machines"
            logs.append(
                {
                    "arquivo": filename,
                    "tipo": log_type,
                    "tamanho_bytes": file_stat.st_size,
                    "criado_em": datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                }
            )

    logs.sort(key=lambda x: x["criado_em"], reverse=True)
    return {"logs": logs}


@router.get("/logs/download/{filename}")
async def download_log(filename: str):
    """Baixa um arquivo de log específico (JSON ou TXT)."""
    log_dir = "logs"
    filepath = os.path.join(log_dir, filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Log não encontrado")

    return FileResponse(
        filepath,
        media_type="application/json" if filename.endswith(".json") else "text/plain",
        filename=filename,
    )
