from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, time
from typing import Optional
from app.database import get_db
from app.models.job import Job
from app.models.setup import Setup
from app.utils.save_schedule import save_solver_result_to_db
from pulp import LpMinimize, LpProblem, LpVariable, lpSum, LpBinary, value
import numpy as np
from app.auth.auth_bearer import get_current_user
from app.models.user import User

router = APIRouter(prefix="/sequenciamento", tags=["Sequenciamento"])

@router.post("/solve")
def solve_jobs(
    job_ids: list[int],
    sequencing_date: Optional[datetime] = Query(default=None),
    machine_availability: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    jobs_data = db.query(Job).filter(Job.id.in_(job_ids)).all()

    if len(jobs_data) != len(job_ids):
        raise HTTPException(status_code=404, detail="Algum job não foi encontrado")

    if sequencing_date is None:
        today = datetime.now().date()
        sequencing_date = datetime.combine(today, time(hour=12))
    else:
        sequencing_date = sequencing_date.replace(hour=12, minute=0, second=0, microsecond=0)

    jobs = list(range(len(jobs_data)))

    fator_maquina = 1 + ((100 - machine_availability) / 100)

    processing_time = []
    for job in jobs_data:
        scrap_percentual = float(job.product.scrap)
        fator_scrap = 1 + (scrap_percentual / 100)
        demanda_com_refugo = job.demand * fator_scrap
        tempo_horas_ajustado = (job.product.cycle * demanda_com_refugo) / 3600 * fator_maquina
        processing_time.append(round(tempo_horas_ajustado))

    due_time = [
        max(int((job.promised_date.replace(hour=12, minute=0, second=0, microsecond=0) - sequencing_date).total_seconds() // 3600), 0)
        for job in jobs_data
    ]

    weight = [job.client.priority for job in jobs_data]

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
                    setups_faltando.append(f"{job_i.product.name} ➜ {job_j.product.name}")

    if setups_faltando:
        raise HTTPException(status_code=400, detail={
            "erro": "Faltam setups cadastrados entre os seguintes produtos:",
            "faltantes": setups_faltando
        })

    model = LpProblem("Sequenciamento_Produção", LpMinimize)
    start = LpVariable.dicts("inicio", jobs, lowBound=0)
    early = LpVariable.dicts("antecipacao", jobs, lowBound=0)
    tardy = LpVariable.dicts("atraso", jobs, lowBound=0)
    x = LpVariable.dicts("setup", [(i, j) for i in jobs for j in jobs if i != j], cat=LpBinary)

    model += lpSum(weight[i] * tardy[i] for i in jobs)
    M = 10000

    for i in jobs:
        for j in jobs:
            if i != j:
                model += start[j] - start[i] - (M + setup_time[i][j]) * x[(i, j)] >= processing_time[i] - M
                model += x[(i, j)] + x[(j, i)] == 1

    for i in jobs:
        model += start[i] + processing_time[i] - tardy[i] + early[i] == due_time[i]

    model.solve()

    jobs_ordenados = sorted(jobs, key=lambda i: value(start[i]))
    resultado = []
    for posicao, i in enumerate(jobs_ordenados):
        resultado.append({
            "job_id": jobs_data[i].id,
            "ordem": posicao + 1,
            "inicio_h": round(value(start[i]), 2),
            "atraso_h": round(value(tardy[i]), 2),
            "produto": jobs_data[i].product.name,
            "cliente": jobs_data[i].client.name,
        })

    for job in jobs_data:
        job.processed = True
    db.commit()

    run_saved = save_solver_result_to_db(
        db=db,
        sequencing_date=sequencing_date,
        jobs_data=jobs_data,
        ordem_execucao=jobs_ordenados,
        start=start,
        tardy=tardy,
        processing_time=processing_time,
        setup_count=len(jobs) - 1,
        optimized_setups=sum(1 for (i, j) in x if i != j and value(x[(i, j)]) > 0.5)
    )

    return {
        "sequencing_date": sequencing_date.isoformat(),
        "sequencia": resultado,
        "objective_value": value(model.objective)
    }

