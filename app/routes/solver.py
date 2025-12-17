from fastapi import APIRouter, Depends, HTTPException, Query, Body, File, UploadFile, Form
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
from datetime import datetime, time, date
from app.database import get_db
from app.models.job import Job
from app.models.setup import Setup
from app.models.composition_line import CompositionLine
from app.models.production_line import ProductionLine
from app.models.mold import Mold
from app.models.product import Product
from app.models.client import Client
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
from io import StringIO, BytesIO
import sys
import json
import pandas as pd
from app.utils.email_sender import send_solver_report
import math
import logging
from algorithm.injection import solve_injection_scheduling
from algorithm.injection.job_calculator import calculate_injection_jobs_data
from algorithm.injection.programmed_stops import ProgrammedStop, create_stop_jobs, merge_stop_jobs_with_normal_jobs
from app.schemas.injetoras_solver_schema import (
    InjetorasRequest,
    InjetorasFromJobsRequest,
    MachineStateEntry,
    ProgrammedStopRequest
)

logger = logging.getLogger("uvicorn.error")

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
    # TODO: Product model now only has id and name. 
    # cycle, bottleneck, and scrap fields were removed.
    # These values need to come from another source (e.g., Mold, ProductionLine, or separate ProductSpecs model)
    
    # Cálculo do refugo
    # scrap_percent = float(job.product.scrap)  # REMOVED: Product.scrap no longer exists
    scrap_percent = 0  # Default value - needs to be updated with correct source
    scrap_factor = 1 + scrap_percent / 100
    demand_with_scrap = job.demand * scrap_factor

    # fator de disponibilidade
    available_factor = (100 - machine_availability) / 100 + 1

    # Gargalo
    # cycle_bottleneck = job.product.cycle * available_factor  # REMOVED: Product.cycle no longer exists
    cycle_bottleneck = 0 * available_factor  # Default value - needs to be updated with correct source
    in_bottleneck_time = int(demand_with_scrap * cycle_bottleneck)
    # post_bottleneck_time = job.product.bottleneck * available_factor  # REMOVED: Product.bottleneck no longer exists
    post_bottleneck_time = 0 * available_factor  # Default value - needs to be updated with correct source
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

    # Para usar o novo formato de setup, precisamos mapear jobs para production_lines
    # Por enquanto, vamos buscar a primeira production_line que corresponde ao produto de cada job
    # TODO: Idealmente, o Job deveria ter um campo composition_line_id ou permitir especificar
    from app.models.composition_line import CompositionLine
    
    job_to_composition_line = {}
    for job in jobs_data:
        # Busca a primeira composition_line que tem o produto do job
        # Assumindo que o job tem um produto, precisamos encontrar uma composition_line com esse produto
        composition_line = db.query(CompositionLine).filter_by(
            product_id=job.fk_id_product
        ).first()
        if not composition_line:
            raise HTTPException(
                status_code=404, 
                detail=f"Nenhuma composition line encontrada para o produto {job.product.name}"
            )
        job_to_composition_line[job.id] = composition_line.id
    
    setup_time = np.zeros((len(jobs_data), len(jobs_data)), dtype=float)
    setups_faltando = []

    for i, job_i in enumerate(jobs_data):
        for j, job_j in enumerate(jobs_data):
            if i != j:
                from_cl_id = job_to_composition_line[job_i.id]
                to_cl_id = job_to_composition_line[job_j.id]
                
                setup = db.query(Setup).filter_by(
                    from_composition_line_id=from_cl_id,
                    to_composition_line_id=to_cl_id
                ).first()
                if setup:
                    setup_time[i][j] = math.ceil((setup.setup_time / 3600) * 10) / 10
                else:
                    from_cl = db.query(CompositionLine).options(
                        joinedload(CompositionLine.mold),
                        joinedload(CompositionLine.product)
                    ).get(from_cl_id)
                    to_cl = db.query(CompositionLine).options(
                        joinedload(CompositionLine.mold),
                        joinedload(CompositionLine.product)
                    ).get(to_cl_id)
                    from_label = f"M{from_cl.mold_id}-{from_cl.product.name}" if from_cl else f"Produto {job_i.product.name}"
                    to_label = f"M{to_cl.mold_id}-{to_cl.product.name}" if to_cl else f"Produto {job_j.product.name}"
                    setups_faltando.append(f"{from_label} ➜ {to_label}")

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

    status, obj_value, sequences, completion, tardiness = solve_injection_scheduling(
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


def _log_injection_solver_input(
    context: str,
    line_id: int | None,
    jobs: list[int],
    machines: list[int],
    processing: dict[tuple[int, int], float],
    due: dict[int, float],
    priority: dict[int, float],
) -> None:
    """
    Loga uma tabela com os dados que vão entrar no solver de injetoras.
    
    Formato aproximado ao da planilha:
    - Jobs
    - Tempo de Produção (h) por máquina
    - Prioridade
    - Prazo nas injetoras (h)
    """
    
    # Cabeçalho exatamente no formato desejado
    header_cols = ["Jobs"]
    for idx, _ in enumerate(machines, start=1):
        header_cols.append(f"Tempo de Produção (h)\tMaq {idx}")
    header_cols.extend(["Prioridade", "Prazo nas injetoras (h)"])
    
    header = "\t".join(header_cols)
    
    logger.info("==== Injetoras Solver Input ====")
    logger.info("Contexto: %s", context)
    if line_id is not None:
        logger.info("Linha de produção: %s", line_id)
    logger.info(header)
    
    print("==== Injetoras Solver Input ====")
    print(f"Contexto:\t{context}")
    if line_id is not None:
        print(f"Linha de produção:\t{line_id}")
    print(header)
    
    for j in jobs:
        row = [str(j)]
        for m in machines:
            val = processing.get((j, m), 0.0)
            row.append(f"{val:.1f}")
        prio = priority.get(j, 0.0)
        due_h = due.get(j, 0.0)
        row.append(f"{prio:.0f}")
        row.append(f"{due_h:.1f}")
        
        line_str = "\t".join(row)
        logger.info(line_str)
        print(line_str)
    
    logger.info("==== Fim do input ====")
    print("==== Fim do input ====")


@router.post("/injetoras/solve-from-jobs")
async def solve_injetoras_from_jobs(
    request: InjetorasFromJobsRequest,
    db: Session = Depends(get_db),
):
    """
    Roda o solver de injetoras a partir de jobs do banco de dados,
    considerando também o estado atual das máquinas (jobs em execução).
    """
    
    # Buscar jobs do banco
    jobs_data = db.query(Job).filter(Job.id.in_(request.job_ids)).all()
    
    if len(jobs_data) != len(request.job_ids):
        raise HTTPException(
            status_code=404,
            detail="Algum job não foi encontrado no banco de dados"
        )
    
    # Converter machine_states em ProgrammedStop (jobs em execução)
    programmed_stops = []
    if request.machine_states:
        for state in request.machine_states:
            if state.used and not state.completed:
                # Criar um ProgrammedStop representando o job em execução
                # O tempo restante já está em minutos, então dividimos por 60 para horas
                remaining_hours = (state.remaining_injection_hours + state.remaining_post_injection_hours) / 60
                
                # Para jobs em execução, o prazo é 0 (já começou)
                # Vamos criar um stop que começa no sequencing_date e termina após remaining_hours
                from datetime import timedelta
                start_dt = request.sequencing_date
                end_dt = start_dt + timedelta(hours=remaining_hours)
                
                stop = ProgrammedStop(
                    reason=f"Job em execução: {state.order_number or 'N/A'}",
                    start_datetime=start_dt,
                    end_datetime=end_dt,
                    machine_id=state.machine_id
                )
                programmed_stops.append(stop)
    
    # Calcular dados dos jobs usando job_calculator
    jobs_data_dict = calculate_injection_jobs_data(
        jobs_data=jobs_data,
        sequencing_date=request.sequencing_date,
        machine_availability=None,  # Usa a disponibilidade individual de cada máquina
        db=db,
        programmed_stops=programmed_stops if programmed_stops else None,
    )
    
    if jobs_data_dict.get("errors"):
        raise HTTPException(
            status_code=400,
            detail={"erro": "Erros encontrados ao calcular dados dos jobs", "detalhes": jobs_data_dict["errors"]}
        )
    
    # Log do input
    _log_injection_solver_input(
        context="solve-from-jobs",
        line_id=None,
        jobs=jobs_data_dict["jobs"],
        machines=jobs_data_dict["machines"],
        processing=jobs_data_dict["processing"],
        due=jobs_data_dict["due"],
        priority=jobs_data_dict["priority"],
    )
    
    # Rodar o solver
    status, obj_value, sequences, completion, tardiness = solve_injection_scheduling(
        jobs=jobs_data_dict["jobs"],
        machines=jobs_data_dict["machines"],
        processing=jobs_data_dict["processing"],
        due=jobs_data_dict["due"],
        priority=jobs_data_dict["priority"],
        setup3=jobs_data_dict["setup3"],
        dummy=0,  # Job 0 já está incluído no job_calculator
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


@router.post("/injetoras/create-stop-job")
async def create_stop_job_route(
    request: ProgrammedStopRequest,
    db: Session = Depends(get_db),
):
    """
    Cria um job falso representando uma parada programada (manutenção, etc.).
    
    A resposta já vem no mesmo formato usado pelo solver de injetoras (processing, due, priority).
    """
    
    # Combinar data e hora de início/fim
    start_datetime = datetime.combine(request.start_date, request.start_time)
    end_datetime = datetime.combine(request.end_date, request.end_time)
    
    # Criar ProgrammedStop
    stop = ProgrammedStop(
        reason=request.reason,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        machine_id=request.machine_id
    )
    
    # Criar dados do job de parada
    stop_jobs_data = create_stop_jobs(
        stops=[stop],
        sequencing_date=request.sequencing_date,
        machines=request.machines,
        db=db,
        reference_date=request.sequencing_date.date()
    )
    
    return {
        "stop_jobs": stop_jobs_data["stop_jobs"],
        "processing": stop_jobs_data["processing"],
        "due": stop_jobs_data["due"],
        "priority": stop_jobs_data["priority"],
        "stop_info": stop_jobs_data["stop_info"],
    }


@router.post("/injetoras/solve-from-xlsx")
async def solve_injetoras_from_xlsx(
    file: UploadFile = File(..., description="Arquivo XLSX com os jobs"),
    sequencing_date: datetime = Form(..., description="Data e hora de início do sequenciamento"),
    default_billing_deadline_time: time = Form(..., description="Hora limite padrão do faturamento (ex: 16:59)"),
    next_saturday_is_working: bool = Form(..., description="Se o próximo sábado é dia de trabalho"),
    machine_states_json: str = Form(default="[]", description="JSON com estados das máquinas"),
    programmed_stops_json: str = Form(default="[]", description="JSON com paradas programadas"),
    db: Session = Depends(get_db),
):
    """
    Roda o solver de injetoras a partir de um arquivo XLSX com jobs.
    
    O arquivo deve conter as colunas:
    - Linha (production_line_id)
    - Código do Molde (mold_id ou nome do molde, ex: M1, M2)
    - Produto (product_id ou nome do produto)
    - Demanda do Pedido (quantidade, pode ter separador de milhar: 100.800)
    - Data Limite de Faturamento (formato DD/MM/YYYY)
    - Horário Limite de Faturamento (formato HH:MM)
    - Cliente (nome do cliente)
    - Valor Unitário (R$/por unidade) (formato R$ 0,41 - com vírgula como decimal)
    """
    
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="O arquivo precisa ser .xlsx")
    
    try:
        contents = await file.read()
        df = pd.read_excel(BytesIO(contents), engine="openpyxl")
        
        # Normalizar nomes das colunas (remover espaços extras)
        df.columns = df.columns.str.strip()
        
        # Log para debug
        logger.info(f"Colunas do Excel: {list(df.columns)}")
        print(f"DEBUG - Colunas do Excel: {list(df.columns)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler arquivo XLSX: {str(e)}")
    
    # Parse JSON de machine_states e programmed_stops
    try:
        machine_states_data = json.loads(machine_states_json) if machine_states_json else []
        programmed_stops_data = json.loads(programmed_stops_json) if programmed_stops_json else []
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Erro ao parsear JSON: {str(e)}")
    
    # Normalizar machine_states (pode vir como lista de listas ou lista de dicts)
    machine_states = []
    if machine_states_data:
        for item in machine_states_data:
            if isinstance(item, dict):
                machine_states.append(MachineStateEntry(**item))
            elif isinstance(item, list) and len(item) > 0:
                # Se for lista de listas, converter primeiro item para dict
                if isinstance(item[0], dict):
                    machine_states.append(MachineStateEntry(**item[0]))
    
    # Normalizar programmed_stops
    programmed_stops = []
    if programmed_stops_data:
        for item in programmed_stops_data:
            if isinstance(item, dict):
                programmed_stops.append(ProgrammedStopRequest(**item))
    
    # Agrupar todos os jobs - a linha será descoberta pela CompositionLine (molde + produto)
    all_jobs = []
    for _, row in df.iterrows():
        all_jobs.append(row)
    
    # Processar todos os jobs - agrupar por linha de produção descoberta
    results = {}
    jobs_by_line_discovered = {}
    
    def process_all_jobs(jobs_list: list):
        # Criar jobs temporários
        jobs_data = []
        
        for idx, row in enumerate(jobs_list):
            # Debug: ver o que tem na linha
            logger.info(f"DEBUG linha {idx}: {dict(row)}")
            print(f"DEBUG linha {idx}: Colunas disponíveis: {list(row.index)}")
            print(f"DEBUG linha {idx}: Valores: {dict(row)}")
            
            # Buscar molde - tentar múltiplas variações do nome da coluna
            mold_value_raw = None
            for col_name in ["Código do Molde", "Código Do Molde", "Codigo do Molde", "CODIGO DO MOLDE", "código do molde", "Molde", "molde", "MOLDE", "mold_id", "Mold", "MOLDE_ID"]:
                if col_name in row.index:
                    mold_value_raw = row[col_name]
                    print(f"DEBUG: Encontrou coluna '{col_name}' com valor: {mold_value_raw} (tipo: {type(mold_value_raw)})")
                    break
            
            if mold_value_raw is None or (pd.isna(mold_value_raw) if hasattr(pd, 'isna') else (mold_value_raw is None or str(mold_value_raw).strip() == '')):
                available_cols = list(row.index)
                raise HTTPException(
                    status_code=400, 
                    detail=f"Valor de Molde está vazio na linha {idx+1} do Excel. Colunas disponíveis: {available_cols}"
                )
            
            # Normalizar o valor - tratar NaN do pandas
            if pd.isna(mold_value_raw):
                available_cols = list(row.index)
                raise HTTPException(
                    status_code=400, 
                    detail=f"Valor de Molde está vazio (NaN) na linha {idx+1} do Excel. Colunas disponíveis: {available_cols}"
                )
            
            # Normalizar o valor
            if isinstance(mold_value_raw, float) and not pd.isna(mold_value_raw) and mold_value_raw.is_integer():
                mold_value_raw = int(mold_value_raw)
            
            mold_value = str(mold_value_raw).strip()
            print(f"DEBUG: mold_value normalizado: '{mold_value}'")
            
            # Buscar molde - tentar todas as possibilidades de uma vez
            mold = None
            
            # Construir lista de condições OR para buscar
            conditions = []
            
            # 1. Buscar por ID (se for número)
            try:
                mold_id_int = int(float(mold_value_raw)) if isinstance(mold_value_raw, (str, float)) else int(mold_value_raw)
                conditions.append(Mold.id == mold_id_int)
            except:
                pass
            
            # 2. Buscar por nome exato (case-insensitive)
            conditions.append(func.lower(Mold.name) == func.lower(mold_value))
            
            # 3. Se começa com M, buscar sem o M (por ID e por nome)
            if mold_value.upper().startswith("M") and len(mold_value) > 1:
                mold_without_m = mold_value[1:].strip()
                try:
                    mold_id_no_m = int(float(mold_without_m))
                    conditions.append(Mold.id == mold_id_no_m)
                except:
                    pass
                conditions.append(func.lower(Mold.name) == func.lower(mold_without_m))
            
            # 4. Se é só número, buscar com prefixo M
            try:
                int(mold_value)  # Se conseguir converter, é número
                mold_with_m = f"M{mold_value}"
                conditions.append(func.lower(Mold.name) == func.lower(mold_with_m))
            except:
                pass
            
            # Buscar com todas as condições OR
            if conditions:
                mold = db.query(Mold).filter(or_(*conditions)).first()
            
            # Se ainda não encontrou, retornar erro com todos os moldes disponíveis
            if not mold:
                all_molds = db.query(Mold).all()
                mold_info = [f"ID:{m.id} Nome:'{m.name}'" for m in all_molds]
                error_msg = f"Molde '{mold_value}' (raw: {mold_value_raw}, tipo: {type(mold_value_raw).__name__}) não encontrado. Moldes disponíveis: {mold_info}"
                logger.error(error_msg)
                print(f"ERRO: {error_msg}")  # Print também para garantir que aparece
                raise HTTPException(status_code=404, detail=error_msg)
            
            mold_id = mold.id
            
            # Buscar produto - tentar múltiplas variações
            product_value = None
            for col_name in ["Produto", "produto", "PRODUTO", "product_id", "Product"]:
                if col_name in row.index:
                    product_value = row[col_name]
                    break
            
            if product_value is None or pd.isna(product_value):
                raise HTTPException(status_code=400, detail=f"Valor de Produto está vazio na linha {idx+1} do Excel")
            
            # Converter para string, tratando floats que podem vir do Excel
            if isinstance(product_value, (int, float)):
                # Se for número, converter direto (tratando floats como "1.0" -> 1)
                if isinstance(product_value, float) and product_value.is_integer():
                    product_value = str(int(product_value))
                else:
                    product_value = str(product_value)
            else:
                product_value = str(product_value).strip()
            
            product = None
            product_id = None
            
            # Estratégia 1: Tentar converter para int e buscar por ID
            try:
                # Tenta converter float primeiro (caso venha "1.0"), depois int
                product_id_int = int(float(product_value))
                product = db.query(Product).filter(Product.id == product_id_int).first()
                if product:
                    product_id = product.id
            except (ValueError, TypeError):
                pass
            
            # Estratégia 2: Se não encontrou por ID, buscar pelo nome exato (case-insensitive)
            if not product:
                product = db.query(Product).filter(func.lower(Product.name) == func.lower(product_value)).first()
                if product:
                    product_id = product.id
            
            # Se ainda não encontrou, retornar erro com todos os produtos disponíveis
            if not product:
                all_products = db.query(Product).all()
                product_names = [p.name for p in all_products]
                raise HTTPException(
                    status_code=404,
                    detail=f"Produto '{product_value}' não encontrado. Produtos disponíveis: {product_names}"
                )
            
            # Buscar composition_line pelo molde e produto (sem especificar linha)
            comp_line = db.query(CompositionLine).filter_by(
                mold_id=mold_id,
                product_id=product_id
            ).first()
            
            if not comp_line:
                raise HTTPException(
                    status_code=404,
                    detail=f"CompositionLine não encontrada para molde {mold_id}, produto {product_id}"
                )
            
            # Descobrir a linha de produção através da CompositionLine encontrada
            discovered_line_id = comp_line.production_line_id
            
            # Buscar cliente - tentar múltiplas variações
            client_name = None
            for col_name in ["Cliente", "cliente", "CLIENTE", "client"]:
                if col_name in row.index:
                    client_name = str(row[col_name]).strip()
                    break
            
            if not client_name:
                raise HTTPException(status_code=400, detail=f"Valor de Cliente está vazio na linha {idx+1} do Excel")
            
            client = db.query(Client).filter_by(name=client_name).first()
            if not client:
                raise HTTPException(status_code=404, detail=f"Cliente '{client_name}' não encontrado")
            
            # Buscar demanda - tentar múltiplas variações
            demand_value = None
            for col_name in ["Demanda do Pedido", "Demanda", "demanda", "DEMANDA", "Demanda do pedido"]:
                if col_name in row.index:
                    demand_value = row[col_name]
                    break
            
            if demand_value is None or pd.isna(demand_value):
                raise HTTPException(status_code=400, detail=f"Valor de Demanda está vazio na linha {idx+1} do Excel")
            
            # Converter demanda (pode vir com separador de milhar como "100.800")
            try:
                if isinstance(demand_value, str):
                    demand_value = demand_value.replace(".", "").replace(",", ".")
                demand = int(float(demand_value))
            except:
                raise HTTPException(status_code=400, detail=f"Valor de Demanda inválido na linha {idx+1}: {demand_value}")
            
            # Buscar data limite - tentar múltiplas variações
            billing_date_value = None
            for col_name in ["Data Limite de Faturamento", "Data Limite do Faturamento", "data limite de faturamento", "Data Limite"]:
                if col_name in row.index:
                    billing_date_value = row[col_name]
                    break
            
            if billing_date_value is None or pd.isna(billing_date_value):
                raise HTTPException(status_code=400, detail=f"Valor de Data Limite de Faturamento está vazio na linha {idx+1} do Excel")
            
            billing_date = pd.to_datetime(billing_date_value).date()
            
            # Buscar hora limite - tentar múltiplas variações
            billing_time_value = None
            for col_name in ["Horário Limite de Faturamento", "Hora Limite do Faturamento", "Horario Limite de Faturamento", "Hora Limite", "horário limite de faturamento"]:
                if col_name in row.index:
                    billing_time_value = row[col_name]
                    break
            
            if billing_time_value is None or pd.isna(billing_time_value):
                billing_time = default_billing_deadline_time
            else:
                billing_time = pd.to_datetime(billing_time_value).time()
            
            promised_date = datetime.combine(billing_date, billing_time)
            
            # Buscar valor unitário - tentar múltiplas variações
            product_value_raw = None
            for col_name in ["Valor Unitário (R$/por unidade)", "Valor a Faturar", "Valor Unitário", "valor unitário", "Valor"]:
                if col_name in row.index:
                    product_value_raw = row[col_name]
                    break
            
            if product_value_raw is None or pd.isna(product_value_raw):
                raise HTTPException(status_code=400, detail=f"Valor Unitário está vazio na linha {idx+1} do Excel")
            
            # Converter valor (pode vir como "R$ 0,41" - remover R$ e trocar vírgula por ponto)
            try:
                if isinstance(product_value_raw, str):
                    product_value_str = product_value_raw.replace("R$", "").replace(" ", "").replace(",", ".")
                else:
                    product_value_str = str(product_value_raw)
                product_value_float = float(product_value_str)
            except:
                raise HTTPException(status_code=400, detail=f"Valor Unitário inválido na linha {idx+1}: {product_value_raw}")
            
            # Criar job (não salvar no banco, apenas usar para cálculo)
            job = Job(
                fk_id_product=product_id,
                fk_id_client=client.id,
                demand=demand,
                promised_date=promised_date,
                product_value=product_value_float
            )
            jobs_data.append(job)
            
            # Agrupar por linha descoberta
            if discovered_line_id not in jobs_by_line_discovered:
                jobs_by_line_discovered[discovered_line_id] = []
            jobs_by_line_discovered[discovered_line_id].append(job)
        
        # Processar cada linha descoberta separadamente
        for line_id, line_jobs in jobs_by_line_discovered.items():
            # Converter machine_states para ProgrammedStop (apenas desta linha)
            stops_for_line = []
            for state in machine_states:
                if state.production_line_id == line_id:
                    if state.used and not state.completed:
                        remaining_hours = (state.remaining_injection_hours + state.remaining_post_injection_hours) / 60
                        from datetime import timedelta
                        start_dt = sequencing_date
                        end_dt = start_dt + timedelta(hours=remaining_hours)
                        stop = ProgrammedStop(
                            reason=f"Job em execução: {state.order_number or 'N/A'}",
                            start_datetime=start_dt,
                            end_datetime=end_dt,
                            machine_id=state.machine_id
                        )
                        stops_for_line.append(stop)
            
            # Converter programmed_stops para ProgrammedStop (apenas desta linha)
            for stop_req in programmed_stops:
                # Verificar se a máquina da parada está nesta linha
                comp_line_check = db.query(CompositionLine).filter_by(production_line_id=line_id).first()
                if comp_line_check:
                    # Verificar se a máquina está na linha
                    machines_in_line = [clm.machine_id for clm in comp_line_check.machines]
                    if stop_req.machine_id in machines_in_line:
                        start_dt = datetime.combine(stop_req.start_date, stop_req.start_time)
                        end_dt = datetime.combine(stop_req.end_date, stop_req.end_time)
                        stop = ProgrammedStop(
                            reason=stop_req.reason,
                            start_datetime=start_dt,
                            end_datetime=end_dt,
                            machine_id=stop_req.machine_id
                        )
                        stops_for_line.append(stop)
        
        # Calcular dados dos jobs
        jobs_data_dict = calculate_injection_jobs_data(
            jobs_data=jobs_data,
            sequencing_date=sequencing_date,
            machine_availability=None,  # Usa a disponibilidade individual de cada máquina
            db=db,
            programmed_stops=stops_for_line if stops_for_line else None,
        )
        
        if jobs_data_dict.get("errors"):
            raise HTTPException(
                status_code=400,
                detail={"erro": f"Erros na linha {line_id}", "detalhes": jobs_data_dict["errors"]}
            )
        
        # Log do input
        log_line_id = actual_line_id if actual_line_id != "unknown" else line_id
        _log_injection_solver_input(
            context="solve-from-xlsx",
            line_id=log_line_id,
            jobs=jobs_data_dict["jobs"],
            machines=jobs_data_dict["machines"],
            processing=jobs_data_dict["processing"],
            due=jobs_data_dict["due"],
            priority=jobs_data_dict["priority"],
        )
        
        # Rodar o solver
        status, obj_value, sequences, completion, tardiness = solve_injection_scheduling(
            jobs=jobs_data_dict["jobs"],
            machines=jobs_data_dict["machines"],
            processing=jobs_data_dict["processing"],
            due=jobs_data_dict["due"],
            priority=jobs_data_dict["priority"],
            setup3=jobs_data_dict["setup3"],
            dummy=0,
        )
        
        return {
            "line_id": log_line_id,
            "status": status,
            "objective_value": obj_value,
            "sequences": {str(machine): seq for machine, seq in sequences.items()},
            "completion": [
                {"job": job, "machine": machine, "completion_time": time_value}
                for (job, machine), time_value in completion.items()
            ],
            "tardiness": [
                {"job": job, "tardiness": tard}
                for job, tard in tardiness.items()
            ],
        }
    
    # Processar todas as linhas em paralelo
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=len(jobs_by_line))
    tasks = [
        loop.run_in_executor(executor, process_line, line_id, line_jobs)
        for line_id, line_jobs in jobs_by_line.items()
    ]
    line_results = await asyncio.gather(*tasks)
    
    # Organizar resultados por linha
    for result in line_results:
        results[result["line_id"]] = {
            "status": result["status"],
            "objective_value": result["objective_value"],
            "sequences": result["sequences"],
            "completion": result["completion"],
            "tardiness": result["tardiness"],
        }
    
    return {
        "results_by_line": results,
    }
