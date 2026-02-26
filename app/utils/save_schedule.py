from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date
from collections import defaultdict
from pulp import value
from typing import Dict, List

from app.models.production_schedule_run import ProductionScheduleRun
from app.models.production_schedule_result import ProductionScheduleResult
from app.models.predicted_revenue_by_day import PredictedRevenueByDay
from app.models.composition_line import CompositionLine
from app.models.regular_shift import RegularShift
from app.models.holiday import Holiday
from algorithm.injection.due_date_calculator import calculate_billing_date, add_working_hours
from algorithm.injection.schedule_report_from_db import (
    generate_schedule_report,
    write_schedule_report_from_memory,
)

def save_solver_result_to_db(
    db: Session,
    sequencing_date: datetime,
    jobs_data: list,
    ordem_execucao: list[int],
    start: dict,
    processing_time: list[float],
    bottleneck_times: list[float],
    setup_count: int,
    optimized_setups: int,
) -> ProductionScheduleRun:

    latest_promised_datetime = max(job.promised_date for job in jobs_data)
    total_machine_hours = (latest_promised_datetime - sequencing_date).total_seconds() / 3600

    time_required = max(
        value(start[i]) + processing_time[i] + bottleneck_times[i]
        for i in range(len(jobs_data))
    )

    machine_status = "On Time" if total_machine_hours >= time_required else "Late"

    on_time_count = 0
    revenue_by_day = defaultdict(float)

    # Garantir coluna de sábado quinzenal no run para evitar quebra e preservar regra do solver
    try:
        from sqlalchemy import inspect, text
        bind = db.get_bind()
        insp = inspect(bind)
        run_cols = {c["name"] for c in insp.get_columns(ProductionScheduleRun.__tablename__)}
        if "next_saturday_is_working" not in run_cols:
            db.execute(text("ALTER TABLE production_schedule_run ADD COLUMN next_saturday_is_working BOOLEAN DEFAULT 0"))
    except Exception as e:
        print(f"⚠️  Coluna next_saturday_is_working em production_schedule_run (aviso): {e}")

    run = ProductionScheduleRun(
        sequencing_start=sequencing_date,
        setup_count=setup_count,
        optimized_setups=optimized_setups,
        on_time_jobs=0,
        total_machine_hours=int(time_required),
        max_deadline_hours=int(total_machine_hours),
        machine_status=machine_status,
        next_saturday_is_working=False,
        created_at=datetime.utcnow()
    )
    db.add(run)
    db.flush()

    # Garantir colunas necessárias para salvar valores brutos do solver
    try:
        from sqlalchemy import inspect, text
        bind = db.get_bind()
        insp = inspect(bind)
        table_cols = {c["name"] for c in insp.get_columns(ProductionScheduleResult.__tablename__)}
        if "scheduled_time" not in table_cols:
            db.execute(text("ALTER TABLE production_schedule_result ADD COLUMN scheduled_time TIME"))
        if "completion_time_hours" not in table_cols:
            db.execute(text("ALTER TABLE production_schedule_result ADD COLUMN completion_time_hours FLOAT"))
        if "order_number" not in table_cols:
            db.execute(text("ALTER TABLE production_schedule_result ADD COLUMN order_number VARCHAR"))
        if "completion_injection_date" not in table_cols:
            db.execute(text("ALTER TABLE production_schedule_result ADD COLUMN completion_injection_date DATE"))
        if "completion_injection_time" not in table_cols:
            db.execute(text("ALTER TABLE production_schedule_result ADD COLUMN completion_injection_time TIME"))
    except Exception as e:
        print(f"⚠️  Colunas da tabela production_schedule_result (aviso): {e}")

    saved_order = 0  # Contador da ordem REAL dos jobs salvos (começa em 0)
    for pos, i in enumerate(ordem_execucao):
        job = jobs_data[i]
        start_h = value(start[i])
        proc_time = processing_time[i]
        bottleneck = bottleneck_times[i]

        moment_conclusion = start_h + proc_time
        moment_conclusion_final = moment_conclusion + bottleneck
        
        # Filtrar jobs com tempo de conclusão no gargalo <= 0
        if moment_conclusion_final <= 0:
            continue  # Pular este job, não armazenar (não incrementa saved_order!)
        
        production_completion = sequencing_date + timedelta(hours=moment_conclusion_final)
        injection_completion = sequencing_date + timedelta(hours=moment_conclusion)
        start_dt = sequencing_date + timedelta(hours=start_h)

        status = "On Time" if production_completion <= job.promised_date else "Late"
        if status == "On Time":
            on_time_count += 1

        # Calcular data de faturamento baseada nas regras de configuração
        billing_date = calculate_billing_date(production_completion, db)
        
        # Garantir que demand não seja None
        job_demand = job.demand if job.demand is not None else 0
        job_value = job.product_value if job.product_value is not None else 0

        revenue = round(job_value * job_demand, 2)
        
        print(f"DEBUG - Job {job.id}: demand={job_demand}, value={job_value}, revenue={revenue}")
        revenue_by_day[billing_date] += revenue

        # Buscar máquina e molde através da composition_line
        composition_line = db.query(CompositionLine).filter_by(
            product_id=job.fk_id_product
        ).first()
        
        machine_name = "N/A"
        mold_name = "N/A"
        
        if composition_line:
            mold_name = composition_line.mold.name if composition_line.mold else "N/A"
            # Pegar a primeira máquina da composition_line (se houver)
            if composition_line.machines and len(composition_line.machines) > 0:
                machine_name = composition_line.machines[0].machine.name

        db.add(ProductionScheduleResult(
            run_id=run.id,
            job_id=job.id,
            order_index=saved_order,  # Usa o contador sequencial correto!
            production_line_id=1,  # Linha única para solver antigo
            machine_id=1,  # Máquina única (solver antigo não tem múltiplas máquinas)
            sequence_pos=saved_order,  # Posição na sequência (igual ao order_index para solver antigo)
            job_index_solver=i,  # Índice do job no solver
            client_name=job.client.name,
            product_name=job.product.name,
            machine_name=machine_name,
            mold_name=mold_name,
            quantity=job_demand,
            order_number=None,
            scheduled_date=job.promised_date.date(),
            scheduled_time=job.promised_date.time(),  # Hora prometida (planilha col. Horário Limite Faturamento)
            actual_date=start_dt.date(),
            actual_time=start_dt.time(),  # Adicionar hora de início
            start_in_bottleneck_hours=start_h,  # Adicionar horas desde início
            completion_date=production_completion.date(),
            completion_time=production_completion.time(),
            completion_time_hours=moment_conclusion,  # Fim do solver (valor puro)
            completion_injection_date=injection_completion.date(),
            completion_injection_time=injection_completion.time(),
            billing_date=billing_date,
            status=status,
            expected_revenue=revenue,
            final_completion_time_hours=moment_conclusion_final  # Adicionar tempo final
        ))
        
        saved_order += 1  # Incrementa APENAS quando salva um job

    run.on_time_jobs = on_time_count
    db.flush()

    for day, total in sorted(revenue_by_day.items()):
        db.add(PredictedRevenueByDay(
            run_id=run.id,
            billing_date=day,
            revenue_total=round(total, 2)
        ))

    db.commit()
    db.refresh(run)
    
    # ========== GERAR SCHEDULE REPORT (OBRIGATÓRIO) ==========
    # REGRA: O log SEMPRE deve ser gerado na pasta logs. Se falhar, o fluxo falha.
    print(f"\n{'='*100}")
    print(f"[SCHEDULE_REPORT] Iniciando geração do schedule_report para run_id={run.id}")
    print(f"[SCHEDULE_REPORT] Fonte: 100% Banco de Dados (após commit)")
    print(f"{'='*100}")
    
    filepath = generate_schedule_report(run.id, db)
    print(f"\n✅ Schedule report gerado: {filepath}\n")
    return run


def save_test_solver_results_to_db(
    db: Session,
    sequencing_date: datetime,
    solver_results: Dict[int, Dict],
    jobs_by_line: Dict[int, Dict],
    next_saturday_is_working: bool = False,
):
    """
    Salva resultados do solver respeitando turnos, feriados e sábados quinzenais.
    Retorna (run, schedule_report_path). O log é SEMPRE gerado na pasta logs.
    """
    regular_shifts = db.query(RegularShift).all()
    holidays = [h.date for h in db.query(Holiday).all()]
    
    # Calcular métricas gerais
    total_setups = 0
    optimized_setups = 0
    on_time_count = 0
    max_completion_time = 0.0
    
    revenue_by_day = defaultdict(float)
    all_results = []
    errors = []  # Lista de erros de validação
    
    # Processar cada linha de produção
    for pl_id, solver_result in solver_results.items():
        if "error" in solver_result:
            print(f"⚠️ Linha {pl_id} teve erro, pulando salvamento")
            continue
        
        sequences = solver_result.get("sequences", {})
        completion = solver_result.get("completion", {})
        inputs = solver_result.get("inputs", {})
        setup3 = inputs.get("setup3", {})
        machine_idx_to_id = inputs.get("machine_idx_to_id", {})
        ordered_jobs = inputs.get("ordered_jobs", [])
        
        # Para cada sequência de máquina, processar os jobs
        for machine_idx, job_sequence in sequences.items():
            # machine_idx é o índice da máquina (1, 2, 3...)
            try:
                machine_idx_int = int(machine_idx)
            except (TypeError, ValueError):
                machine_idx_int = machine_idx

            # Converter índice interno do solver para machine_id real do JSON/BD
            machine_real_id = machine_idx_to_id.get(machine_idx_int)
            if machine_real_id is None:
                machine_real_id = machine_idx_to_id.get(str(machine_idx_int))
            if machine_real_id is None:
                # fallback seguro para não quebrar
                machine_real_id = machine_idx_int

            # Contar setups reais desta máquina com base na sequência do solver.
            # Regra: setup > 0 entre jobs consecutivos conta 1 setup.
            seq_for_setup = [j for j in job_sequence if j != 0]
            for prev_job, curr_job in zip(seq_for_setup, seq_for_setup[1:]):
                setup_val = setup3.get((prev_job, curr_job, machine_idx_int))
                if setup_val is None:
                    setup_val = setup3.get((prev_job, curr_job, machine_idx))
                try:
                    if setup_val is not None and float(setup_val) > 0:
                        total_setups += 1
                except (TypeError, ValueError):
                    pass
            
            # FILTRAR DUMMY ANTES DO ENUMERATE (para sequence_pos correto)
            job_sequence_no_dummy = [j for j in job_sequence if j != 0]
            
            for sequence_position, job_idx in enumerate(job_sequence_no_dummy):
                # Agora sequence_position é correto: 0, 1, 2... (sem contar dummy)
                
                # sequence_position é a posição deste job na sequência desta máquina (0-indexed)
                
                # Buscar dados do job
                job_data = next((j for j in ordered_jobs if j["job_index"] == job_idx), None)
                if not job_data:
                    continue
                
                job_type = job_data.get("type")
                
                # Buscar tempo de conclusão
                completion_time = completion.get((job_idx, machine_idx_int))
                if completion_time is None:
                    completion_time = completion.get((job_idx, machine_idx))
                if completion_time is None:
                    continue
                
                # Filtrar jobs com tempo de conclusão <= 0
                if completion_time <= 0:
                    continue
                
                # CALCULAR DATAS COM TURNOS, FERIADOS E SÁBADOS QUINZENAIS
                production_completion = add_working_hours(
                    start_datetime=sequencing_date,
                    hours_to_add=completion_time,
                    regular_shifts=regular_shifts,
                    holidays=holidays,
                    reference_date=sequencing_date.date(),
                    next_saturday_is_working=next_saturday_is_working
                )
                max_completion_time = max(max_completion_time, completion_time)
                
                # CALCULAR INSTANTE DE INÍCIO NO GARGALO (horário real de início do job)
                # start_in_bottleneck = completion_time - processing_time
                machines_data = job_data.get("processing_time_by_machine", job_data.get("machines", []))
                
                # machines é uma LISTA de dicionários com machine_id e production_time
                processing_time = 0.0
                try:
                    if isinstance(machines_data, list):
                        for machine_data in machines_data:
                            if machine_data.get("machine_id") == machine_real_id:
                                processing_time = float(machine_data.get("production_time", 0.0))
                                break
                    elif isinstance(machines_data, dict):
                        # Se for dict (formato antigo), buscar direto
                        processing_time = float(machines_data.get(machine_idx_int, machines_data.get(machine_idx, 0.0)))
                except:
                    processing_time = 0.0
                
                start_in_bottleneck_hours = max(0.0, float(completion_time) - processing_time)
                start_in_bottleneck_datetime = add_working_hours(
                    start_datetime=sequencing_date,
                    hours_to_add=start_in_bottleneck_hours,
                    regular_shifts=regular_shifts,
                    holidays=holidays,
                    reference_date=sequencing_date.date(),
                    next_saturday_is_working=next_saturday_is_working
                )
                
                # PEGAR final_completion_time_hours DO JOB (já calculado no solver)
                final_completion_time_hours = job_data.get("final_completion_time_hours")
                
                # Fallback: Se não encontrou, calcular agora
                if final_completion_time_hours is None:
                    try:
                        excel_data = job_data.get("excel_data", {})
                        total_post_injection = float(excel_data.get("total_post_injection_time", 0.0)) if excel_data else 0.0
                        final_completion_time_hours = float(completion_time) + total_post_injection
                    except:
                        final_completion_time_hours = float(completion_time)
                
                # ========== PROCESSAR STATE_MACHINE ==========
                if job_type == "state_machine":
                    # Jobs state_machine: representam estado inicial das máquinas
                    
                    # VERIFICAR SE FOI COMPLETADO (não salvar no BD se completed=True)
                    is_completed = bool(job_data.get("completed", False))
                    
                    product_name = job_data.get("product_name", "Estado Inicial da Máquina")
                    mold_name = job_data.get("mold_name", "--")
                    client_name = job_data.get("client_name", "--")  # SALVAR CLIENT_NAME DO JSON
                    order_number = job_data.get("order_number")
                    
                    # PEGAR DEMAND E BILLING_VALUE DO JSON (campos adicionais do state_machine)
                    demand = job_data.get("demand", 0)
                    billing_value = job_data.get("billing_value", 0.0)
                    
                    # Buscar billing_deadline_date e billing_deadline_time com fallback robusto
                    row_data = job_data.get("row_data", {})
                    scheduled_date = production_completion.date()  # Fallback: usar completion date
                    scheduled_time = None
                    # 1) Root do job_data (quando vier direto do JSON state_machine)
                    billing_deadline_date_val = job_data.get("billing_deadline_date")
                    billing_deadline_time_val = job_data.get("billing_deadline_time")
                    # 2) row_data (compatibilidade)
                    if isinstance(row_data, dict):
                        billing_deadline_date_val = billing_deadline_date_val or row_data.get("billing_deadline_date")
                        billing_deadline_time_val = billing_deadline_time_val or row_data.get("billing_deadline_time")
                        
                        # Tentar parsear billing_deadline_date
                        if billing_deadline_date_val:
                            try:
                                if isinstance(billing_deadline_date_val, str):
                                    # Tentar vários formatos de data
                                    for fmt in ["%Y-%m-%d", "%d/%m/%Y"]:
                                        try:
                                            scheduled_date = datetime.strptime(billing_deadline_date_val, fmt).date()
                                            break
                                        except:
                                            pass
                                elif isinstance(billing_deadline_date_val, (date, datetime)):
                                    scheduled_date = billing_deadline_date_val.date() if isinstance(billing_deadline_date_val, datetime) else billing_deadline_date_val
                            except:
                                pass
                    # Tentar parsear billing_deadline_time (string, time, datetime)
                    if billing_deadline_time_val:
                        if isinstance(billing_deadline_time_val, str):
                            for fmt in ("%H:%M:%S", "%H:%M"):
                                try:
                                    scheduled_time = datetime.strptime(billing_deadline_time_val.strip(), fmt).time()
                                    break
                                except (ValueError, TypeError):
                                    continue
                        elif isinstance(billing_deadline_time_val, datetime):
                            scheduled_time = billing_deadline_time_val.time()
                        elif hasattr(billing_deadline_time_val, "hour") and hasattr(billing_deadline_time_val, "minute"):
                            # datetime.time ou tipo equivalente
                            scheduled_time = billing_deadline_time_val
                    
                    # Buscar nome da máquina pelo machine_id real (vindo do JSON via mapeamento)
                    from app.models.machine import Machine
                    machine = db.query(Machine).filter(Machine.id == machine_real_id).first()
                    machine_name = machine.name if machine else f"Máquina {machine_real_id}"
                    
                    # Calcular data/hora final+pós para comparar com data prometida
                    final_completion_datetime = None
                    if final_completion_time_hours is not None and sequencing_date:
                        try:
                            final_completion_datetime = add_working_hours(
                                start_datetime=sequencing_date,
                                hours_to_add=final_completion_time_hours,
                                regular_shifts=regular_shifts,
                                holidays=holidays,
                                reference_date=sequencing_date.date(),
                                next_saturday_is_working=next_saturday_is_working
                            )
                        except Exception as e:
                            print(f"⚠️  Erro ao calcular final_completion_datetime para state machine {job_idx}: {e}")
                    
                    # Calcular status: comparar data prometida (com hora se houver) com data final+pós
                    if scheduled_date and final_completion_datetime:
                        scheduled_datetime = datetime.combine(scheduled_date, scheduled_time if scheduled_time else datetime.max.time())
                        status = "On Time" if final_completion_datetime <= scheduled_datetime else "Late"
                        if status == "On Time":
                            on_time_count += 1
                    else:
                        # Se não tiver dados suficientes, usar "-"
                        status = "-"
                    
                    print(f"DEBUG State Machine - job_idx {job_idx}: completed={is_completed}, start={start_in_bottleneck_hours:.2f}h, completion={completion_time:.2f}h, product={product_name}, client={client_name}, machine={machine_name}, scheduled_date={scheduled_date}, scheduled_time={scheduled_time}, status={status}")
                    
                    # FILTRAR: Se completed=True, NÃO SALVAR NO BD (não aparece no log)
                    if is_completed:
                        print(f"  ⏩ State machine completado (completed=True) - NÃO salvar no BD")
                        continue  # Pular este job
                    
                    # Calcular data de faturamento
                    billing_date = calculate_billing_date(production_completion, db)
                    
                    # Adicionar à lista de resultados (salvar no BD)
                    all_results.append({
                        "job_id": 0,  # State machine não tem composition_line_id
                        "order_index": 0,  # Será recalculado após ordenação
                        "production_line_id": pl_id,
                        "machine_id": machine_real_id,  # SALVAR ID REAL DA MÁQUINA
                        "sequence_pos": sequence_position,  # SALVAR POSIÇÃO NA SEQUÊNCIA
                        "job_index_solver": job_idx,
                        "client_name": client_name,  # SALVAR CLIENT_NAME DO JSON
                        "order_number": order_number,
                        "product_name": product_name,  # SALVAR PRODUCT_NAME DO JSON
                        "machine_name": machine_name,  # NOME DA MÁQUINA BUSCADO DO BD
                        "mold_name": mold_name,  # SALVAR MOLD_NAME DO JSON
                        "quantity": demand if demand else 0,  # SALVAR DEMAND DO JSON
                        "scheduled_date": scheduled_date,  # USAR BILLING_DEADLINE_DATE SE DISPONÍVEL
                        "scheduled_time": scheduled_time,  # Hora limite de faturamento (planilha)
                        "actual_date": start_in_bottleneck_datetime.date(),
                        "actual_time": start_in_bottleneck_datetime.time(),
                        "start_in_bottleneck_hours": round(start_in_bottleneck_hours, 2),
                        "completion_date": production_completion.date(),
                        "completion_time": production_completion.time(),
                        "completion_time_hours": round(float(completion_time), 2),  # Fim puro do solver
                        "completion_injection_date": production_completion.date(),
                        "completion_injection_time": production_completion.time(),
                        "billing_date": billing_date,
                        "status": status,  # CALCULAR STATUS CORRETAMENTE
                        "expected_revenue": float(billing_value) if billing_value else 0.0,  # SALVAR BILLING_VALUE DO JSON
                        "final_completion_time_hours": round(final_completion_time_hours, 2)
                    })
                    
                    continue  # Próximo job
                
                # ========== PROCESSAR PROGRAMMED_STOP ==========
                if job_type == "programmed_stop":
                    # Jobs programmed_stop: apenas mostrar no report, sem validações estritas
                    product_name = job_data.get("product_name", "Parada Programada")
                    
                    # Buscar nome da máquina pelo machine_id real (vindo do JSON via mapeamento)
                    comp_line_id = job_data.get("composition_line_id")
                    from app.models.machine import Machine
                    machine = db.query(Machine).filter(Machine.id == machine_real_id).first()
                    machine_name = machine.name if machine else f"Máquina {machine_real_id}"
                    
                    print(f"DEBUG Programmed Stop - job_idx {job_idx}: start={start_in_bottleneck_hours:.2f}h, completion={completion_time:.2f}h, final={final_completion_time_hours:.2f}h")

                    # Data/hora prometida da parada programada:
                    # usar end_date/end_time do JSON; fallback para start_date/start_time.
                    row_data = job_data.get("row_data", {})
                    scheduled_date = production_completion.date()
                    scheduled_time = None

                    raw_date = (
                        job_data.get("end_date")
                        or (row_data.get("end_date") if isinstance(row_data, dict) else None)
                        or job_data.get("start_date")
                        or (row_data.get("start_date") if isinstance(row_data, dict) else None)
                    )
                    raw_time = (
                        job_data.get("end_time")
                        or (row_data.get("end_time") if isinstance(row_data, dict) else None)
                        or job_data.get("start_time")
                        or (row_data.get("start_time") if isinstance(row_data, dict) else None)
                    )

                    if raw_date:
                        try:
                            if isinstance(raw_date, str):
                                for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
                                    try:
                                        scheduled_date = datetime.strptime(raw_date.strip(), fmt).date()
                                        break
                                    except ValueError:
                                        continue
                            elif isinstance(raw_date, (date, datetime)):
                                scheduled_date = raw_date.date() if isinstance(raw_date, datetime) else raw_date
                        except Exception:
                            pass

                    if raw_time:
                        try:
                            if isinstance(raw_time, str):
                                for fmt in ("%H:%M:%S", "%H:%M"):
                                    try:
                                        scheduled_time = datetime.strptime(raw_time.strip(), fmt).time()
                                        break
                                    except ValueError:
                                        continue
                            elif isinstance(raw_time, datetime):
                                scheduled_time = raw_time.time()
                            elif hasattr(raw_time, "hour") and hasattr(raw_time, "minute"):
                                scheduled_time = raw_time
                        except Exception:
                            pass
                    
                    # Adicionar à lista de resultados com campos não aplicáveis como "--"
                    all_results.append({
                        "job_id": comp_line_id if comp_line_id else 0,
                        "order_index": 0,  # Será recalculado após ordenação
                        "production_line_id": pl_id,
                        "machine_id": machine_real_id,  # SALVAR ID REAL DA MÁQUINA
                        "sequence_pos": sequence_position,  # SALVAR POSIÇÃO NA SEQUÊNCIA
                        "job_index_solver": job_idx,
                        "client_name": "--",  # Não aplicável
                        "product_name": product_name,
                        "machine_name": machine_name,
                        "mold_name": "--",  # Não aplicável
                        "quantity": 0,  # Não aplicável
                        "scheduled_date": scheduled_date,
                        "scheduled_time": scheduled_time,
                        "actual_date": start_in_bottleneck_datetime.date(),  # Data real de início
                        "actual_time": start_in_bottleneck_datetime.time(),  # Hora real de início
                        "start_in_bottleneck_hours": round(start_in_bottleneck_hours, 2),  # Horas desde sequencing_start
                        "completion_date": production_completion.date(),
                        "completion_time": production_completion.time(),
                        "completion_time_hours": round(float(completion_time), 2),  # Fim puro do solver
                        "completion_injection_date": production_completion.date(),
                        "completion_injection_time": production_completion.time(),
                        "billing_date": production_completion.date(),  # Não aplicável, mas precisa de data válida
                        "status": "--",  # Não aplicável
                        "expected_revenue": 0.0,  # Não aplicável
                        "final_completion_time_hours": round(final_completion_time_hours, 2)
                    })
                    
                    continue  # Próximo job
                
                # ========== PROCESSAR EXCEL (VALIDAÇÃO ESTRITA) ==========
                # VALIDAÇÃO: Job Excel DEVE ter product_name e mold_name preenchidos
                if not job_data.get("product_name") or not job_data.get("mold_name"):
                    error_msg = (
                        f"❌ ERRO DE VALIDAÇÃO: Job Excel (idx={job_idx}) sem product_name ou mold_name! "
                        f"product_name={job_data.get('product_name')}, mold_name={job_data.get('mold_name')}"
                    )
                    print(error_msg)
                    errors.append(error_msg)
                    # Falhar o processo de persistência
                    raise ValueError(error_msg)
                
                # USAR DADOS PRESERVADOS DO JOB_DATA (já vêm do solver_wrapper)
                product_name = job_data.get("product_name", "Produto Desconhecido")
                mold_name = job_data.get("mold_name", "N/A")
                client_name = job_data.get("client_name", "Cliente Desconhecido")
                
                # Extrair dados do job_data (demanda, valor unitário, etc)
                quantity = job_data.get("demand", 0)
                if quantity:
                    try:
                        quantity = int(float(quantity))
                    except:
                        quantity = 0
                
                # Obter valor unitário diretamente do job_data ou excel_data (já lido da planilha)
                product_value = job_data.get("unit_value", 0.0)
                source = "job_data.unit_value"
                if not product_value or product_value == 0.0:
                    # Tentar buscar do excel_data
                    excel_data = job_data.get("excel_data", {})
                    product_value = excel_data.get("unit_value", 0.0)
                    if product_value:
                        source = "excel_data.unit_value"
                
                if product_value:
                    try:
                        product_value = float(product_value)
                    except:
                        product_value = 0.0
                        source = "conversion_failed"
                
                # Se não encontrou no job_data/excel_data, tentar buscar do row_data (fallback)
                # Buscar em TODAS as colunas que possam conter o valor unitário
                if product_value == 0.0:
                    row_data = job_data.get("row_data", {})
                    if isinstance(row_data, dict):
                        # Lista expandida de termos para buscar
                        search_terms = [
                            "valor unitário", "valor unitario", "valor unit", 
                            "unit value", "unit price", "preço unitário", "preco unitario",
                            "valor", "value", "price", "preço", "preco"
                        ]
                        for key, value in row_data.items():
                            if key and value:
                                key_lower = str(key).lower().strip()
                                # Verificar se a chave contém algum dos termos de busca
                                if any(term in key_lower for term in search_terms):
                                    try:
                                        # Tentar converter diretamente
                                        product_value = float(value)
                                        break
                                    except (ValueError, TypeError):
                                        # Tentar tratar formatos comuns (R$ 20,00 ou 20.000,00)
                                        try:
                                            value_str = str(value).strip()
                                            value_str = value_str.replace("R$", "").replace("$", "").replace("€", "").replace("£", "").strip()
                                            # Substituir vírgula por ponto (formato brasileiro)
                                            if value_str.count(".") > 0 and value_str.count(",") > 0:
                                                # Formato: 20.000,50 -> 20000.50
                                                value_str = value_str.replace(".", "").replace(",", ".")
                                            elif value_str.count(",") > 0:
                                                # Formato: 20,50 -> 20.50
                                                value_str = value_str.replace(",", ".")
                                            product_value = float(value_str)
                                            break
                                        except (ValueError, TypeError):
                                            pass
                
                # Buscar data e hora prometida: 1) job_data.promised_date (planilha col. F+G), 2) row_data
                scheduled_date = production_completion.date()
                scheduled_time = None
                order_number = None
                promised = job_data.get("promised_date")
                if promised is not None:
                    if isinstance(promised, datetime):
                        scheduled_date = promised.date()
                        scheduled_time = promised.time()
                    elif isinstance(promised, str):
                        try:
                            promised_dt = datetime.fromisoformat(promised.replace("Z", "+00:00"))
                            scheduled_date = promised_dt.date()
                            scheduled_time = promised_dt.time()
                        except (ValueError, TypeError):
                            pass
                row_data = job_data.get("row_data", {})
                if isinstance(row_data, dict):
                    for key, value in row_data.items():
                        if not key or value is None:
                            continue
                        key_lower = str(key).lower().strip()
                        if key_lower in ["número do pedido", "numero do pedido", "pedido", "order_number", "order number"]:
                            order_number = str(value).strip()
                            break
                if isinstance(row_data, dict) and (scheduled_time is None or scheduled_date == production_completion.date()):
                    data_str = None
                    hora_str = None
                    for key, value in row_data.items():
                        if not key or value is None:
                            continue
                        key_lower = str(key).lower().strip()
                        if key_lower in ["data limite de faturamento", "data prometida", "data", "date", "promised_date"]:
                            data_str = value
                        if key_lower in ["horário limite de faturamento", "horario limite de faturamento", "horário prometido", "horario prometido"]:
                            hora_str = value
                    if data_str:
                        try:
                            if isinstance(data_str, str):
                                for fmt in ["%d/%m/%Y", "%Y-%m-%d"]:
                                    try:
                                        scheduled_date = datetime.strptime(str(data_str).strip(), fmt).date()
                                        break
                                    except ValueError:
                                        continue
                            elif isinstance(data_str, (date, datetime)):
                                scheduled_date = data_str.date() if isinstance(data_str, datetime) else data_str
                        except (ValueError, TypeError):
                            pass
                    if hora_str and isinstance(hora_str, str):
                        for fmt in ("%H:%M:%S", "%H:%M"):
                            try:
                                scheduled_time = datetime.strptime(str(hora_str).strip(), fmt).time()
                                break
                            except ValueError:
                                continue
                
                print(f"DEBUG Excel - job_idx {job_idx}: demand={quantity}, unit_value={product_value}, product={product_name}, mold={mold_name}, client={client_name}, scheduled_date={scheduled_date}, scheduled_time={scheduled_time}")
                print(f"DEBUG - final_completion_time_hours={final_completion_time_hours:.2f}h")
                
                # Buscar nome da máquina pelo machine_id real (vindo do JSON via mapeamento)
                comp_line_id = job_data.get("composition_line_id")
                from app.models.machine import Machine
                machine = db.query(Machine).filter(Machine.id == machine_real_id).first()
                machine_name = machine.name if machine else "N/A"
                
                # Calcular status usando data e hora prometida (quando houver)
                scheduled_datetime = datetime.combine(scheduled_date, scheduled_time if scheduled_time else datetime.max.time())
                status = "On Time" if production_completion <= scheduled_datetime else "Late"
                if status == "On Time":
                    on_time_count += 1
                
                # Calcular data de faturamento
                billing_date = calculate_billing_date(production_completion, db)
                
                # Calcular receita: valor unitário * demanda
                revenue = round(product_value * quantity, 2) if quantity > 0 and product_value > 0 else 0.0
                revenue_by_day[billing_date] += revenue
                
                # Log detalhado para debug
                if product_value == 0.0:
                    print(f"⚠️ WARNING - Excel Job (comp_line {comp_line_id}): unit_value=0.0! quantity={quantity}, revenue={revenue}")
                    print(f"   Product: {product_name}, Mold: {mold_name}")
                    print(f"   job_data keys: {list(job_data.keys())}")
                    print(f"   excel_data: {job_data.get('excel_data', {})}")
                    row_data = job_data.get("row_data", {})
                    print(f"   row_data keys: {list(row_data.keys()) if isinstance(row_data, dict) else 'N/A'}")
                    # Mostrar TODAS as colunas e valores do row_data para debug
                    if isinstance(row_data, dict):
                        print(f"   TODAS as colunas da planilha para este job:")
                        for key, value in row_data.items():
                            if key:
                                print(f"      '{key}' = {value} (tipo: {type(value).__name__})")
                        print(f"   Tentando encontrar valor unitário no row_data...")
                        for key, value in row_data.items():
                            if key and value:
                                key_lower = str(key).lower().strip()
                                if any(term in key_lower for term in ["valor", "value", "price", "preço"]):
                                    print(f"   ⚠️ CANDIDATO ENCONTRADO: '{key}' = {value} (tipo: {type(value).__name__}) - mas não foi convertido!")
                else:
                    print(f"✅ DEBUG - Excel Job (comp_line {comp_line_id}): start={start_in_bottleneck_hours:.2f}h, completion={completion_time:.2f}h, quantity={quantity}, unit_value={product_value} (fonte: {source}), revenue={revenue}")
                
                # Adicionar à lista de resultados
                all_results.append({
                    "job_id": comp_line_id,  # Usar composition_line_id como job_id
                    "order_index": 0,  # Será recalculado após ordenação
                    "production_line_id": pl_id,  # SALVAR LINHA DE PRODUÇÃO DO SOLVER
                    "machine_id": machine_real_id,  # SALVAR ID REAL DA MÁQUINA (para ordenação)
                    "sequence_pos": sequence_position,  # SALVAR POSIÇÃO NA SEQUÊNCIA DA MÁQUINA
                    "job_index_solver": job_idx,  # SALVAR ÍNDICE DO JOB NO SOLVER
                    "client_name": client_name,
                    "order_number": order_number,
                    "product_name": product_name,
                    "machine_name": machine_name,
                    "mold_name": mold_name,
                    "quantity": quantity,
                    "scheduled_date": scheduled_date,
                    "scheduled_time": scheduled_time,  # Hora prometida (planilha Horário Limite Faturamento)
                    "actual_date": start_in_bottleneck_datetime.date(),  # Data real de início
                    "actual_time": start_in_bottleneck_datetime.time(),  # Hora real de início
                    "start_in_bottleneck_hours": round(start_in_bottleneck_hours, 2),  # Horas desde sequencing_start
                    "completion_date": production_completion.date(),
                    "completion_time": production_completion.time(),
                    "completion_time_hours": round(float(completion_time), 2),  # Fim puro do solver
                    "completion_injection_date": production_completion.date(),
                    "completion_injection_time": production_completion.time(),
                    "billing_date": billing_date,
                    "status": status,
                    "expected_revenue": revenue,
                    "final_completion_time_hours": round(final_completion_time_hours, 2)  # NOVO CAMPO
                })
    
    # ORDENAR RESULTADOS POR ORDEM REAL DE EXECUÇÃO
    # ORDENAÇÃO OBRIGATÓRIA: production_line_id ASC, machine_id ASC, sequence_pos ASC
    # Garantir que TODOS os valores críticos existam e sejam válidos
    for result in all_results:
        if result.get("start_in_bottleneck_hours") is None:
            result["start_in_bottleneck_hours"] = 0.0
        if result.get("final_completion_time_hours") is None:
            result["final_completion_time_hours"] = 0.0
        if result.get("production_line_id") is None:
            result["production_line_id"] = 1
        if result.get("machine_id") is None:
            result["machine_id"] = 1
        if result.get("sequence_pos") is None:
            result["sequence_pos"] = 0
    
    try:
        # ORDENAÇÃO: production_line_id ASC, machine_id ASC, sequence_pos ASC
        all_results.sort(key=lambda x: (
            x["production_line_id"], 
            x["machine_id"], 
            x["sequence_pos"]
        ))
        print(f"✅ Resultados ordenados: production_line_id ASC, machine_id ASC, sequence_pos ASC")
    except Exception as e:
        print(f"ERRO ao ordenar resultados: {e}")
        # Se falhar ordenação, pelo menos deixa na ordem que veio
        pass
    
    # RECRIAR ORDER_INDEX SEQUENCIAL baseado na ordem real de execução
    for idx, result in enumerate(all_results, start=1):
        result["order_index"] = idx
    
    # Garantir coluna de sábado quinzenal no run para evitar quebra e preservar regra do solver
    try:
        from sqlalchemy import inspect, text
        bind = db.get_bind()
        insp = inspect(bind)
        run_cols = {c["name"] for c in insp.get_columns(ProductionScheduleRun.__tablename__)}
        if "next_saturday_is_working" not in run_cols:
            db.execute(text("ALTER TABLE production_schedule_run ADD COLUMN next_saturday_is_working BOOLEAN DEFAULT 0"))
    except Exception as e:
        print(f"⚠️  Coluna next_saturday_is_working em production_schedule_run (aviso): {e}")

    # Criar run
    run = ProductionScheduleRun(
        sequencing_start=sequencing_date,
        setup_count=total_setups,
        optimized_setups=optimized_setups,
        on_time_jobs=on_time_count,
        total_machine_hours=int(max_completion_time),
        max_deadline_hours=0,  # Não temos essa informação no teste
        machine_status="Completed",
        next_saturday_is_working=next_saturday_is_working,
        created_at=datetime.utcnow()
    )
    db.add(run)
    db.flush()
    
    # Garantir colunas de data/hora prometida e fim bruto do solver
    try:
        from sqlalchemy import inspect, text
        bind = db.get_bind()
        insp = inspect(bind)
        table_cols = {c["name"] for c in insp.get_columns(ProductionScheduleResult.__tablename__)}
        if "scheduled_time" not in table_cols:
            db.execute(text("ALTER TABLE production_schedule_result ADD COLUMN scheduled_time TIME"))
        if "completion_time_hours" not in table_cols:
            db.execute(text("ALTER TABLE production_schedule_result ADD COLUMN completion_time_hours FLOAT"))
        if "order_number" not in table_cols:
            db.execute(text("ALTER TABLE production_schedule_result ADD COLUMN order_number VARCHAR"))
        if "completion_injection_date" not in table_cols:
            db.execute(text("ALTER TABLE production_schedule_result ADD COLUMN completion_injection_date DATE"))
        if "completion_injection_time" not in table_cols:
            db.execute(text("ALTER TABLE production_schedule_result ADD COLUMN completion_injection_time TIME"))
    except Exception as e:
        print(f"⚠️  Colunas da tabela production_schedule_result (aviso): {e}")
    
    # Salvar resultados (sempre com scheduled_date e scheduled_time para o schedule_report mostrar data+hora)
    for result_data in all_results:
        db.add(ProductionScheduleResult(
            run_id=run.id,
            **result_data
        ))
    
    # Salvar previsão de receita por dia
    for day, total in sorted(revenue_by_day.items()):
        db.add(PredictedRevenueByDay(
            run_id=run.id,
            billing_date=day,
            revenue_total=round(total, 2)
        ))
    
    try:
        db.commit()
        db.refresh(run)
    except Exception as commit_err:
        # LOG É SUPREMO: gerar arquivo mesmo quando o commit falha
        filepath = write_schedule_report_from_memory(
            run_id=run.id,
            sequencing_start=sequencing_date,
            all_results=all_results,
            created_at=datetime.utcnow(),
            machine_status="Erro no commit",
        )
        print(f"\n✅ Schedule report gerado (fallback pós-erro): {filepath}\n")
        raise commit_err
    
    print(f"\n{'='*100}")
    print(f"✅ Salvamento concluído: {len(all_results)} resultados salvos")
    print(f"📊 Jobs no prazo: {on_time_count}/{len(all_results)}")
    print(f"💰 Previsão de receita: {len(revenue_by_day)} dias")
    print(f"{'='*100}\n")
    
    # ========== GERAR SCHEDULE REPORT (OBRIGATÓRIO - O LOG É SUPREMO) ==========
    # O arquivo SEMPRE é gerado: do BD ou, em fallback, dos dados em memória.
    print(f"\n{'='*100}")
    print(f"[SCHEDULE_REPORT] Iniciando geração do schedule_report para run_id={run.id}")
    print(f"{'='*100}")
    try:
        filepath = generate_schedule_report(run.id, db)
        print(f"\n✅ Schedule report gerado (BD): {filepath}\n")
    except Exception as e:
        print(f"\n⚠️  Falha ao gerar report do BD ({e}). Gerando a partir de dados em memória...")
        filepath = write_schedule_report_from_memory(
            run_id=run.id,
            sequencing_start=sequencing_date,
            all_results=all_results,
            created_at=run.created_at,
            machine_status=run.machine_status or "Completed",
        )
        print(f"\n✅ Schedule report gerado (fallback): {filepath}\n")
    return run, filepath
