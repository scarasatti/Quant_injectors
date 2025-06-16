from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, time
from typing import Optional
from app.database import get_db
from app.models.job import Job
from app.models.setup import Setup
import numpy as np

router = APIRouter(prefix="/sequenciamento", tags=["Sequenciamento"])

@router.post("/inputs-formatado")
def get_solver_inputs_formatado(
    job_ids: list[int],
    sequencing_date: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db)
):
    jobs_data = db.query(Job).filter(Job.id.in_(job_ids)).all()

    if len(jobs_data) != len(job_ids):
        raise HTTPException(status_code=404, detail="Algum job não foi encontrado")

    # ✅ Ajusta sequencing_date para meio-dia
    if sequencing_date is None:
        today = datetime.now().date()
        sequencing_date = datetime.combine(today, time(hour=12))
    else:
        sequencing_date = sequencing_date.replace(hour=12, minute=0, second=0, microsecond=0)

    produtos = [job.product.name for job in jobs_data]
    clientes = [job.client.name for job in jobs_data]

    # ✅ TEMPO EM HORAS (ARREDONDADO)
    processing_time = [
        round((job.product.cycle * job.demand) / 3600)
        for job in jobs_data
    ]

    # ✅ PRAZO EM HORAS entre meio-dia das datas
    due_time = [
        max(int((job.promised_date.replace(hour=12, minute=0, second=0, microsecond=0) - sequencing_date).total_seconds() // 3600), 0)
        for job in jobs_data
    ]

    weight = [job.client.priority for job in jobs_data]

    # Matriz de setup
    setup_time = np.zeros((len(jobs_data), len(jobs_data)), dtype=int)
    setups_faltando = []

    for i, job_i in enumerate(jobs_data):
        for j, job_j in enumerate(jobs_data):
            if i != j:
                setup = db.query(Setup).filter_by(
                    produto_de=job_i.fk_id_product,
                    produto_para=job_j.fk_id_product
                ).first()
                if setup:
                    setup_time[i][j] = setup.tempo_setup
                else:
                    setups_faltando.append(
                        f"{job_i.product.name} ➜ {job_j.product.name}"
                    )

    setup_time_str = "setup_time = np.array([\n"
    for linha in setup_time.tolist():
        setup_time_str += "    " + str(linha) + ",\n"
    setup_time_str += "])"

    return {
        "sequencing_date": sequencing_date.isoformat(),
        "jobs": [job.id for job in jobs_data],
        "produtos": produtos,
        "clientes": clientes,
        "processing_time": processing_time,
        "due_time": due_time,
        "weight": weight,
        "setup_time_numpy": setup_time_str,
        "setups_faltando": setups_faltando
    }