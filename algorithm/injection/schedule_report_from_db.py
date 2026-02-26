"""
Gerador de Schedule Report 100% baseado no Banco de Dados.

REGRAS:
- Fonte única da verdade: banco de dados
- NUNCA usar JSON do solver, Excel ou estruturas intermediárias
- Sempre gerar arquivo com timestamp único em /logs
- Ordenação obrigatória: production_line_id ASC, machine_id ASC, sequence_pos ASC
- NO LOG: ocultar jobs com start_in_bottleneck_hours <= 0, EXCETO paradas programadas
"""

import math
import os
from pathlib import Path
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.models.production_schedule_run import ProductionScheduleRun
from app.models.production_schedule_result import ProductionScheduleResult
from app.models.regular_shift import RegularShift
from app.models.holiday import Holiday
from algorithm.injection.due_date_calculator import (
    add_working_hours,
    calculate_billing_date,
)


def generate_schedule_report(run_id: int, db: Session) -> str:
    """
    Gera o schedule_report 100% a partir do banco de dados.
    
    FONTE DA VERDADE: Apenas dados do BD.
    ORDENAÇÃO: production_line_id ASC, machine_id ASC, sequence_pos ASC
    
    Args:
        run_id: ID do run no banco de dados
        db: Sessão do banco de dados
        
    Returns:
        Caminho do arquivo de log gerado (sempre em /logs com timestamp)
        
    Raises:
        ValueError: Se o run_id não existir no banco
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
        print(f"⚠️  Colunas de compatibilidade do schedule_report (aviso): {e}")

    # ========== 1. BUSCAR RUN NO BANCO ==========
    run = db.query(ProductionScheduleRun).filter(
        ProductionScheduleRun.id == run_id
    ).first()
    
    if not run:
        # Mesmo sem run, gerar log informando o erro
        return _generate_error_log(run_id, "Run não encontrado no banco de dados")
    
    # ========== 2. BUSCAR RESULTADOS COM ORDENAÇÃO OBRIGATÓRIA ==========
    # ORDENAÇÃO OBRIGATÓRIA: production_line_id ASC, machine_id ASC, sequence_pos ASC
    results = db.query(ProductionScheduleResult).filter(
        ProductionScheduleResult.run_id == run_id
    ).order_by(
        ProductionScheduleResult.production_line_id.asc(),
        ProductionScheduleResult.machine_id.asc(),
        ProductionScheduleResult.sequence_pos.asc()
    ).all()
    
    # Se não houver resultados, ainda gerar log
    if not results:
        return _generate_empty_log(run_id, run)
    
    # ========== 2.5. BUSCAR INFORMAÇÕES DE JORNADA DE TRABALHO ==========
    # Necessário para calcular data/hora final considerando jornada de trabalho
    regular_shifts = db.query(RegularShift).all()
    holidays = [h.date for h in db.query(Holiday).all()]
    next_saturday_is_working = getattr(run, "next_saturday_is_working", False) or False
    
    # ========== 3. GERAR ARQUIVO COM TIMESTAMP ÚNICO ==========
    # SEMPRE escrever na pasta logs (raiz do projeto; fallback: cwd/logs)
    base_dir = Path(__file__).resolve().parents[2]  # .../Quant_injectors
    logs_dir = base_dir / "logs"
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / ".write_test").write_text("", encoding="utf-8")
        (logs_dir / ".write_test").unlink(missing_ok=True)
    except Exception:
        logs_dir = Path.cwd() / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"schedule_report_{run_id}_{timestamp}.txt"
    log_filepath = logs_dir / log_filename
    
    # ========== 4. GERAR CONTEÚDO DO LOG ==========
    lines = []
    
    # Cabeçalho
    lines.append("=" * 200)
    lines.append("SCHEDULE REPORT - GERADO 100% DO BANCO DE DADOS".center(200))
    lines.append("=" * 200)
    lines.append("")
    lines.append(f"Run ID: {run_id}")
    lines.append(f"Data/Hora de Início: {run.sequencing_start.strftime('%d/%m/%Y %H:%M:%S') if run.sequencing_start else 'N/A'}")
    lines.append(f"Data de Criação: {run.created_at.strftime('%d/%m/%Y %H:%M:%S') if run.created_at else 'N/A'}")
    lines.append(f"Status Geral: {run.machine_status or '-'}")
    lines.append("")
    
    # Métricas (considerar TODOS os results, antes de filtrar)
    lines.append("MÉTRICAS:")
    lines.append(f"  Total de Jobs (BD): {len(results)}")
    lines.append(f"  Jobs no Prazo: {run.on_time_jobs or 0}")
    lines.append(f"  Jobs Atrasados: {len(results) - (run.on_time_jobs or 0)}")
    lines.append(f"  Total de Setups: {run.setup_count or 0}")
    lines.append(f"  Setups Otimizados: {run.optimized_setups or 0}")
    lines.append(f"  Horas de Máquina Totais: {run.total_machine_hours or 0:.1f}h")
    lines.append(f"  Prazo Máximo: {run.max_deadline_hours or 0:.1f}h")
    lines.append("")
    
    lines.append("=" * 200)
    lines.append("")
    
    # Tabela de resultados (Dt Prometida = data + hora limite de faturamento da planilha)
    columns = [
        "Ordem", "Job ID", "Pedido", "Linha", "Cliente", "Produto", "Máquina", "Molde",
        "Demanda", "Início (h)", "Conclusão (h)", "Final+Pós (h)",
        "Dt Prometida", "Dt Início", "Dt Final Inj", "Dt Final+Pós", "Dt Faturamento", "Status", "Receita"
    ]
    widths = [6, 8, 10, 6, 20, 25, 15, 12, 10, 12, 14, 14, 16, 16, 16, 16, 14, 10, 12]
    
    # Cabeçalho da tabela
    header = " | ".join(col.ljust(w) for col, w in zip(columns, widths))
    lines.append(header)
    lines.append("-+-".join("-" * w for w in widths))
    
    # ========== FILTRAR PARA O LOG ==========
    # TODOS os jobs que estão no BD aparecem no log
    # (State machines com completed=True já foram filtrados na persistência)
    filtered_results = results
    filtered_count = 0
    
    # Linhas de dados (ORDEM JÁ VEM DO BD COM ORDENAÇÃO CORRETA)
    # REATRIBUIR "Ordem" como 1..N (apenas para exibição)
    for display_order, result in enumerate(filtered_results, start=1):
        # Valores do BD (se NULL, mostrar "-")
        # MOSTRAR job_index_solver (SEQUÊNCIA DO SOLVER) e NÃO job_id (composition_line_id)!
        job_id = result.job_index_solver if result.job_index_solver is not None else "-"
        order_number = result.order_number if getattr(result, "order_number", None) else "-"
        line_id = result.production_line_id if result.production_line_id is not None else "-"
        client = (result.client_name or "-")[:20]
        product = (result.product_name or "-")[:25]
        machine = (result.machine_name or "-")[:15]
        mold = (result.mold_name or "-")[:12]
        quantity = f"{result.quantity:,}".replace(',', '.') if result.quantity else "-"
        
        # Tempos (em horas desde sequencing_start)
        start_h = f"{result.start_in_bottleneck_hours:.2f}h" if result.start_in_bottleneck_hours is not None else "-"
        
        # Conclusão (h): usar valor bruto do solver (Fim), sem recalcular.
        completion_h = getattr(result, "completion_time_hours", None)
        completion_str = f"{completion_h:.2f}h" if completion_h is not None else "-"
        
        final_h = f"{result.final_completion_time_hours:.2f}h" if result.final_completion_time_hours is not None else "-"
        
        # Calcular data/hora final usando remaining_post_injection_hours
        # final_completion_time_hours já inclui o tempo pós-injeção
        final_completion_datetime_str = "-"
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
                final_completion_datetime_str = final_completion_datetime.strftime("%d/%m/%y %H:%M")
            except Exception as e:
                print(f"⚠️  Erro ao calcular final_completion_datetime para job {result.job_id}: {e}")
                final_completion_datetime_str = "-"
        
        # Data e hora prometida (Data Limite + Horário Limite de Faturamento da planilha)
        scheduled_time_val = getattr(result, "scheduled_time", None)
        if result.scheduled_date and scheduled_time_val:
            scheduled = datetime.combine(result.scheduled_date, scheduled_time_val).strftime("%d/%m/%y %H:%M")
        elif result.scheduled_date:
            scheduled = result.scheduled_date.strftime("%d/%m/%y")
        else:
            scheduled = "-"
        
        if result.actual_date and result.actual_time:
            start_dt = datetime.combine(result.actual_date, result.actual_time)
            start_str = start_dt.strftime("%d/%m/%y %H:%M")
        elif result.actual_date:
            start_str = result.actual_date.strftime("%d/%m/%y")
        else:
            start_str = "-"

        # Data/hora de finalização na injetora (sem pós)
        completion_inj_date = getattr(result, "completion_injection_date", None) or result.completion_date
        completion_inj_time = getattr(result, "completion_injection_time", None) or result.completion_time
        if completion_inj_date and completion_inj_time:
            completion_inj_str = datetime.combine(completion_inj_date, completion_inj_time).strftime("%d/%m/%y %H:%M")
        elif completion_inj_date:
            completion_inj_str = completion_inj_date.strftime("%d/%m/%y")
        else:
            completion_inj_str = "-"
        
        # Calcular data de faturamento
        # SEMPRE calcular baseado na data/hora de término do job e aplicar as regras de faturamento
        # Prioridade: 1) final_completion_datetime (término incluindo pós-injeção), 
        #             2) completion_date + completion_time (término da injeção),
        #             3) billing_date do BD (fallback)
        billing_date_str = "-"
        job_completion_datetime = None
        
        # Prioridade 1: Usar final_completion_datetime (término completo incluindo pós-injeção)
        if final_completion_datetime:
            job_completion_datetime = final_completion_datetime
        # Prioridade 2: Usar completion_date + completion_time (término da injeção)
        elif result.completion_date and result.completion_time:
            job_completion_datetime = datetime.combine(result.completion_date, result.completion_time)
        
        # Calcular data de faturamento usando a data/hora de término e aplicando as regras
        if job_completion_datetime:
            try:
                billing_date = calculate_billing_date(job_completion_datetime, db)
                billing_date_str = billing_date.strftime("%d/%m/%y")
            except Exception as e:
                print(f"⚠️  Erro ao calcular billing_date para job {result.job_id}: {e}")
                billing_date_str = "-"
        elif result.billing_date:
            # Fallback: se não tiver nenhuma data de término, usar o valor do BD
            billing_date_str = result.billing_date.strftime("%d/%m/%y")
        
        # RECALCULAR STATUS: Comparar data+hora prometida com data final+pós
        # Status válidos são apenas "On Time" ou "Late"
        if result.scheduled_date and final_completion_datetime:
            # Usar hora prometida quando existir (planilha), senão fim do dia
            promised_time = getattr(result, "scheduled_time", None) or datetime.max.time()
            scheduled_datetime = datetime.combine(result.scheduled_date, promised_time)
            status = "On Time" if final_completion_datetime <= scheduled_datetime else "Late"
        elif result.status in ["On Time", "Late"]:
            # Se já tiver status válido no BD, usar
            status = result.status
        else:
            # Se não tiver dados suficientes ou status inválido (ex: "State Machine"), usar "-"
            status = "-"
        revenue = f"R$ {result.expected_revenue:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') if result.expected_revenue else "-"
        
        # Montar linha
        row_data = [
            str(display_order),  # ORDEM REATRIBUÍDA COMO 1..N
            str(job_id),
            str(order_number),
            str(line_id),
            client,
            product,
            machine,
            mold,
            quantity,
            start_h,
            completion_str,
            final_h,
            scheduled,
            start_str,
            completion_inj_str,
            final_completion_datetime_str,
            billing_date_str,
            status,
            revenue
        ]
        
        row = " | ".join(val.ljust(w) for val, w in zip(row_data, widths))
        lines.append(row)
    
    lines.append("-+-".join("-" * w for w in widths))
    lines.append("")
    
    # Resumo (recalcular status para todos os jobs para estatísticas corretas)
    lines.append("RESUMO:")
    lines.append(f"  📊 Jobs exibidos no log: {len(filtered_results)}")
    
    # Recalcular status para todos os jobs (comparando data prometida com data final+pós)
    on_time = 0
    late = 0
    applicable_count = 0
    
    for result in filtered_results:
        # Pular jobs sem status válido (--, -, None, ou status inválido como "State Machine")
        # Status válidos são apenas "On Time" ou "Late"
        if result.status not in ["On Time", "Late"]:
            continue
        
        # Recalcular status comparando data+hora prometida com data final+pós
        if result.scheduled_date and result.final_completion_time_hours is not None and run.sequencing_start:
            try:
                final_completion_datetime = add_working_hours(
                    start_datetime=run.sequencing_start,
                    hours_to_add=result.final_completion_time_hours,
                    regular_shifts=regular_shifts,
                    holidays=holidays,
                    reference_date=run.sequencing_start.date() if run.sequencing_start else None,
                    next_saturday_is_working=next_saturday_is_working
                )
                promised_time = getattr(result, "scheduled_time", None) or datetime.max.time()
                scheduled_datetime = datetime.combine(result.scheduled_date, promised_time)
                calculated_status = "On Time" if final_completion_datetime <= scheduled_datetime else "Late"
                
                applicable_count += 1
                if calculated_status == "On Time":
                    on_time += 1
                else:
                    late += 1
            except Exception as e:
                print(f"⚠️  Erro ao recalcular status para job {result.job_id}: {e}")
                continue
    
    if applicable_count > 0:
        lines.append(f"  [OK] No Prazo: {on_time} jobs ({on_time/applicable_count*100:.1f}%)")
        lines.append(f"  [!!] Atrasados: {late} jobs ({late/applicable_count*100:.1f}%)")

    # Métricas solicitadas para capacity/load da simulação (baseadas em Conclusão (h))
    completion_by_machine = {}
    used_machines = set()
    last_completion_h = 0.0
    for r in filtered_results:
        completion_h = getattr(r, "completion_time_hours", None)
        machine_id = getattr(r, "machine_id", None)
        if completion_h is None or machine_id is None:
            continue
        completion_h = float(completion_h)
        used_machines.add(machine_id)
        if completion_h > last_completion_h:
            last_completion_h = completion_h
        current = completion_by_machine.get(machine_id, 0.0)
        if completion_h > current:
            completion_by_machine[machine_id] = completion_h

    hs_disponibilidade = math.ceil(last_completion_h * len(used_machines))
    hs_necessarias = math.ceil(sum(completion_by_machine.values()))
    carga_maquina = round((hs_necessarias / hs_disponibilidade) * 100.0, 2) if hs_disponibilidade > 0 else 0.0

    lines.append(f"  Hs. De Disponibilidade: {hs_disponibilidade:.2f}h")
    lines.append(f"  Hs. Nec. de Produção: {hs_necessarias:.2f}h")
    lines.append(f"  Carga de Máquina: {carga_maquina:.2f}%")
    
    # Receita total considera TODOS os results (não filtrados)
    total_revenue = sum(r.expected_revenue or 0 for r in results)
    if total_revenue > 0:
        lines.append(f"  💰 Receita Total Esperada: R$ {total_revenue:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
    
    lines.append("")
    
    # Rodapé
    lines.append("=" * 200)
    lines.append(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    lines.append(f"Fonte: 100% Banco de Dados (run_id={run_id})")
    lines.append(f"Query/Ordenação: ORDER BY production_line_id ASC, machine_id ASC, sequence_pos ASC")
    lines.append("=" * 200)
    
    # ========== 5. SALVAR ARQUIVO (OBRIGATÓRIO) ==========
    content = '\n'.join(lines)
    with open(log_filepath, 'w', encoding='utf-8') as f:
        f.write(content)
        f.flush()
        if hasattr(f, 'fileno'):
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
    if not log_filepath.exists():
        raise RuntimeError(f"Schedule report não foi criado: {log_filepath.absolute()}")
    return str(log_filepath.absolute())


def write_schedule_report_from_memory(
    run_id: int,
    sequencing_start: datetime,
    all_results: list,
    created_at: Optional[datetime] = None,
    machine_status: str = "Completed",
) -> str:
    """
    Gera o arquivo de schedule report a partir dos dados em memória (fallback quando o BD falha).
    O LOG É SUPREMO: este método garante que o arquivo seja sempre criado.
    """
    base_dir = Path(__file__).resolve().parents[2]
    logs_dir = base_dir / "logs"
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        logs_dir = Path.cwd() / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"schedule_report_{run_id}_{timestamp}.txt"
    log_filepath = logs_dir / log_filename

    lines = []
    lines.append("=" * 200)
    lines.append("SCHEDULE REPORT - GERADO A PARTIR DE DADOS EM MEMÓRIA (FALLBACK)".center(200))
    lines.append("=" * 200)
    lines.append("")
    lines.append(f"Run ID: {run_id}")
    lines.append(f"Data/Hora de Início: {sequencing_start.strftime('%d/%m/%Y %H:%M:%S') if sequencing_start else 'N/A'}")
    lines.append(f"Data de Criação: {created_at.strftime('%d/%m/%Y %H:%M:%S') if created_at else 'N/A'}")
    lines.append(f"Status Geral: {machine_status or '-'}")
    lines.append("")
    lines.append(f"MÉTRICAS:")
    lines.append(f"  Total de Jobs: {len(all_results)}")
    # Métricas de disponibilidade/necessidade para manter consistência no fallback
    completion_by_machine = {}
    used_machines = set()
    last_completion_h = 0.0
    for r in all_results:
        completion_h = r.get("completion_time_hours")
        machine_id = r.get("machine_id")
        if completion_h is None or machine_id is None:
            continue
        completion_h = float(completion_h)
        used_machines.add(machine_id)
        if completion_h > last_completion_h:
            last_completion_h = completion_h
        current = completion_by_machine.get(machine_id, 0.0)
        if completion_h > current:
            completion_by_machine[machine_id] = completion_h
    hs_disponibilidade = math.ceil(last_completion_h * len(used_machines))
    hs_necessarias = math.ceil(sum(completion_by_machine.values()))
    carga_maquina = round((hs_necessarias / hs_disponibilidade) * 100.0, 2) if hs_disponibilidade > 0 else 0.0
    lines.append(f"  Hs. De Disponibilidade: {hs_disponibilidade:.2f}h")
    lines.append(f"  Hs. Nec. de Produção: {hs_necessarias:.2f}h")
    lines.append(f"  Carga de Máquina: {carga_maquina:.2f}%")
    lines.append("")
    lines.append("=" * 200)
    lines.append("")

    columns = [
        "Ordem", "Job ID", "Linha", "Cliente", "Produto", "Máquina", "Molde",
        "Demanda", "Início (h)", "Final+Pós (h)", "Dt Prometida", "Dt Início", "Status", "Receita"
    ]
    widths = [6, 8, 6, 20, 25, 15, 12, 10, 12, 14, 16, 16, 10, 12]
    header = " | ".join(col.ljust(w) for col, w in zip(columns, widths))
    lines.append(header)
    lines.append("-+-".join("-" * w for w in widths))

    for display_order, r in enumerate(all_results, start=1):
        sd = r.get("scheduled_date")
        st = r.get("scheduled_time")
        if sd and st:
            scheduled = datetime.combine(sd, st).strftime("%d/%m/%y %H:%M") if hasattr(st, "isoformat") else f"{sd}"
        elif sd:
            scheduled = sd.strftime("%d/%m/%y") if hasattr(sd, "strftime") else str(sd)
        else:
            scheduled = "-"
        actual_d = r.get("actual_date")
        actual_t = r.get("actual_time")
        if actual_d and actual_t:
            start_str = datetime.combine(actual_d, actual_t).strftime("%d/%m/%y %H:%M")
        elif actual_d:
            start_str = actual_d.strftime("%d/%m/%y") if hasattr(actual_d, "strftime") else str(actual_d)
        else:
            start_str = "-"
        start_h = f"{r.get('start_in_bottleneck_hours', 0):.2f}h" if r.get("start_in_bottleneck_hours") is not None else "-"
        final_h = f"{r.get('final_completion_time_hours', 0):.2f}h" if r.get("final_completion_time_hours") is not None else "-"
        quantity = f"{r.get('quantity', 0):,}".replace(",", ".") if r.get("quantity") is not None else "-"
        revenue = r.get("expected_revenue")
        revenue_str = f"R$ {revenue:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if revenue is not None else "-"
        row = [
            str(display_order),
            str(r.get("job_index_solver", "-")),
            str(r.get("production_line_id", "-")),
            (r.get("client_name") or "-")[:20],
            (r.get("product_name") or "-")[:25],
            (r.get("machine_name") or "-")[:15],
            (r.get("mold_name") or "-")[:12],
            quantity,
            start_h,
            final_h,
            scheduled,
            start_str,
            r.get("status", "-"),
            revenue_str,
        ]
        lines.append(" | ".join(str(v).ljust(w) for v, w in zip(row, widths)))

    lines.append("-+-".join("-" * w for w in widths))
    lines.append("")
    lines.append("=" * 200)
    lines.append(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    lines.append(f"Fonte: Dados em memória (fallback) - run_id={run_id}")
    lines.append("=" * 200)

    content = "\n".join(lines)
    with open(log_filepath, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        if hasattr(f, "fileno"):
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
    return str(log_filepath.absolute())


def _generate_error_log(run_id: int, error_message: str) -> str:
    """Gera log de erro quando run não é encontrado."""
    base_dir = Path(__file__).resolve().parents[2]
    logs_dir = base_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"schedule_report_{run_id}_{timestamp}.txt"
    log_filepath = logs_dir / log_filename
    
    lines = [
        "=" * 100,
        "SCHEDULE REPORT - ERRO".center(100),
        "=" * 100,
        "",
        f"Run ID: {run_id}",
        f"Erro: {error_message}",
        "",
        "=" * 100,
        f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        "=" * 100
    ]
    
    with open(log_filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"⚠️  Schedule report (erro) gerado: {log_filepath}")
    return str(log_filepath)


def _generate_empty_log(run_id: int, run: ProductionScheduleRun) -> str:
    """Gera log quando não há resultados para o run."""
    base_dir = Path(__file__).resolve().parents[2]
    logs_dir = base_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"schedule_report_{run_id}_{timestamp}.txt"
    log_filepath = logs_dir / log_filename
    
    lines = [
        "=" * 100,
        "SCHEDULE REPORT - SEM RESULTADOS".center(100),
        "=" * 100,
        "",
        f"Run ID: {run_id}",
        f"Data/Hora de Início: {run.sequencing_start.strftime('%d/%m/%Y %H:%M:%S') if run.sequencing_start else 'N/A'}",
        f"Status: {run.machine_status or 'N/A'}",
        "",
        "⚠️  Nenhum resultado encontrado no banco de dados para este run.",
        "",
        "=" * 100,
        f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        f"Fonte: 100% Banco de Dados (run_id={run_id})",
        "=" * 100
    ]
    
    with open(log_filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"⚠️  Schedule report (vazio) gerado: {log_filepath}")
    return str(log_filepath)
