"""
Gera logs dos inputs e outputs do solver.
"""

from pathlib import Path
from datetime import datetime
from typing import Dict, List
import json
from sqlalchemy.orm import Session, joinedload

from app.models.composition_line import CompositionLine


def log_solver_inputs(
    solver_inputs: Dict[int, Dict],
    jobs_by_line: Dict[int, Dict],
    db: Session
) -> str:
    """
    Gera um log textual dos inputs do solver (formato similar à imagem de referência).
    
    Retorna o caminho do arquivo de log gerado.
    """
    base_dir = Path(__file__).resolve().parents[2]
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Limpeza automática de logs antigos antes de criar novo (apenas uma vez por execução)
    try:
        from algorithm.injection.log_cleanup import auto_cleanup_logs
        auto_cleanup_logs(base_dir, keep_recent=5)
    except Exception as e:
        print(f"Erro na limpeza de logs: {e}")
    
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"solver_inputs_{timestamp_str}.txt"
    
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("INPUTS DO SOLVER - PARÂMETROS DOS JOBS\n")
        f.write("=" * 80 + "\n\n")
        
        for pl_id, solver_input in solver_inputs.items():
            pl_name = jobs_by_line[pl_id]["production_line_name"]
            f.write(f"\n{'=' * 80}\n")
            f.write(f"LINHA DE PRODUÇÃO: {pl_name} (ID: {pl_id})\n")
            f.write(f"{'=' * 80}\n\n")
            
            jobs = solver_input["jobs"]
            machines = solver_input["machines"]
            processing = solver_input["processing"]
            due = solver_input["due"]
            priority = solver_input["priority"]
            setup3 = solver_input["setup3"]
            ordered_jobs = solver_input["ordered_jobs"]
            
            # Tabela de parâmetros dos jobs
            f.write("PARÂMETROS DOS JOBS:\n")
            f.write("=" * 100 + "\n")
            
            # Cabeçalho - calcular larguras
            col_width_job = 6
            col_width_machine = 18
            col_width_priority = 12
            col_width_deadline = 22
            col_width_type = 20
            
            # Linha de cabeçalho
            header = f"{'Job':<{col_width_job}}"
            for m_idx in machines:
                header += f"{f'Tempo Prod (h) Maq {m_idx}':<{col_width_machine}}"
            header += f"{'Prioridade':<{col_width_priority}}"
            header += f"{'Prazo nas injetoras (h)':<{col_width_deadline}}"
            header += f"{'Tipo':<{col_width_type}}\n"
            f.write(header)
            f.write("-" * 100 + "\n")
            
            # Dados dos jobs
            for job_data in ordered_jobs:
                j_idx = job_data["job_index"]
                job_type = job_data.get("type", "unknown")
                
                # Traduzir tipo para português
                type_map = {
                    "dummy": "Dummy",
                    "excel": "Excel",
                    "state_machine": "State Machine",
                    "programmed_stop": "Parada Programada"
                }
                job_type_display = type_map.get(job_type, job_type)
                
                line = f"{j_idx:<{col_width_job}}"
                
                # Production time por máquina
                for m_idx in machines:
                    processing_time_by_machine = job_data.get("processing_time_by_machine", {})
                    if isinstance(processing_time_by_machine, dict):
                        prod_time = processing_time_by_machine.get(m_idx, 0.0)
                    else:
                        # Se for lista, tentar buscar
                        prod_time = 0.0
                        if isinstance(processing_time_by_machine, list):
                            for m_data in processing_time_by_machine:
                                if isinstance(m_data, dict) and m_data.get("machine_id") == m_idx:
                                    prod_time = m_data.get("production_time", 0.0)
                                    break
                    
                    if prod_time >= 99999.0:
                        line += f"{'99999.0':<{col_width_machine}}"
                    else:
                        line += f"{prod_time:<{col_width_machine}.1f}"
                
                # Priority
                prio = priority.get(j_idx, 99)
                line += f"{prio:<{col_width_priority}}"
                
                # Deadline
                deadline = due.get(j_idx, 0.0)
                if deadline is None or (isinstance(deadline, float) and deadline != deadline):  # NaN check
                    line += f"{'N/A':<{col_width_deadline}}"
                else:
                    try:
                        deadline_float = float(deadline)
                        line += f"{deadline_float:<{col_width_deadline}.2f}"
                    except (TypeError, ValueError):
                        line += f"{'N/A':<{col_width_deadline}}"
                
                # Tipo do job
                line += f"{job_type_display:<{col_width_type}}\n"
                
                f.write(line)
            
            f.write("=" * 100 + "\n\n")
            
            # Matriz de Setup
            f.write("MATRIZ DE SETUP (tempo de troca entre jobs, em horas):\n")
            f.write("=" * 100 + "\n\n")
            
            # Agrupar por máquina
            for m_idx in machines:
                f.write(f"MÁQUINA {m_idx}:\n")
                f.write("-" * 100 + "\n")
                
                # Cabeçalho da matriz
                header_setup = f"{'De\\Para':<8}"
                for j in jobs:
                    header_setup += f"{j:>8}"
                header_setup += "\n"
                f.write(header_setup)
                f.write("-" * (8 + len(jobs) * 9) + "\n")
                
                # Dados da matriz
                for i in jobs:
                    line_setup = f"{i:<8}"
                    for j in jobs:
                        setup_time = setup3.get((i, j, m_idx), 0.0)
                        line_setup += f"{setup_time:>8.2f}"
                    line_setup += "\n"
                    f.write(line_setup)
                
                f.write("\n")
            
            f.write("=" * 100 + "\n\n")
    
    return str(log_file)


def log_solver_results(
    solver_results: Dict[int, Dict]
) -> str:
    """
    Gera um log textual DETALHADO dos resultados do solver para validação.
    
    Inclui:
    - Sequências de execução por máquina
    - Detalhes de cada job (produto, cliente, molde)
    - Tempos de produção, setup e término
    - Análise de atrasos e prazos
    - Resumo de utilização das máquinas
    - Validações de consistência
    
    Retorna o caminho do arquivo de log gerado.
    """
    print(f"[LOG] log_solver_results chamado com {len(solver_results)} resultados")
    for pl_id in solver_results.keys():
        print(f"[LOG] - Linha {pl_id}: {solver_results[pl_id].get('production_line_name', 'N/A')}")
    
    base_dir = Path(__file__).resolve().parents[2]
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Limpeza automática de logs antigos antes de criar novo
    try:
        from algorithm.injection.log_cleanup import auto_cleanup_logs
        auto_cleanup_logs(base_dir, keep_recent=5)
    except Exception as e:
        print(f"Erro na limpeza de logs: {e}")
    
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"solver_results_{timestamp_str}.txt"
    
    print(f"[LOG] Criando arquivo de log: {log_file}")
    
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("=" * 120 + "\n")
        f.write("RESULTADOS DO SOLVER - SEQUENCIAMENTO DETALHADO PARA VALIDAÇÃO\n")
        f.write("=" * 120 + "\n\n")
        
        print(f"[LOG] Iterando por {len(solver_results)} resultados para escrever no arquivo...")
        for pl_id, result in solver_results.items():
            try:
                print(f"[LOG] Escrevendo resultado da Linha {pl_id}...")
                pl_name = result.get("production_line_name", f"Linha {pl_id}")
                
                f.write(f"\n{'=' * 120}\n")
                f.write(f"LINHA DE PRODUÇÃO: {pl_name} (ID: {pl_id})\n")
                f.write(f"{'=' * 120}\n\n")
                
                if "error" in result:
                    f.write(f"ERRO: {result['error']}\n\n")
                    print(f"[LOG] ✓ Linha {pl_id} escrita (com erro)")
                    continue
                
                print(f"[LOG]   - Linha {pl_id}: Extraindo dados...")
                status = result.get("status", "Unknown")
                objective = result.get("objective", 0.0)
                sequences = result.get("sequences", {})
                completion = result.get("completion", {})
                tardiness = result.get("tardiness", {})
                inputs = result.get("inputs", {})
                
                ordered_jobs = inputs.get("ordered_jobs", [])
                processing = inputs.get("processing", {})
                due = inputs.get("due", {})
                priority_dict = inputs.get("priority", {})
                setup3 = inputs.get("setup3", {})
                
                print(f"[LOG]   - Linha {pl_id}: Escrevendo status e objetivo...")
                f.write(f"STATUS: {status}\n")
                f.write(f"VALOR OBJETIVO (soma ponderada de atrasos): {objective:.2f}\n\n")
                
                # ========== SEQUÊNCIAS DETALHADAS POR MÁQUINA ==========
                print(f"[LOG]   - Linha {pl_id}: Escrevendo sequências detalhadas...")
                f.write("=" * 120 + "\n")
                f.write("SEQUÊNCIAS DE EXECUÇÃO DETALHADAS\n")
                f.write("=" * 120 + "\n\n")
                
                for machine_id in sorted(sequences.keys()):
                    seq = sequences[machine_id]
                    f.write(f"\n{'─' * 120}\n")
                    f.write(f"MÁQUINA {machine_id}\n")
                    f.write(f"{'─' * 120}\n\n")
                    
                    if not seq or len(seq) == 0:
                        f.write("  (Nenhum job atribuído)\n\n")
                        continue
                    
                    # Tabela detalhada de sequência
                    f.write(f"{'Pos':<5}{'Job':<6}{'Tipo':<18}{'Produto/Molde':<35}{'Cliente':<20}{'Início':<12}{'Setup':<10}{'Prod':<10}{'Fim':<12}{'Prazo':<12}{'Atraso':<10}\n")
                    f.write("─" * 120 + "\n")
                    
                    current_time = 0.0
                    prev_job = None
                    
                    for pos, job_idx in enumerate(seq, start=1):
                        # Buscar dados do job
                        job_data = next((j for j in ordered_jobs if j["job_index"] == job_idx), None)
                        if not job_data:
                            continue
                        
                        job_type = job_data.get("type", "unknown")
                        type_display = {
                            "dummy": "Dummy",
                            "excel": "Excel",
                            "state_machine": "State Machine",
                            "programmed_stop": "Parada Programada"
                        }.get(job_type, job_type)
                        
                        # Extrair informações do job
                        product_name = job_data.get("product_name", "N/A")
                        mold_name = job_data.get("mold_name", "")
                        client_name = ""
                        
                        # Buscar cliente do row_data se for job do Excel
                        row_data = {}
                        if job_type == "excel":
                            row_data = job_data.get("row_data", {})
                            if isinstance(row_data, dict):
                                for key, value in row_data.items():
                                    if key and value:
                                        key_lower = str(key).lower().strip()
                                        if key_lower in ["cliente", "client"]:
                                            client_name = str(value).strip()
                                            break
                        
                        # Concatenar produto e molde
                        if mold_name and mold_name != "N/A":
                            product_display = f"{product_name} ({mold_name})"
                        else:
                            product_display = product_name
                        
                        # Truncar strings longas
                        product_display = (product_display[:32] + "...") if len(product_display) > 35 else product_display
                        client_name = (client_name[:17] + "...") if len(client_name) > 20 else client_name
                        
                        # Tempos
                        prod_time = processing.get((job_idx, machine_id), 0.0)
                        if prod_time >= 99999.0:
                            prod_time_display = "N/A"
                        else:
                            prod_time_display = f"{prod_time:.1f}"
                        
                        # Setup time
                        setup_time = 0.0
                        if prev_job is not None:
                            setup_time = setup3.get((prev_job, job_idx, machine_id), 0.0)
                        
                        # Calcular tempos de início e fim (estimativa baseada na sequência)
                        start_time = current_time + setup_time
                        if prod_time < 99999.0:
                            end_time = start_time + prod_time
                        else:
                            end_time = start_time
                        
                        # Buscar tempo real de completion do solver
                        actual_completion = completion.get((job_idx, machine_id))
                        if actual_completion is not None:
                            end_time_display = f"{actual_completion:.2f}"
                        else:
                            end_time_display = f"{end_time:.2f}*"
                        
                        # Prazo e atraso
                        deadline = due.get(job_idx, 0.0)
                        if deadline is None or (isinstance(deadline, float) and deadline != deadline):
                            deadline_display = "N/A"
                            tardiness_display = "N/A"
                        else:
                            deadline_display = f"{deadline:.2f}"
                            tard = tardiness.get(job_idx, 0.0)
                            if tard is not None and tard > 0.001:
                                tardiness_display = f"{tard:.2f}"
                            else:
                                tardiness_display = "0.00"
                        
                        # Linha da tabela
                        f.write(f"{pos:<5}{job_idx:<6}{type_display:<18}{product_display:<35}{client_name:<20}"
                               f"{start_time:<12.2f}{setup_time:<10.2f}{prod_time_display:<10}{end_time_display:<12}"
                               f"{deadline_display:<12}{tardiness_display:<10}\n")
                        
                        # Atualizar para próximo job
                        if prod_time < 99999.0:
                            current_time = end_time
                        prev_job = job_idx
                    
                    f.write("\n")
                
                # ========== DADOS DETALHADOS DOS JOBS (PARA VALIDAÇÃO) ==========
                print(f"[LOG]   - Linha {pl_id}: Escrevendo dados detalhados dos jobs...")
                f.write("\n" + "=" * 120 + "\n")
                f.write("DADOS DETALHADOS DOS JOBS (EXCEL)\n")
                f.write("=" * 120 + "\n\n")
                
                excel_jobs = [j for j in ordered_jobs if j.get("type") == "excel"]
                if excel_jobs:
                    for job_data in excel_jobs:
                        job_idx = job_data["job_index"]
                        f.write(f"\n{'─' * 120}\n")
                        f.write(f"JOB {job_idx}\n")
                        f.write(f"{'─' * 120}\n")
                        
                        # Informações básicas
                        f.write(f"Produto: {job_data.get('product_name', 'N/A')}\n")
                        f.write(f"Molde: {job_data.get('mold_name', 'N/A')}\n")
                        f.write(f"Prioridade: {job_data.get('priority', 'N/A')}\n")
                        f.write(f"Prazo nas injetoras: {job_data.get('deadline_in_injection', 'N/A')}\n")
                        
                        # Máquinas compatíveis
                        f.write(f"\nMáquinas compatíveis e tempos de produção:\n")
                        machines_dict = job_data.get("processing_time_by_machine", {})
                        for m_idx in sorted(machines_dict.keys()):
                            prod_time = machines_dict[m_idx]
                            if prod_time < 99999.0:
                                f.write(f"  - Máquina {m_idx}: {prod_time:.2f} horas\n")
                        
                        # Dados do Excel original
                        row_data = job_data.get("row_data", {})
                        if isinstance(row_data, dict) and row_data:
                            f.write(f"\nDados originais do Excel:\n")
                            for key, value in row_data.items():
                                if key and value is not None:
                                    f.write(f"  - {key}: {value}\n")
                        
                        # Tempos de término e atraso
                        completion_times = [(k, completion.get((job_idx, k))) for k in sorted(sequences.keys())]
                        completion_times = [(k, t) for k, t in completion_times if t is not None]
                        if completion_times:
                            f.write(f"\nTempo de término por máquina:\n")
                            for k, t in completion_times:
                                f.write(f"  - Máquina {k}: {t:.2f} horas\n")
                        
                        tard = tardiness.get(job_idx, 0.0)
                        if tard is not None and tard > 0.001:
                            f.write(f"\n⚠ ATRASO: {tard:.2f} horas\n")
                        else:
                            f.write(f"\n✓ SEM ATRASO\n")
                else:
                    f.write("(Nenhum job do Excel nesta linha)\n")
                
                f.write("\n")
                
                # ========== RESUMO DE UTILIZAÇÃO DAS MÁQUINAS ==========
                print(f"[LOG]   - Linha {pl_id}: Calculando resumo de utilização...")
                f.write("\n" + "=" * 120 + "\n")
                f.write("RESUMO DE UTILIZAÇÃO DAS MÁQUINAS\n")
                f.write("=" * 120 + "\n\n")
                
                f.write(f"{'Máquina':<12}{'Jobs':<10}{'Tempo Prod (h)':<18}{'Tempo Setup (h)':<18}{'Tempo Total (h)':<18}\n")
                f.write("─" * 120 + "\n")
                
                for machine_id in sorted(sequences.keys()):
                    seq = sequences[machine_id]
                    if not seq:
                        continue
                    
                    total_prod = 0.0
                    total_setup = 0.0
                    job_count = 0
                    prev_job = None
                    
                    for job_idx in seq:
                        if job_idx == 0:  # Skip dummy
                            prev_job = job_idx
                            continue
                        
                        job_count += 1
                        prod_time = processing.get((job_idx, machine_id), 0.0)
                        if prod_time < 99999.0:
                            total_prod += prod_time
                        
                        if prev_job is not None:
                            setup_time = setup3.get((prev_job, job_idx, machine_id), 0.0)
                            total_setup += setup_time
                        
                        prev_job = job_idx
                    
                    total_time = total_prod + total_setup
                    f.write(f"{machine_id:<12}{job_count:<10}{total_prod:<18.2f}{total_setup:<18.2f}{total_time:<18.2f}\n")
                
                f.write("\n")
                
                # ========== ANÁLISE DE ATRASOS ==========
                print(f"[LOG]   - Linha {pl_id}: Analisando atrasos...")
                f.write("=" * 120 + "\n")
                f.write("ANÁLISE DE ATRASOS\n")
                f.write("=" * 120 + "\n\n")
                
                jobs_with_delay = []
                total_tardiness = 0.0
                
                for job_idx in sorted(tardiness.keys()):
                    if job_idx == 0:  # Skip dummy
                        continue
                    
                    tard = tardiness.get(job_idx, 0.0)
                    if tard is not None and tard > 0.001:
                        job_data = next((j for j in ordered_jobs if j["job_index"] == job_idx), None)
                        if job_data:
                            jobs_with_delay.append((job_idx, tard, job_data))
                            total_tardiness += tard
                
                if jobs_with_delay:
                    f.write(f"TOTAL DE JOBS COM ATRASO: {len(jobs_with_delay)}\n")
                    f.write(f"ATRASO TOTAL: {total_tardiness:.2f} horas\n\n")
                    
                    f.write(f"{'Job':<6}{'Tipo':<18}{'Produto':<35}{'Cliente':<20}{'Prazo (h)':<12}{'Atraso (h)':<12}{'Prioridade':<12}\n")
                    f.write("─" * 120 + "\n")
                    
                    for job_idx, tard, job_data in sorted(jobs_with_delay, key=lambda x: x[1], reverse=True):
                        job_type = job_data.get("type", "unknown")
                        type_display = {
                            "dummy": "Dummy",
                            "excel": "Excel",
                            "state_machine": "State Machine",
                            "programmed_stop": "Parada Programada"
                        }.get(job_type, job_type)
                        
                        product_name = job_data.get("product_name", "N/A")
                        mold_name = job_data.get("mold_name", "")
                        if mold_name and mold_name != "N/A":
                            product_display = f"{product_name} ({mold_name})"
                        else:
                            product_display = product_name
                        product_display = (product_display[:32] + "...") if len(product_display) > 35 else product_display
                        
                        client_name = ""
                        if job_type == "excel":
                            row_data = job_data.get("row_data", {})
                            if isinstance(row_data, dict):
                                for key, value in row_data.items():
                                    if key and value:
                                        key_lower = str(key).lower().strip()
                                        if key_lower in ["cliente", "client"]:
                                            client_name = str(value).strip()
                                            break
                        client_name = (client_name[:17] + "...") if len(client_name) > 20 else client_name
                        
                        deadline = due.get(job_idx, 0.0)
                        prio = priority_dict.get(job_idx, 99)
                        
                        f.write(f"{job_idx:<6}{type_display:<18}{product_display:<35}{client_name:<20}"
                               f"{deadline:<12.2f}{tard:<12.2f}{prio:<12}\n")
                    else:
                        f.write("✓ NENHUM JOB COM ATRASO!\n")
                
                f.write("\n")
                
                # ========== VALIDAÇÕES ==========
                print(f"[LOG]   - Linha {pl_id}: Realizando validações...")
                f.write("=" * 120 + "\n")
                f.write("VALIDAÇÕES DE CONSISTÊNCIA\n")
                f.write("=" * 120 + "\n\n")
                
                validations = []
                
                # 1. Todos os jobs (exceto dummy) foram sequenciados?
                all_jobs = set(j["job_index"] for j in ordered_jobs if j["job_index"] != 0)
                sequenced_jobs = set()
                for seq in sequences.values():
                    sequenced_jobs.update(j for j in seq if j != 0)
                
                missing_jobs = all_jobs - sequenced_jobs
                if missing_jobs:
                    validations.append(f"⚠ ATENÇÃO: Jobs não sequenciados: {sorted(missing_jobs)}")
                else:
                    validations.append("✓ Todos os jobs foram sequenciados")
                
                # 2. Jobs sequenciados em máquinas incompatíveis?
                incompatible_count = 0
                for machine_id, seq in sequences.items():
                    for job_idx in seq:
                        if job_idx == 0:
                            continue
                        prod_time = processing.get((job_idx, machine_id), 99999.0)
                        if prod_time >= 99999.0:
                            incompatible_count += 1
                            validations.append(f"⚠ ATENÇÃO: Job {job_idx} sequenciado na Máquina {machine_id} mas tem tempo de produção inválido (99999h)")
                
                if incompatible_count == 0:
                    validations.append("✓ Nenhum job sequenciado em máquina incompatível")
                
                # 3. Jobs com completion time?
                jobs_without_completion = []
                for job_idx in all_jobs:
                    has_completion = False
                    for machine_id in sequences.keys():
                        if completion.get((job_idx, machine_id)) is not None:
                            has_completion = True
                            break
                    if not has_completion:
                        jobs_without_completion.append(job_idx)
                
                if jobs_without_completion:
                    validations.append(f"⚠ ATENÇÃO: Jobs sem tempo de término registrado: {sorted(jobs_without_completion)}")
                else:
                    validations.append("✓ Todos os jobs têm tempo de término registrado")
                
                # Escrever validações
                for validation in validations:
                    f.write(f"{validation}\n")
                
                f.write("\n")
                print(f"[LOG] ✓ Linha {pl_id} escrita no arquivo")
                
            except Exception as e:
                import traceback
                print(f"[LOG] ✗ ERRO ao escrever Linha {pl_id}: {str(e)}")
                traceback.print_exc()
                # Tentar escrever erro no arquivo e continuar
                try:
                    f.write(f"\n{'=' * 120}\n")
                    f.write(f"LINHA DE PRODUÇÃO: Linha {pl_id}\n")
                    f.write(f"{'=' * 120}\n\n")
                    f.write(f"ERRO AO GERAR LOG: {str(e)}\n")
                    f.write(f"TRACEBACK:\n{traceback.format_exc()}\n\n")
                except:
                    pass
        
        # ========== RESUMO GERAL ==========
        f.write("\n" + "=" * 120 + "\n")
        f.write("RESUMO GERAL DE TODAS AS LINHAS\n")
        f.write("=" * 120 + "\n\n")
        
        total_lines = len(solver_results)
        successful_lines = sum(1 for r in solver_results.values() if "error" not in r)
        failed_lines = total_lines - successful_lines
        
        f.write(f"Total de linhas processadas: {total_lines}\n")
        f.write(f"Linhas resolvidas com sucesso: {successful_lines}\n")
        f.write(f"Linhas com erro: {failed_lines}\n\n")
        
        if successful_lines > 0:
            f.write("Status por linha:\n")
            for pl_id, result in solver_results.items():
                pl_name = result.get("production_line_name", f"Linha {pl_id}")
                if "error" in result:
                    f.write(f"  - {pl_name} (ID {pl_id}): ERRO - {result['error']}\n")
                else:
                    status = result.get("status", "Unknown")
                    obj = result.get("objective", 0.0)
                    f.write(f"  - {pl_name} (ID {pl_id}): {status} (Objetivo: {obj:.2f})\n")
    
    print(f"[LOG] Arquivo de log concluído: {log_file}")
    
    # ========== GERAR TAMBÉM LOG JSON PARA ANÁLISE PROGRAMÁTICA ==========
    json_log_file = log_dir / f"solver_results_{timestamp_str}.json"
    print(f"[LOG] Gerando log JSON: {json_log_file}")
    
    try:
        # Preparar dados para JSON (converter tipos não serializáveis)
        json_data = {
            "timestamp": timestamp_str,
            "datetime": datetime.now().isoformat(),
            "total_lines": len(solver_results),
            "lines": {}
        }
        
        for pl_id, result in solver_results.items():
            line_data = {
                "production_line_id": pl_id,
                "production_line_name": result.get("production_line_name", f"Linha {pl_id}")
            }
            
            if "error" in result:
                line_data["error"] = result["error"]
            else:
                line_data["status"] = result.get("status", "Unknown")
                line_data["objective"] = result.get("objective", 0.0)
                
                # Sequências
                line_data["sequences"] = {
                    str(k): v for k, v in result.get("sequences", {}).items()
                }
                
                # Completion times
                completion_dict = {}
                for (j, k), t in result.get("completion", {}).items():
                    key = f"job_{j}_machine_{k}"
                    completion_dict[key] = t if t is not None else None
                line_data["completion_times"] = completion_dict
                
                # Tardiness
                line_data["tardiness"] = {
                    f"job_{j}": t if t is not None else None 
                    for j, t in result.get("tardiness", {}).items()
                }
                
                # Jobs detalhados
                inputs = result.get("inputs", {})
                ordered_jobs = inputs.get("ordered_jobs", [])
                
                line_data["jobs"] = []
                for job_data in ordered_jobs:
                    job_json = {
                        "job_index": job_data["job_index"],
                        "type": job_data.get("type", "unknown"),
                        "product_name": job_data.get("product_name"),
                        "mold_name": job_data.get("mold_name"),
                        "priority": job_data.get("priority", 99),
                        "deadline_in_injection": job_data.get("deadline_in_injection", 0.0),
                        "processing_time_by_machine": {str(k): v for k, v in job_data.get("processing_time_by_machine", {}).items()},
                        "final_completion_time_hours": job_data.get("final_completion_time_hours")
                    }
                    
                    # Adicionar row_data se for job do Excel
                    if job_data.get("type") == "excel":
                        row_data = job_data.get("row_data", {})
                        if isinstance(row_data, dict):
                            # Converter valores para strings serializáveis
                            job_json["excel_data"] = {
                                str(k): str(v) if v is not None else None 
                                for k, v in row_data.items()
                            }
                    
                    line_data["jobs"].append(job_json)
                
                # Resumo de utilização
                line_data["machine_utilization"] = {}
                for machine_id, seq in result.get("sequences", {}).items():
                    if not seq:
                        continue
                    
                    total_prod = 0.0
                    total_setup = 0.0
                    job_count = 0
                    prev_job = None
                    
                    processing = inputs.get("processing", {})
                    setup3 = inputs.get("setup3", {})
                    
                    for job_idx in seq:
                        if job_idx == 0:
                            prev_job = job_idx
                            continue
                        
                        job_count += 1
                        prod_time = processing.get((job_idx, machine_id), 0.0)
                        if prod_time < 99999.0:
                            total_prod += prod_time
                        
                        if prev_job is not None:
                            setup_time = setup3.get((prev_job, job_idx, machine_id), 0.0)
                            total_setup += setup_time
                        
                        prev_job = job_idx
                    
                    line_data["machine_utilization"][str(machine_id)] = {
                        "job_count": job_count,
                        "production_time": round(total_prod, 2),
                        "setup_time": round(total_setup, 2),
                        "total_time": round(total_prod + total_setup, 2)
                    }
            
            json_data["lines"][str(pl_id)] = line_data
        
        # Salvar JSON
        with open(json_log_file, "w", encoding="utf-8") as jf:
            json.dump(json_data, jf, indent=2, ensure_ascii=False)
        
        print(f"[LOG] Log JSON concluído: {json_log_file}")
    except Exception as e:
        print(f"[LOG] Erro ao gerar log JSON: {e}")
        import traceback
        traceback.print_exc()
    
    return str(log_file)





