"""
Módulo para gerar logs formatados dos resultados do sequenciamento.
Cria arquivos de log legíveis em formato tabular.
"""

from datetime import datetime
from typing import List, Dict, Any
import os
from pathlib import Path


def format_table_row(columns: List[str], widths: List[int]) -> str:
    """Formata uma linha da tabela com as larguras especificadas."""
    return " | ".join(col.ljust(width) for col, width in zip(columns, widths))


def format_table_separator(widths: List[int]) -> str:
    """Cria uma linha separadora para a tabela."""
    return "-+-".join("-" * width for width in widths)


def generate_schedule_log(
    sequencing_date: datetime,
    results: List[Dict[str, Any]],
    run_metrics: Dict[str, Any],
    filename: str = None
) -> str:
    """
    Gera um arquivo de log formatado com os resultados do sequenciamento.
    
    Args:
        sequencing_date: Data e hora de início do sequenciamento
        results: Lista de dicionários com os resultados de cada job
        run_metrics: Métricas gerais da execução (setup_count, on_time_jobs, etc)
        filename: Nome do arquivo (opcional, gera automaticamente se não fornecido)
    
    Returns:
        Caminho do arquivo gerado
    """
    
    # Criar pasta de logs se não existir
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Gerar nome do arquivo se não fornecido
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"schedule_report_{timestamp}.txt"
    
    filepath = logs_dir / filename
    
    # Definir colunas e larguras
    columns = ["Ordem", "Job ID", "Cliente", "Produto", "Máquina", "Molde", 
               "Demanda", "Tempo (h)", "Final Completion (h)", "Início Gargalo (h)", "Dt Prometida", "Dt Início Gargalo", "Dt Conclusão", "Status"]
    widths = [6, 10, 20, 25, 15, 10, 10, 10, 18, 17, 16, 18, 16, 12]
    
    # Criar conteúdo do arquivo
    lines = []
    
    # Cabeçalho do relatório
    lines.append("=" * sum(widths) + "=" * (len(widths) - 1) * 3)
    lines.append("RELATÓRIO DE SEQUENCIAMENTO DE PRODUÇÃO".center(sum(widths) + (len(widths) - 1) * 3))
    lines.append("=" * sum(widths) + "=" * (len(widths) - 1) * 3)
    lines.append("")
    
    # Informações gerais
    lines.append(f"Data/Hora do Sequenciamento: {sequencing_date.strftime('%d/%m/%Y %H:%M:%S')}")
    lines.append(f"Total de Jobs: {len(results)}")
    lines.append(f"Jobs no Prazo: {run_metrics.get('on_time_jobs', 0)}")
    lines.append(f"Jobs Atrasados: {len(results) - run_metrics.get('on_time_jobs', 0)}")
    lines.append(f"Total de Setups: {run_metrics.get('setup_count', 0)}")
    lines.append(f"Setups Otimizados: {run_metrics.get('optimized_setups', 0)}")
    lines.append(f"Horas de Máquina Necessárias: {run_metrics.get('total_machine_hours', 0):.1f}h")
    lines.append(f"Status Geral: {run_metrics.get('machine_status', 'N/A')}")
    lines.append("")
    lines.append("=" * sum(widths) + "=" * (len(widths) - 1) * 3)
    lines.append("")
    
    # Cabeçalho da tabela
    lines.append(format_table_row(columns, widths))
    lines.append(format_table_separator(widths))
    
    # Dados dos jobs
    for result in results:
        # Formatar Job ID com prefixo
        job_id = result.get("job_id", "N/A")
        job_id_str = f"#{job_id}" if job_id != "N/A" else "N/A"
        
        # Calcular tempo em horas desde o início do sequenciamento
        completion_dt = result.get("completion_datetime")
        if completion_dt and hasattr(completion_dt, "timestamp"):
            time_hours = (completion_dt - sequencing_date).total_seconds() / 3600
            time_str = f"{time_hours:.1f}h"
        else:
            time_str = "N/A"
        
        # Final completion time (tempo total com pós-injeção)
        final_time = result.get("final_completion_time_hours")
        if final_time is not None:
            final_time_str = f"{final_time:.2f}h"
        else:
            final_time_str = "N/A"
        
        # Instante de início no gargalo (em horas desde sequencing_start)
        start_bottleneck = result.get("start_in_bottleneck_hours")
        if start_bottleneck is not None:
            start_bottleneck_str = f"{start_bottleneck:.2f}h"
        else:
            start_bottleneck_str = "N/A"
        
        # Formatar quantidade (se for 0 E cliente for "--", mostrar "--")
        quantity = result.get('quantity', 0)
        client_name = result.get("client_name", "N/A")
        if quantity == 0 and client_name == "--":
            quantity_str = "--"
        else:
            quantity_str = f"{quantity:,}".replace(',', '.')
        
        row = [
            str(result.get("order_index", "")).ljust(widths[0]),
            job_id_str.ljust(widths[1]),
            client_name[:widths[2]].ljust(widths[2]),
            result.get("product_name", "N/A")[:widths[3]].ljust(widths[3]),
            result.get("machine_name", "N/A")[:widths[4]].ljust(widths[4]),
            result.get("mold_name", "N/A")[:widths[5]].ljust(widths[5]),
            quantity_str.ljust(widths[6]),
            time_str.ljust(widths[7]),
            final_time_str.ljust(widths[8]),  # Final Completion (h)
            start_bottleneck_str.ljust(widths[9]),  # Início Gargalo (h)
            result.get("scheduled_date", "N/A").strftime("%d/%m/%y %H:%M") if hasattr(result.get("scheduled_date"), "strftime") else str(result.get("scheduled_date", "N/A"))[:widths[10]].ljust(widths[10]),
            result.get("start_datetime", "N/A").strftime("%d/%m/%y %H:%M") if hasattr(result.get("start_datetime"), "strftime") else str(result.get("start_datetime", "N/A"))[:widths[11]].ljust(widths[11]),
            result.get("completion_datetime", "N/A").strftime("%d/%m/%y %H:%M") if hasattr(result.get("completion_datetime"), "strftime") else str(result.get("completion_datetime", "N/A"))[:widths[12]].ljust(widths[12]),
            result.get("status", "N/A").ljust(widths[13])
        ]
        lines.append(" | ".join(row))
    
    lines.append(format_table_separator(widths))
    lines.append("")
    
    # Resumo por status (apenas jobs aplicáveis, excluir programmed_stop com status "--")
    applicable_results = [r for r in results if r.get("status") not in ["--", "N/A"]]
    on_time = sum(1 for r in applicable_results if r.get("status") == "On Time")
    late = sum(1 for r in applicable_results if r.get("status") == "Late")
    
    lines.append("RESUMO POR STATUS:")
    if applicable_results:
        lines.append(f"  [OK] No Prazo (On Time): {on_time} jobs ({on_time/len(applicable_results)*100:.1f}%)")
        lines.append(f"  [!!] Atrasados (Late): {late} jobs ({late/len(applicable_results)*100:.1f}%)")
    else:
        lines.append("  [OK] No Prazo (On Time): 0 jobs (0.0%)")
        lines.append("  [!!] Atrasados (Late): 0 jobs (0.0%)")
    
    # Se houver jobs não aplicáveis (programmed_stop), mencionar
    non_applicable = len(results) - len(applicable_results)
    if non_applicable > 0:
        lines.append(f"  [--] Outros (Paradas Programadas, etc.): {non_applicable} jobs")
    lines.append("")
    
    # Resumo financeiro se disponível
    total_revenue = sum(r.get("expected_revenue", 0) for r in results)
    if total_revenue > 0:
        lines.append("PREVISÃO DE RECEITA:")
        lines.append(f"  Total Esperado: R$ {total_revenue:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
        lines.append("")
    
    # Rodapé
    lines.append("=" * sum(widths) + "=" * (len(widths) - 1) * 3)
    lines.append(f"Relatório gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    lines.append("=" * sum(widths) + "=" * (len(widths) - 1) * 3)
    
    # Escrever arquivo
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"[OK] Log de sequenciamento salvo em: {filepath}")
    return str(filepath)


def generate_schedule_log_from_db(run_id: int, db) -> str:
    """
    Gera um log formatado a partir de uma execução salva no banco de dados.
    
    Args:
        run_id: ID da execução no banco
        db: Sessão do banco de dados
    
    Returns:
        Caminho do arquivo gerado
    """
    from app.models.production_schedule_run import ProductionScheduleRun
    from app.models.production_schedule_result import ProductionScheduleResult
    from datetime import datetime as dt
    
    # Buscar dados do banco
    run = db.query(ProductionScheduleRun).filter_by(id=run_id).first()
    if not run:
        raise ValueError(f"Execução {run_id} não encontrada no banco de dados")
    
    results_db = db.query(ProductionScheduleResult).filter_by(run_id=run_id).order_by(ProductionScheduleResult.order_index).all()
    
    # Converter para formato esperado - ORDENADO por production_line_id e job_index
    results = []
    for r in results_db:
        completion_datetime = dt.combine(r.completion_date, r.completion_time)
        scheduled_datetime = dt.combine(r.scheduled_date, dt.max.time().replace(microsecond=0))
        
        # Start datetime: combinar actual_date com actual_time (se existir)
        if r.actual_time:
            start_datetime = dt.combine(r.actual_date, r.actual_time)
        else:
            start_datetime = dt.combine(r.actual_date, dt.min.time())
        
        results.append({
            "order_index": r.order_index,
            "job_id": r.job_id,
            "client_name": r.client_name,
            "product_name": r.product_name,
            "machine_name": r.machine_name,
            "mold_name": r.mold_name,
            "quantity": r.quantity,
            "scheduled_date": scheduled_datetime,
            "start_datetime": start_datetime,  # Data/hora real de início
            "start_in_bottleneck_hours": r.start_in_bottleneck_hours,  # Horas desde sequencing_start
            "completion_datetime": completion_datetime,
            "status": r.status,
            "expected_revenue": r.expected_revenue,
            "final_completion_time_hours": r.final_completion_time_hours  # CAMPO OBRIGATÓRIO DO BD
        })
    
    run_metrics = {
        "on_time_jobs": run.on_time_jobs,
        "setup_count": run.setup_count,
        "optimized_setups": run.optimized_setups,
        "total_machine_hours": run.total_machine_hours,
        "machine_status": run.machine_status
    }
    
    return generate_schedule_log(
        sequencing_date=run.sequencing_start,
        results=results,
        run_metrics=run_metrics,
        filename=f"schedule_report_run_{run_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    )

