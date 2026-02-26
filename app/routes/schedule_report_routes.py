"""
Endpoint REST para geração de Schedule Reports 100% do Banco de Dados.

Regras:
- Fonte única: banco de dados
- Ordenação: production_line_id ASC, machine_id ASC, sequence_pos ASC
- Sempre gera arquivo em /logs (se save_file=true)
- Nunca sobrescreve (timestamp único)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.database import get_db
from app.models.production_schedule_run import ProductionScheduleRun
from app.models.production_schedule_result import ProductionScheduleResult
from app.models.regular_shift import RegularShift
from app.models.holiday import Holiday
from algorithm.injection.schedule_report_from_db import generate_schedule_report
from algorithm.injection.schedule_report_service import generate_schedule_report_data
from algorithm.injection.due_date_calculator import add_working_hours

router = APIRouter(prefix="/runs", tags=["Schedule Reports"])


@router.post("/{run_id}/schedule-report")
def create_schedule_report(
    run_id: int = Path(..., description="ID do run para gerar o report"),
    format: str = Query("json", regex="^(json|text)$", description="Formato do retorno: json ou text"),
    save_file: bool = Query(True, description="Se true, salva arquivo em /logs"),
    db: Session = Depends(get_db)
):
    """
    Gera Schedule Report 100% do Banco de Dados.
    
    **Fonte da Verdade**: Apenas tabelas do BD (production_schedule_run e production_schedule_result)
    
    **Ordenação Obrigatória**: ORDER BY production_line_id ASC, machine_id ASC, sequence_pos ASC
    
    **Parâmetros**:
    - `run_id`: ID do run (obrigatório)
    - `format`: "json" (default) ou "text"
    - `save_file`: true (default) ou false - se salva arquivo em /logs
    
    **Retorno**:
    - Se format=json: lista ordenada de jobs + file_path (se save_file=true)
    - Se format=text: conteúdo do log como string + file_path (se save_file=true)
    
    **Regras**:
    - Nunca sobrescreve logs (timestamp único)
    - Campos faltantes preenchidos com "-"
    - Dummy não aparece nos resultados
    """
    
    print(f"\n{'='*100}")
    print(f"[SCHEDULE_REPORT_API] POST /runs/{run_id}/schedule-report")
    print(f"[SCHEDULE_REPORT_API] Format: {format} | Save file: {save_file}")
    print(f"{'='*100}\n")

    # Compatibilidade com bancos antigos: garantir coluna do run antes da query ORM
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
        print(f"⚠️  Colunas de compatibilidade do schedule_report_routes (aviso): {e}")
    
    # ========== 1. BUSCAR RUN NO BANCO ==========
    run = db.query(ProductionScheduleRun).filter(
        ProductionScheduleRun.id == run_id
    ).first()
    
    if not run:
        print(f"❌ Run {run_id} não encontrado no banco de dados")
        raise HTTPException(
            status_code=404,
            detail=f"Run {run_id} não encontrado no banco de dados"
        )
    
    # ========== 2. BUSCAR RESULTADOS COM ORDENAÇÃO OBRIGATÓRIA ==========
    # ORDENAÇÃO: production_line_id ASC, machine_id ASC, sequence_pos ASC
    results = db.query(ProductionScheduleResult).filter(
        ProductionScheduleResult.run_id == run_id
    ).order_by(
        ProductionScheduleResult.production_line_id.asc(),
        ProductionScheduleResult.machine_id.asc(),
        ProductionScheduleResult.sequence_pos.asc()
    ).all()
    
    print(f"✅ Run {run_id} encontrado")
    print(f"✅ Total de resultados: {len(results)}")
    print(f"✅ Ordenação: production_line_id ASC, machine_id ASC, sequence_pos ASC")
    
    if len(results) == 0:
        print(f"⚠️  Nenhum resultado encontrado para run {run_id}")
        
        # Ainda salvar arquivo "sem resultados" se save_file=true
        file_path = None
        if save_file:
            file_path = generate_schedule_report(run_id, db)
            print(f"✅ Arquivo 'sem resultados' gerado: {file_path}")
        
        return {
            "run_id": run_id,
            "status": "no_results",
            "message": "Nenhum resultado encontrado para este run",
            "total_jobs": 0,
            "jobs": [],
            "file_path": file_path,
            "generated_at": datetime.now().isoformat()
        }
    
    # ========== 3. BUSCAR INFORMAÇÕES DE JORNADA DE TRABALHO ==========
    # Necessário para calcular data/hora final considerando jornada de trabalho
    regular_shifts = db.query(RegularShift).all()
    holidays = [h.date for h in db.query(Holiday).all()]
    next_saturday_is_working = getattr(run, "next_saturday_is_working", False) or False
    
    # ========== 4. GERAR DADOS ESTRUTURADOS ==========
    jobs_data = []
    
    for idx, result in enumerate(results, start=1):
        # Calcular processing_time (tempo de produção)
        processing_time_hours = None
        if result.start_in_bottleneck_hours is not None and result.completion_date and result.completion_time and run.sequencing_start:
            completion_dt = datetime.combine(result.completion_date, result.completion_time)
            completion_hours = (completion_dt - run.sequencing_start).total_seconds() / 3600.0
            processing_time_hours = completion_hours - result.start_in_bottleneck_hours
        
        # Calcular final_completion_datetime usando remaining_post_injection_hours
        # final_completion_time_hours já inclui o tempo pós-injeção
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
        
        # RECALCULAR STATUS: Comparar data prometida com data final+pós
        # Status válidos são apenas "On Time" ou "Late"
        if result.scheduled_date and final_completion_datetime:
            # Comparar data prometida (fim do dia) com data final+pós
            scheduled_datetime = datetime.combine(result.scheduled_date, datetime.max.time())
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
        
        # Montar estrutura de dados
        job_data = {
            "order": idx,  # Ordem de execução (1..N)
            "production_line_id": result.production_line_id or "-",
            "machine_id": result.machine_id or "-",
            "sequence_pos": result.sequence_pos if result.sequence_pos is not None else "-",
            "job_index": result.job_index_solver or "-",
            "job_id": result.job_id or "-",
            "order_number": getattr(result, "order_number", None) or "-",
            "product_name": result.product_name or "-",
            "mold_name": result.mold_name or "-",
            "client_name": result.client_name or "-",
            "machine_name": result.machine_name or "-",
            "quantity": result.quantity if result.quantity is not None else "-",
            "processing_time_hours": round(processing_time_hours, 2) if processing_time_hours is not None else "-",
            "start_in_bottleneck_hours": round(result.start_in_bottleneck_hours, 2) if result.start_in_bottleneck_hours is not None else "-",
            "completion_time_hours": round((datetime.combine(result.completion_date, result.completion_time) - run.sequencing_start).total_seconds() / 3600.0, 2) if result.completion_date and result.completion_time and run.sequencing_start else "-",
            "final_completion_time_hours": round(result.final_completion_time_hours, 2) if result.final_completion_time_hours is not None else "-",
            "final_completion_datetime": final_completion_datetime.isoformat() if final_completion_datetime else "-",
            "promised_date": result.scheduled_date.isoformat() if result.scheduled_date else "-",
            "start_datetime": datetime.combine(result.actual_date, result.actual_time).isoformat() if result.actual_date and result.actual_time else (result.actual_date.isoformat() if result.actual_date else "-"),
            "completion_injection_datetime": datetime.combine(getattr(result, "completion_injection_date", None), getattr(result, "completion_injection_time", None)).isoformat() if getattr(result, "completion_injection_date", None) and getattr(result, "completion_injection_time", None) else "-",
            "tardiness_hours": round(tardiness_hours, 2) if tardiness_hours > 0 else 0,
            "status": calculated_status,
            "expected_revenue": round(result.expected_revenue, 2) if result.expected_revenue is not None else "-"
        }
        
        jobs_data.append(job_data)
    
    print(f"✅ Dados estruturados gerados: {len(jobs_data)} jobs")
    
    # ========== 5. SALVAR ARQUIVO (se save_file=true) ==========
    file_path = None
    if save_file:
        try:
            file_path = generate_schedule_report(run_id, db)
            print(f"✅ Arquivo salvo: {file_path}")
        except Exception as e:
            print(f"⚠️  Erro ao salvar arquivo: {e}")
            # Continua mesmo se falhar (best-effort)
    
    # ========== 6. RETORNAR RESPOSTA ==========
    response = {
        "run_id": run_id,
        "status": "success",
        "sequencing_start": run.sequencing_start.isoformat() if run.sequencing_start else None,
        "total_jobs": len(jobs_data),
        "on_time_jobs": run.on_time_jobs or 0,
        "machine_status": run.machine_status or "-",
        "ordering": "production_line_id ASC, machine_id ASC, sequence_pos ASC",
        "source": "100% Database",
        "generated_at": datetime.now().isoformat()
    }
    
    if format == "json":
        # Retornar JSON
        response["jobs"] = jobs_data
        response["file_path"] = file_path
        
        print(f"\n{'='*100}")
        print(f"✅ Retornando JSON com {len(jobs_data)} jobs")
        print(f"{'='*100}\n")
        
        return response
    
    elif format == "text":
        # Retornar texto (conteúdo do arquivo)
        # Se não salvou arquivo ainda, gerar agora
        if not file_path:
            try:
                file_path = generate_schedule_report(run_id, db)
                print(f"✅ Arquivo gerado para formato text: {file_path}")
            except Exception as e:
                print(f"⚠️  Erro ao gerar arquivo: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Erro ao gerar arquivo de log: {str(e)}"
                )
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            response["content"] = content
            response["file_path"] = file_path
            
            print(f"\n{'='*100}")
            print(f"✅ Retornando TEXT ({len(content)} caracteres)")
            print(f"{'='*100}\n")
            
            return response
        except Exception as e:
            print(f"❌ Erro ao ler arquivo: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Erro ao ler arquivo de log: {str(e)}"
            )


@router.get("/{run_id}/schedule-report")
def get_schedule_report(
    run_id: int = Path(..., description="ID do run"),
    format: str = Query("json", regex="^(json|text)$", description="Formato: json ou text"),
    db: Session = Depends(get_db)
):
    """
    Busca Schedule Report existente ou gera novo (método GET).
    
    Alias para POST, mas usando GET para facilitar acesso via browser.
    Sempre salva arquivo.
    """
    return create_schedule_report(
        run_id=run_id,
        format=format,
        save_file=True,  # GET sempre salva
        db=db
    )


@router.get("/{run_id}/schedule-report-frontend")
def get_schedule_report_frontend(
    run_id: int = Path(..., description="ID do run"),
    db: Session = Depends(get_db)
):
    """
    Endpoint JSON dedicado ao Front-End com todos os dados do schedule report.

    Inclui:
    - run_info
    - jobs (campos completos)
    - summary
    - métricas de capacidade:
      * Hs. De Disponibilidade
      * Hs. Nec. de Produção
      * Carga de Máquina (%)
    """
    try:
        data = generate_schedule_report_data(run_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar dados do report: {str(e)}")

    jobs = data.get("jobs", [])

    # Métricas para o front (mesma regra do schedule_report)
    completion_by_machine: Dict[int, float] = {}
    used_machines = set()
    last_completion_h = 0.0
    for job in jobs:
        machine_id = job.get("machine_id")
        completion_h = job.get("completion_time_hours")
        if machine_id in [None, "-"] or completion_h in [None, "-"]:
            continue
        try:
            machine_id_int = int(machine_id)
            completion_h_float = float(completion_h)
        except (TypeError, ValueError):
            continue
        used_machines.add(machine_id_int)
        if completion_h_float > last_completion_h:
            last_completion_h = completion_h_float
        prev = completion_by_machine.get(machine_id_int, 0.0)
        if completion_h_float > prev:
            completion_by_machine[machine_id_int] = completion_h_float

    hs_disponibilidade = int(last_completion_h * len(used_machines) + 0.999999) if used_machines else 0
    hs_necessarias = int(sum(completion_by_machine.values()) + 0.999999) if completion_by_machine else 0
    carga_maquina_percent = round((hs_necessarias / hs_disponibilidade) * 100.0, 2) if hs_disponibilidade > 0 else 0.0

    return {
        "run_id": run_id,
        "run_info": data.get("run_info", {}),
        "jobs": jobs,
        "summary": data.get("summary", {}),
        "metrics": {
            "hs_de_disponibilidade": hs_disponibilidade,
            "hs_nec_de_producao": hs_necessarias,
            "carga_de_maquina_percent": carga_maquina_percent,
        },
        "generated_at": datetime.now().isoformat(),
    }

