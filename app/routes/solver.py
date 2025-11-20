from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from datetime import datetime, time
from app.database import get_db
from app.models.job import Job
from app.models.setup import Setup
from app.utils.save_schedule import save_solver_result_to_db
from pulp import LpMinimize, LpProblem, LpVariable, lpSum, LpBinary, value, PULP_CBC_CMD
import numpy as np
from app.auth.auth_bearer import get_current_user
from app.models.user import User
from fastapi.responses import StreamingResponse
from app.utils.sse import register_user, unregister_user
from app.utils.sse import send_event, set_processing, is_processing
import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
import sys
from app.utils.email_sender import send_solver_report
import math
from algorithm.injetoras_modelo import build_and_solve as solve_injetoras_model
from app.schemas.injetoras_solver_schema import InjetorasRequest

router = APIRouter(prefix="/sequenciamento", tags=["Sequenciamento"])

@router.get("/stream")
async def stream_updates(user_id: str):
    queue = register_user(user_id)

    await send_event(user_id, is_processing(user_id))

    async def event_generator():
        try:
            while True:
                data = await queue.get()
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            unregister_user(user_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

def calculate_processing_time(job, sequencing_date: datetime, machine_availability: int, weight: list, job_index: int):
    # Cálculo do refugo
    scrap_percent = float(job.product.scrap)
    scrap_factor = 1 + scrap_percent / 100
    demand_with_scrap = job.demand * scrap_factor

    # fator de disponibilidade
    available_factor = (100 - machine_availability) / 100 + 1

    # Gargalo
    cycle_bottleneck = job.product.cycle * available_factor
    in_bottleneck_time = int(demand_with_scrap * cycle_bottleneck)
    post_bottleneck_time = job.product.bottleneck * available_factor
    total_bottleneck_time = int(demand_with_scrap * post_bottleneck_time)
    in_bottleneck_time_hours = math.ceil((in_bottleneck_time / 3600) * 10) / 10

    # Prazos
    promised_date = job.promised_date
    deadline = (promised_date - sequencing_date).total_seconds() / 3600
    deadline_in_bottleneck = math.ceil((deadline - total_bottleneck_time / 3600) * 10) / 10

    if deadline_in_bottleneck < 0:
        deadline_in_bottleneck = 0

    return round( in_bottleneck_time_hours, 2), round(deadline_in_bottleneck, 2), round(total_bottleneck_time/3600, 2)

@router.post("/solve")
async def solve_jobs(
    job_ids: list[int],
    sequencing_date: datetime = Query(..., description="Data e hora de início do sequenciamento"),
    machine_availability: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
):

    jobs_data = db.query(Job).filter(Job.id.in_(job_ids)).all()

    jobs = list(range(len(jobs_data)))

    if len(jobs_data) != len(job_ids):
        raise HTTPException(status_code=404, detail="Algum job não foi encontrado")

    weight = [job.client.priority for job in jobs_data]

    processing_time = []
    due_time = []
    post_bottleneck_times = []

    for i, job in enumerate(jobs_data):
        proc_time, real_due, bottleneck  = calculate_processing_time(
            job, sequencing_date, machine_availability, weight, i
        )
        processing_time.append(proc_time)
        due_time.append(real_due)
        post_bottleneck_times.append(bottleneck)

    weight = [job.client.priority for job in jobs_data]

    setup_time = np.zeros((len(jobs_data), len(jobs_data)), dtype=float)
    setups_faltando = []


    for i, job_i in enumerate(jobs_data):
        for j, job_j in enumerate(jobs_data):
            if i != j:
                setup = db.query(Setup).filter_by(
                    from_product=job_i.fk_id_product,
                    to_product=job_j.fk_id_product
                ).first()
                if setup:
                    setup_time[i][j] = math.ceil((setup.setup_time / 3600) * 10) / 10
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

    executor = ThreadPoolExecutor(max_workers=1)

    user_id = str(jobs_data[0].client.id)


    if is_processing(user_id):
        raise HTTPException(status_code=409, detail="Já existe um sequenciamento em andamento.")

    set_processing(user_id, True)
    await send_event(user_id, True)

    def resolver_modelo(modelo):
        solver = PULP_CBC_CMD(msg=True, timeLimit=3600)
        modelo.solve(solver)
        return modelo

    model = await asyncio.get_event_loop().run_in_executor(executor, resolver_modelo, model)

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
        db.delete(job)
    db.commit()

    run_saved = save_solver_result_to_db(
        db=db,
        sequencing_date=sequencing_date,
        jobs_data=jobs_data,
        ordem_execucao=jobs_ordenados,
        start=start,
        processing_time=processing_time,
        bottleneck_times=post_bottleneck_times,
        setup_count=len(jobs),
        optimized_setups=sum(
            1 for i in range(len(jobs_ordenados) - 1)
            if setup_time[jobs_ordenados[i]][jobs_ordenados[i + 1]] > 0
        )
    )

    await send_event(user_id, "Sequenciamento finalizado.")
    await send_event(user_id, False)
    set_processing(user_id, False)

    return {
        "sequencing_date": sequencing_date.isoformat(),
        "sequencia": resultado,
        "objective_value": value(model.objective)
    }


@router.post("/injetoras/solve")
async def solve_injetoras(request: InjetorasRequest | None = Body(default=None)):
    if request is None:
        request = InjetorasRequest()
    processing_map = (
        {(entry.job, entry.machine): entry.time for entry in request.processing}
        if request.processing else None
    )
    due_map = (
        {entry.job: entry.time for entry in request.due}
        if request.due else None
    )
    priority_map = (
        {entry.job: entry.value for entry in request.priority}
        if request.priority else None
    )
    setup_map = (
        {(entry.predecessor, entry.successor, entry.machine): entry.time for entry in request.setup}
        if request.setup else None
    )

    status, obj_value, sequences, completion, tardiness = solve_injetoras_model(
        jobs=request.jobs,
        machines=request.machines,
        processing=processing_map,
        due=due_map,
        priority=priority_map,
        setup3=setup_map,
        dummy=request.dummy,
    )

    completion_payload = [
        {
            "job": job,
            "machine": machine,
            "completion_time": time_value,
        }
        for (job, machine), time_value in completion.items()
    ]

    tardiness_payload = [
        {"job": job, "tardiness": tard}
        for job, tard in tardiness.items()
    ]

    return {
        "status": status,
        "objective_value": obj_value,
        "sequences": {str(machine): seq for machine, seq in sequences.items()},
        "completion": completion_payload,
        "tardiness": tardiness_payload,
    }
