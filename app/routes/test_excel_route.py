from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Depends
from fastapi.responses import FileResponse
from datetime import datetime
import os
import json
import pandas as pd
from io import BytesIO
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.billing_configuration import BillingConfiguration
from algorithm.injection.excel_reader import process_excel_file
from algorithm.injection.calculate_processing_time import calculate_processing_time
from algorithm.injection.setup_matrix_calculator import build_setup_matrix
from algorithm.injection.solver_wrapper import solve_all_lines, prepare_solver_inputs
from algorithm.injection.solver_logger import log_solver_inputs, log_solver_results
from algorithm.injection.schedule_report_from_db import generate_schedule_report
from app.utils.save_schedule import save_test_solver_results_to_db

router = APIRouter(prefix="/test", tags=["Test"])


@router.post("/excel-read")
async def test_read_excel(
    file: UploadFile = File(..., description="Arquivo XLSX com os dados"),
    sequencing_date: datetime = Form(
        ..., description="Data e hora de início do sequenciamento (formato: YYYY-MM-DDTHH:MM:SS)"
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
    
    IMPORTANTE: Usa a configuração de faturamento ativa do sistema.
    Para configurar os dias e horários permitidos, use os endpoints em /billing-configuration/
    """

    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="O arquivo precisa ser .xlsx")

    try:
        # Buscar configuração de faturamento ativa
        billing_config = db.query(BillingConfiguration).filter(
            BillingConfiguration.is_active == True
        ).first()
        
        if not billing_config:
            raise HTTPException(
                status_code=400, 
                detail="Nenhuma configuração de faturamento ativa encontrada. "
                       "Crie uma configuração em /billing-configuration/"
            )
        
        # Extrair horário limite da configuração (se houver)
        default_billing_deadline_time = None
        if billing_config.billing_deadline_time:
            default_billing_deadline_time = billing_config.billing_deadline_time.strftime("%H:%M:%S")
        
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
            default_billing_deadline_time=default_billing_deadline_time,  # Extraído da configuração
            next_saturday_is_working=next_saturday_is_working,
            machine_states=machine_states or None,
            programmed_stops=programmed_stops or None,
            processing_calculation=processing_result,
        )
        
        # Adicionar informações da configuração de faturamento usada
        result["billing_configuration"] = {
            "rule_type": billing_config.rule_type.value,
            "billing_deadline_time": default_billing_deadline_time,
            "config_id": billing_config.id
        }

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

        # Rodar solver para todas as linhas em paralelo
        result["antes_do_solver"] = "Código chegou aqui"
        result["processing_result_keys"] = list(processing_result.keys())
        result["jobs_by_line_exists"] = "jobs_by_line" in processing_result
        result["solver_debug_step"] = "INICIANDO SOLVER"
        try:
            # Debug: verificar se jobs_by_line tem dados
            jobs_by_line_data = processing_result["jobs_by_line"]
            result["solver_debug_step"] = "JOBS_BY_LINE_OBTIDO"
            result["debug_solver"] = {
                "jobs_by_line_keys": list(jobs_by_line_data.keys()),
                "total_lines": len(jobs_by_line_data),
                "jobs_per_line": {pl_id: len(line_data.get("jobs", [])) for pl_id, line_data in jobs_by_line_data.items()}
            }
            
            if not jobs_by_line_data:
                result["solver_debug_step"] = "JOBS_BY_LINE_VAZIO"
                result["solver_warning"] = "Nenhuma linha de produção com jobs encontrada"
            else:
                # NOVA LÓGICA: Preparar inputs do solver (incluindo matriz de setup) ANTES de resolver
                result["solver_debug_step"] = "PREPARANDO_INPUTS_SOLVER"
                solver_inputs = prepare_solver_inputs(
                    jobs_by_line=jobs_by_line_data,
                    db=db
                )
                result["solver_debug_step"] = "INPUTS_PREPARADOS"
                
                result["debug_solver"]["solver_inputs_keys"] = list(solver_inputs.keys()) if solver_inputs else []
                result["debug_solver"]["solver_inputs_count"] = len(solver_inputs) if solver_inputs else 0
                
                # Gerar log dos inputs ANTES de resolver
                if solver_inputs:
                    result["solver_debug_step"] = "GERANDO_LOG_INPUTS"
                    input_log_path = log_solver_inputs(solver_inputs, jobs_by_line_data, db)
                    result["solver_input_log"] = input_log_path
                    result["solver_debug_step"] = "LOG_INPUTS_GERADO"
                    
                    # Agora rodar o solver com os inputs já preparados
                    result["solver_debug_step"] = "CHAMANDO_SOLVE_ALL_LINES"
                    solver_results = solve_all_lines(
                        jobs_by_line=jobs_by_line_data,
                        db=db,
                        max_workers=None  # Usa padrão do ThreadPoolExecutor
                    )
                    result["solver_debug_step"] = "SOLVE_ALL_LINES_RETORNOU"
                    
                    result["debug_solver"]["solver_results_keys"] = list(solver_results.keys()) if solver_results else []
                    result["debug_solver"]["solver_results_count"] = len(solver_results) if solver_results else 0
                    
                    # Gerar logs dos resultados
                    if solver_results:
                        result["solver_debug_step"] = "GERANDO_LOG_RESULTADOS"
                        result_log_path = log_solver_results(solver_results)
                        result["solver_result_log"] = result_log_path
                        result["solver_debug_step"] = "LOG_RESULTADOS_GERADO"
                        
                        # Salvar resultados no banco de dados
                        try:
                            result["solver_debug_step"] = "SALVANDO_NO_BANCO"
                            run_saved, schedule_report_path = save_test_solver_results_to_db(
                                db=db,
                                sequencing_date=sequencing_date,
                                solver_results=solver_results,
                                jobs_by_line=jobs_by_line_data,
                                next_saturday_is_working=next_saturday_is_working
                            )
                            result["solver_debug_step"] = "SALVAMENTO_CONCLUIDO"
                            result["saved_run_id"] = run_saved.id
                            result["saved_results_count"] = len(run_saved.results)
                            result["schedule_report_path"] = schedule_report_path  # caminho do log na pasta logs
                            result["solver_debug_step"] = "SCHEDULE_REPORT_GERADO_EM_SAVE_SCHEDULE"
                        except Exception as save_error:
                            import traceback
                            result["solver_debug_step"] = "ERRO_AO_SALVAR"
                            result["save_error"] = str(save_error)
                            result["save_error_traceback"] = traceback.format_exc()
                            # Não falhar a requisição se o salvamento der erro
                    else:
                        result["solver_debug_step"] = "SOLVER_RESULTS_VAZIO"
                        result["solver_warning"] = "Nenhum resultado do solver foi gerado"
                    
                    # Adicionar resumo dos resultados ao retorno
                    result["solver_results"] = {
                        "total_lines_solved": len(solver_results) if solver_results else 0,
                        "results": {
                            pl_id: {
                                "status": r.get("status", "Unknown"),
                                "objective": r.get("objective", 0.0),
                                "error": r.get("error") if "error" in r else None
                            }
                            for pl_id, r in solver_results.items()
                        } if solver_results else {}
                    }
                    
                    # Adicionar jobs com final_completion_time ao JSON de resposta
                    result["jobs_with_final_completion"] = []
                    for pl_id, solver_result in solver_results.items():
                        if "error" not in solver_result:
                            inputs = solver_result.get("inputs", {})
                            ordered_jobs = inputs.get("ordered_jobs", [])
                            for job in ordered_jobs:
                                if job.get("type") == "excel":  # Apenas jobs reais
                                    result["jobs_with_final_completion"].append({
                                        "job_index": job.get("job_index"),
                                        "product_name": job.get("product_name"),
                                        "mold_name": job.get("mold_name"),
                                        "client_name": job.get("client_name"),
                                        "final_completion_time_hours": job.get("final_completion_time_hours")
                                    })
                    result["solver_debug_step"] = "SOLVER_COMPLETO"
                else:
                    result["solver_debug_step"] = "SOLVER_INPUTS_VAZIO"
                    result["solver_warning"] = "Nenhum input do solver foi preparado"
                
        except Exception as e:
            import traceback
            result["solver_debug_step"] = f"ERRO_CAPTURADO: {str(e)}"
            result["solver_error"] = str(e)
            result["solver_error_traceback"] = traceback.format_exc()
            # Não falhar a requisição se o solver der erro

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar arquivo: {str(e)}")


@router.post("/logs/cleanup")
async def cleanup_logs(keep_recent: int = 5):
    """
    Limpa logs antigos, mantendo apenas os N mais recentes de cada tipo.
    
    Args:
        keep_recent: Número de arquivos mais recentes para manter (padrão: 5)
    """
    from pathlib import Path
    from algorithm.injection.log_cleanup import cleanup_old_logs
    
    base_dir = Path(__file__).resolve().parents[1]
    log_dir = base_dir / "logs"
    
    stats = cleanup_old_logs(log_dir, keep_recent=keep_recent)
    
    return {
        "message": "Limpeza de logs concluída",
        "deleted": stats["deleted"],
        "kept": stats["kept"],
        "by_type": stats["by_type"]
    }


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
