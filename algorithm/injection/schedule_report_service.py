"""
Serviço reutilizável para geração de Schedule Reports 100% do BD.

Função principal:
    generate_schedule_report_data(run_id, db) -> Dict
    
Retorna dados estruturados prontos para JSON ou formatação.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.production_schedule_run import ProductionScheduleRun
from app.models.production_schedule_result import ProductionScheduleResult
from app.models.regular_shift import RegularShift
from app.models.holiday import Holiday
from algorithm.injection.due_date_calculator import add_working_hours


def generate_schedule_report_data(run_id: int, db: Session) -> Dict[str, Any]:
    """
    Gera dados estruturados do schedule report 100% do BD.
    
    FONTE DA VERDADE: Apenas tabelas do BD.
    ORDENAÇÃO OBRIGATÓRIA: production_line_id ASC, machine_id ASC, sequence_pos ASC
    
    Args:
        run_id: ID do run
        db: Sessão do banco de dados
        
    Returns:
        Dict com:
        - run_info: informações do run
        - jobs: lista ordenada de jobs
        - summary: resumo de métricas
        
    Raises:
        ValueError: Se run não existir
    """
    
    # Garantir coluna do run (compatibilidade com bancos antigos)
    try:
        from sqlalchemy import inspect, text
        bind = db.get_bind()
        insp = inspect(bind)
        run_cols = {c["name"] for c in insp.get_columns(ProductionScheduleRun.__tablename__)}
        if "next_saturday_is_working" not in run_cols:
            db.execute(text("ALTER TABLE production_schedule_run ADD COLUMN next_saturday_is_working BOOLEAN DEFAULT 0"))
        result_cols = {c["name"] for c in insp.get_columns(ProductionScheduleResult.__tablename__)}
        if "order_number" not in result_cols:
            db.execute(text("ALTER TABLE production_schedule_result ADD COLUMN order_number VARCHAR"))
        if "completion_injection_date" not in result_cols:
            db.execute(text("ALTER TABLE production_schedule_result ADD COLUMN completion_injection_date DATE"))
        if "completion_injection_time" not in result_cols:
            db.execute(text("ALTER TABLE production_schedule_result ADD COLUMN completion_injection_time TIME"))
    except Exception as e:
        print(f"⚠️  Colunas de compatibilidade do schedule_report_service (aviso): {e}")

    # ========== 1. BUSCAR RUN ==========
    run = db.query(ProductionScheduleRun).filter(
        ProductionScheduleRun.id == run_id
    ).first()
    
    if not run:
        raise ValueError(f"Run {run_id} não encontrado no banco de dados")
    
    # ========== 2. BUSCAR RESULTADOS COM ORDENAÇÃO OBRIGATÓRIA ==========
    # QUERY: ORDER BY production_line_id ASC, machine_id ASC, sequence_pos ASC
    results = db.query(ProductionScheduleResult).filter(
        ProductionScheduleResult.run_id == run_id
    ).order_by(
        ProductionScheduleResult.production_line_id.asc(),
        ProductionScheduleResult.machine_id.asc(),
        ProductionScheduleResult.sequence_pos.asc()
    ).all()
    
    # ========== 2.5. BUSCAR INFORMAÇÕES DE JORNADA DE TRABALHO ==========
    # Necessário para calcular data/hora final considerando jornada de trabalho
    regular_shifts = db.query(RegularShift).all()
    holidays = [h.date for h in db.query(Holiday).all()]
    next_saturday_is_working = getattr(run, "next_saturday_is_working", False) or False
    
    # ========== 3. PROCESSAR JOBS ==========
    jobs_data = []
    on_time = 0
    late = 0
    total_revenue = 0.0
    
    for idx, result in enumerate(results, start=1):
        # Calcular processing_time
        processing_time_hours = None
        completion_hours = None
        # Conclusão (h): valor puro do solver (Fim), sem recalcular.
        completion_hours = getattr(result, "completion_time_hours", None)
        if result.start_in_bottleneck_hours is not None and completion_hours is not None:
            processing_time_hours = completion_hours - result.start_in_bottleneck_hours
        
        # Calcular final_completion_datetime usando final_completion_time_hours
        final_completion_datetime = None
        if result.final_completion_time_hours is not None and run.sequencing_start:
            try:
                final_completion_datetime = add_working_hours(
                    start_datetime=run.sequencing_start,
                    hours_to_add=result.final_completion_time_hours,
                    regular_shifts=regular_shifts,
                    holidays=holidays,
                    reference_date=run.sequencing_start.date() if run.sequencing_start else None,
                    next_saturday_is_working=next_saturday_is_working
                )
            except Exception as e:
                print(f"⚠️  Erro ao calcular final_completion_datetime para job {result.job_id}: {e}")
                final_completion_datetime = None
        
        # RECALCULAR STATUS: Comparar data+hora prometida com data final+pós
        # Status válidos são apenas "On Time" ou "Late"
        if result.scheduled_date and final_completion_datetime:
            promised_time = getattr(result, "scheduled_time", None) or datetime.max.time()
            scheduled_datetime = datetime.combine(result.scheduled_date, promised_time)
            calculated_status = "On Time" if final_completion_datetime <= scheduled_datetime else "Late"
            # Calcular tardiness (atraso em horas) usando data final+pós
            if final_completion_datetime > scheduled_datetime:
                tardiness_hours = (final_completion_datetime - scheduled_datetime).total_seconds() / 3600.0
            else:
                tardiness_hours = 0.0
        elif result.status in ["On Time", "Late"]:
            # Se já tiver status válido no BD, usar
            calculated_status = result.status
            tardiness_hours = 0.0
        else:
            # Se não tiver dados suficientes ou status inválido (ex: "State Machine"), usar "-"
            calculated_status = "-"
            tardiness_hours = 0.0
        
        # Contadores (usar status recalculado)
        if calculated_status == "On Time":
            on_time += 1
        elif calculated_status == "Late":
            late += 1
        
        if result.expected_revenue:
            total_revenue += result.expected_revenue
        
        # Montar job data
        job_data = {
            "order": idx,
            "production_line_id": result.production_line_id,
            "machine_id": result.machine_id,
            "sequence_pos": result.sequence_pos,
            "job_index_solver": result.job_index_solver,
            "job_id": result.job_id,
            "order_number": getattr(result, "order_number", None),
            "product_name": result.product_name or "-",
            "mold_name": result.mold_name or "-",
            "client_name": result.client_name or "-",
            "machine_name": result.machine_name or "-",
            "quantity": result.quantity,
            "processing_time_hours": round(processing_time_hours, 2) if processing_time_hours is not None else None,
            "start_in_bottleneck_hours": round(result.start_in_bottleneck_hours, 2) if result.start_in_bottleneck_hours is not None else None,
            "completion_time_hours": round(completion_hours, 2) if completion_hours is not None else None,
            "final_completion_time_hours": round(result.final_completion_time_hours, 2) if result.final_completion_time_hours is not None else None,
            "final_completion_datetime": final_completion_datetime.isoformat() if final_completion_datetime else None,
            "scheduled_date": result.scheduled_date,
            "scheduled_time": getattr(result, "scheduled_time", None),
            "actual_date": result.actual_date,
            "actual_time": result.actual_time,
            "completion_date": result.completion_date,
            "completion_time": result.completion_time,
            "completion_injection_date": getattr(result, "completion_injection_date", None),
            "completion_injection_time": getattr(result, "completion_injection_time", None),
            "billing_date": result.billing_date,
            "tardiness_hours": round(tardiness_hours, 2) if tardiness_hours > 0 else 0,
            "status": calculated_status,
            "expected_revenue": round(result.expected_revenue, 2) if result.expected_revenue is not None else None
        }
        
        jobs_data.append(job_data)
    
    # ========== 4. MONTAR RESPOSTA ==========
    return {
        "run_info": {
            "run_id": run.id,
            "sequencing_start": run.sequencing_start,
            "created_at": run.created_at,
            "setup_count": run.setup_count,
            "optimized_setups": run.optimized_setups,
            "on_time_jobs": run.on_time_jobs,
            "total_machine_hours": run.total_machine_hours,
            "max_deadline_hours": run.max_deadline_hours,
            "machine_status": run.machine_status
        },
        "jobs": jobs_data,
        "summary": {
            "total_jobs": len(jobs_data),
            "on_time": on_time,
            "late": late,
            "total_revenue": round(total_revenue, 2),
            "ordering": "production_line_id ASC, machine_id ASC, sequence_pos ASC",
            "source": "100% Database"
        }
    }



