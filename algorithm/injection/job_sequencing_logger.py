"""
Logger focado no sequenciamento de jobs com informações de precedência e término.
Gera logs com detalhes de cada job ordenados por prioridade.
"""

from pathlib import Path
from datetime import datetime
from typing import Dict, List
import json
from sqlalchemy.orm import Session


def log_job_sequencing(
    solver_results: Dict[int, Dict],
    db: Session
) -> str:
    """
    Gera um log focado no sequenciamento de jobs com informações de:
    - Índice do job
    - Nome do produto
    - Nome do cliente
    - Variável precede (precedências)
    - Variável termino (tempo de conclusão)
    
    Jobs são ordenados por prioridade (decrescente - do mais prioritário ao menos prioritário).
    
    Retorna o caminho do arquivo de log gerado.
    """
    base_dir = Path(__file__).resolve().parents[2]
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Limpeza automática de logs antigos
    try:
        from algorithm.injection.log_cleanup import auto_cleanup_logs
        auto_cleanup_logs(base_dir, keep_recent=5)
    except Exception as e:
        print(f"Erro na limpeza de logs: {e}")
    
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"job_sequencing_{timestamp_str}.txt"
    
    print(f"[LOG] Gerando log de sequenciamento de jobs: {log_file}")
    
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("=" * 140 + "\n")
        f.write("SEQUENCIAMENTO DE JOBS - ANÁLISE DE PRECEDÊNCIA E TÉRMINO\n")
        f.write("=" * 140 + "\n\n")
        f.write(f"Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n")
        
        for pl_id, result in solver_results.items():
            try:
                pl_name = result.get("production_line_name", f"Linha {pl_id}")
                
                f.write(f"\n{'=' * 140}\n")
                f.write(f"LINHA DE PRODUÇÃO: {pl_name} (ID: {pl_id})\n")
                f.write(f"{'=' * 140}\n\n")
                
                if "error" in result:
                    f.write(f"ERRO: {result['error']}\n\n")
                    continue
                
                # Extrair dados
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
                
                f.write(f"STATUS: {status}\n")
                f.write(f"VALOR OBJETIVO: {objective:.2f}\n\n")
                
                # ========== JOBS ORDENADOS POR PRIORIDADE ==========
                f.write("=" * 140 + "\n")
                f.write("JOBS ORDENADOS POR PRIORIDADE (DECRESCENTE)\n")
                f.write("=" * 140 + "\n\n")
                
                # Filtrar jobs exceto dummy (job 0) e ordenar por prioridade
                real_jobs = [j for j in ordered_jobs if j["job_index"] != 0]
                
                # Ordenar por prioridade (menor valor = maior prioridade)
                jobs_sorted_by_priority = sorted(
                    real_jobs,
                    key=lambda x: x.get("priority", 99)
                )
                
                # Cabeçalho da tabela
                f.write(f"{'#':<5}{'Job':<8}{'Tipo':<18}{'Produto':<30}{'Cliente':<25}{'Prioridade':<12}{'Prazo (h)':<12}\n")
                f.write("─" * 140 + "\n")
                
                for seq_num, job_data in enumerate(jobs_sorted_by_priority, start=1):
                    job_idx = job_data["job_index"]
                    job_type = job_data.get("type", "unknown")
                    
                    # Traduzir tipo
                    type_display = {
                        "dummy": "Dummy",
                        "excel": "Excel",
                        "state_machine": "State Machine",
                        "programmed_stop": "Parada Programada"
                    }.get(job_type, job_type)
                    
                    # Produto
                    product_name = job_data.get("product_name", "N/A")
                    mold_name = job_data.get("mold_name", "")
                    if mold_name and mold_name != "N/A":
                        product_display = f"{product_name} ({mold_name})"
                    else:
                        product_display = product_name
                    product_display = (product_display[:27] + "...") if len(product_display) > 30 else product_display
                    
                    # Cliente
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
                    client_name = (client_name[:22] + "...") if len(client_name) > 25 else client_name
                    
                    # Prioridade e prazo
                    priority = job_data.get("priority", 99)
                    deadline = due.get(job_idx, 0.0)
                    if deadline is None or (isinstance(deadline, float) and deadline != deadline):
                        deadline_display = "N/A"
                    else:
                        deadline_display = f"{deadline:.2f}"
                    
                    # Linha da tabela
                    f.write(f"{seq_num:<5}{job_idx:<8}{type_display:<18}{product_display:<30}"
                           f"{client_name:<25}{priority:<12}{deadline_display:<12}\n")
                
                f.write("\n")
                
                # ========== DETALHES DE PRECEDÊNCIA E TÉRMINO POR JOB ==========
                f.write("=" * 140 + "\n")
                f.write("DETALHES DE PRECEDÊNCIA E TÉRMINO\n")
                f.write("=" * 140 + "\n\n")
                
                for seq_num, job_data in enumerate(jobs_sorted_by_priority, start=1):
                    job_idx = job_data["job_index"]
                    job_type = job_data.get("type", "unknown")
                    
                    f.write(f"\n{'─' * 140}\n")
                    f.write(f"JOB {job_idx} - Posição na Prioridade: #{seq_num}\n")
                    f.write(f"{'─' * 140}\n")
                    
                    # Informações básicas
                    product_name = job_data.get("product_name", "N/A")
                    mold_name = job_data.get("mold_name", "")
                    
                    f.write(f"Produto: {product_name}\n")
                    if mold_name and mold_name != "N/A":
                        f.write(f"Molde: {mold_name}\n")
                    
                    # Cliente
                    if job_type == "excel":
                        row_data = job_data.get("row_data", {})
                        if isinstance(row_data, dict):
                            for key, value in row_data.items():
                                if key and value:
                                    key_lower = str(key).lower().strip()
                                    if key_lower in ["cliente", "client"]:
                                        f.write(f"Cliente: {value}\n")
                                        break
                    
                    priority = job_data.get("priority", 99)
                    deadline = due.get(job_idx, 0.0)
                    f.write(f"Prioridade: {priority}\n")
                    f.write(f"Prazo nas injetoras: {deadline:.2f} horas\n")
                    f.write(f"Tipo: {job_type}\n")
                    
                    # Variável TERMINO (tempo de conclusão)
                    f.write(f"\nVARIÁVEL TERMINO (tempo de conclusão em cada máquina):\n")
                    termino_found = False
                    for machine_id in sorted(sequences.keys()):
                        termino_value = completion.get((job_idx, machine_id))
                        if termino_value is not None:
                            f.write(f"  termino[{job_idx}, {machine_id}] = {termino_value:.2f} horas\n")
                            termino_found = True
                    
                    if not termino_found:
                        f.write("  (Nenhum tempo de conclusão registrado)\n")
                    
                    # Atraso
                    tard = tardiness.get(job_idx, 0.0)
                    if tard is not None and tard > 0.001:
                        f.write(f"\n⚠ ATRASO: {tard:.2f} horas\n")
                    else:
                        f.write(f"\n✓ SEM ATRASO\n")
                    
                    # Variável PRECEDE (precedências)
                    f.write(f"\nVARIÁVEL PRECEDE (precedências nas máquinas):\n")
                    
                    # Encontrar predecessores e sucessores
                    predecessors = {}  # {machine_id: predecessor_job}
                    successors = {}    # {machine_id: successor_job}
                    
                    for machine_id, seq in sequences.items():
                        if job_idx in seq:
                            pos = seq.index(job_idx)
                            
                            # Predecessor
                            if pos > 0:
                                pred_job = seq[pos - 1]
                                predecessors[machine_id] = pred_job
                            
                            # Sucessor
                            if pos < len(seq) - 1:
                                succ_job = seq[pos + 1]
                                successors[machine_id] = succ_job
                    
                    # Predecessores
                    f.write(f"\n  Predecessores (job que vem antes):\n")
                    if predecessors:
                        for machine_id, pred_job in sorted(predecessors.items()):
                            # Buscar nome do predecessor
                            pred_data = next((j for j in ordered_jobs if j["job_index"] == pred_job), None)
                            pred_name = pred_data.get("product_name", f"Job {pred_job}") if pred_data else f"Job {pred_job}"
                            
                            # Setup time
                            setup_time = setup3.get((pred_job, job_idx, machine_id), 0.0)
                            
                            f.write(f"    precede[{pred_job}, {job_idx}, {machine_id}] = 1  ->  "
                                   f"Máquina {machine_id}: {pred_name} precede este job "
                                   f"(setup: {setup_time:.2f}h)\n")
                    else:
                        f.write(f"    (Nenhum predecessor - job não foi sequenciado ou é o primeiro)\n")
                    
                    # Sucessores
                    f.write(f"\n  Sucessores (job que vem depois):\n")
                    if successors:
                        for machine_id, succ_job in sorted(successors.items()):
                            # Buscar nome do sucessor
                            succ_data = next((j for j in ordered_jobs if j["job_index"] == succ_job), None)
                            succ_name = succ_data.get("product_name", f"Job {succ_job}") if succ_data else f"Job {succ_job}"
                            
                            # Setup time
                            setup_time = setup3.get((job_idx, succ_job, machine_id), 0.0)
                            
                            f.write(f"    precede[{job_idx}, {succ_job}, {machine_id}] = 1  ->  "
                                   f"Máquina {machine_id}: este job precede {succ_name} "
                                   f"(setup: {setup_time:.2f}h)\n")
                    else:
                        f.write(f"    (Nenhum sucessor - job não foi sequenciado ou é o último)\n")
                    
                    # Tempos de produção
                    f.write(f"\nTempo de produção por máquina:\n")
                    machines_dict = job_data.get("processing_time_by_machine", {})
                    for m_idx in sorted(machines_dict.keys()):
                        prod_time = machines_dict[m_idx]
                        if prod_time < 99999.0:
                            f.write(f"  Máquina {m_idx}: {prod_time:.2f} horas\n")
                        else:
                            f.write(f"  Máquina {m_idx}: Incompatível (99999h)\n")
                
                f.write("\n")
                
                # ========== RESUMO DA LINHA ==========
                f.write("=" * 140 + "\n")
                f.write("RESUMO DA LINHA DE PRODUÇÃO\n")
                f.write("=" * 140 + "\n\n")
                
                total_jobs = len([j for j in ordered_jobs if j["job_index"] != 0])
                jobs_with_delay = sum(1 for j in ordered_jobs if j["job_index"] != 0 and tardiness.get(j["job_index"], 0.0) > 0.001)
                
                f.write(f"Total de Jobs: {total_jobs}\n")
                f.write(f"Jobs no Prazo: {total_jobs - jobs_with_delay}\n")
                f.write(f"Jobs Atrasados: {jobs_with_delay}\n")
                f.write(f"Valor Objetivo (soma ponderada de atrasos): {objective:.2f}\n\n")
                
                # Sequências por máquina (ordem de execução)
                f.write("ORDEM DE EXECUÇÃO POR MÁQUINA:\n")
                for machine_id in sorted(sequences.keys()):
                    seq = sequences[machine_id]
                    f.write(f"\n  Máquina {machine_id}: ")
                    if not seq or len(seq) == 0:
                        f.write("(vazia)")
                    else:
                        # Remover dummy da visualização
                        seq_display = [j for j in seq if j != 0]
                        f.write(" → ".join(str(j) for j in seq_display))
                    f.write("\n")
                
                f.write("\n")
                
                print(f"[LOG] ✓ Linha {pl_id} escrita no log de sequenciamento")
                
            except Exception as e:
                import traceback
                print(f"[LOG] ✗ ERRO ao escrever Linha {pl_id}: {str(e)}")
                traceback.print_exc()
                try:
                    f.write(f"\n{'=' * 140}\n")
                    f.write(f"LINHA DE PRODUÇÃO: Linha {pl_id}\n")
                    f.write(f"{'=' * 140}\n\n")
                    f.write(f"ERRO AO GERAR LOG: {str(e)}\n")
                    f.write(f"TRACEBACK:\n{traceback.format_exc()}\n\n")
                except:
                    pass
        
        # ========== RESUMO GERAL ==========
        f.write("\n" + "=" * 140 + "\n")
        f.write("RESUMO GERAL DE TODAS AS LINHAS\n")
        f.write("=" * 140 + "\n\n")
        
        total_lines = len(solver_results)
        successful_lines = sum(1 for r in solver_results.values() if "error" not in r)
        
        f.write(f"Total de linhas processadas: {total_lines}\n")
        f.write(f"Linhas resolvidas com sucesso: {successful_lines}\n\n")
        
        if successful_lines > 0:
            f.write("Status por linha:\n")
            for pl_id, result in solver_results.items():
                pl_name = result.get("production_line_name", f"Linha {pl_id}")
                if "error" in result:
                    f.write(f"  - {pl_name} (ID {pl_id}): ERRO\n")
                else:
                    status = result.get("status", "Unknown")
                    obj = result.get("objective", 0.0)
                    f.write(f"  - {pl_name} (ID {pl_id}): {status} (Objetivo: {obj:.2f})\n")
        
        f.write("\n")
        f.write("=" * 140 + "\n")
        f.write(f"Log gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
        f.write("=" * 140 + "\n")
    
    print(f"[LOG] Log de sequenciamento concluído: {log_file}")
    
    # ========== GERAR TAMBÉM LOG JSON ==========
    json_log_file = log_dir / f"job_sequencing_{timestamp_str}.json"
    
    try:
        json_data = {
            "timestamp": timestamp_str,
            "datetime": datetime.now().isoformat(),
            "total_lines": len(solver_results),
            "lines": {}
        }
        
        for pl_id, result in solver_results.items():
            if "error" in result:
                json_data["lines"][str(pl_id)] = {
                    "production_line_id": pl_id,
                    "production_line_name": result.get("production_line_name", f"Linha {pl_id}"),
                    "error": result["error"]
                }
                continue
            
            inputs = result.get("inputs", {})
            ordered_jobs = inputs.get("ordered_jobs", [])
            priority_dict = inputs.get("priority", {})
            due = inputs.get("due", {})
            completion = result.get("completion", {})
            tardiness = result.get("tardiness", {})
            sequences = result.get("sequences", {})
            setup3 = inputs.get("setup3", {})
            
            # Filtrar e ordenar jobs por prioridade
            real_jobs = [j for j in ordered_jobs if j["job_index"] != 0]
            jobs_sorted_by_priority = sorted(real_jobs, key=lambda x: x.get("priority", 99))
            
            jobs_list = []
            for seq_num, job_data in enumerate(jobs_sorted_by_priority, start=1):
                job_idx = job_data["job_index"]
                
                # Cliente
                client_name = ""
                if job_data.get("type") == "excel":
                    row_data = job_data.get("row_data", {})
                    if isinstance(row_data, dict):
                        for key, value in row_data.items():
                            if key and value and str(key).lower().strip() in ["cliente", "client"]:
                                client_name = str(value).strip()
                                break
                
                # Encontrar predecessores e sucessores
                predecessors = {}
                successors = {}
                for machine_id, seq in sequences.items():
                    if job_idx in seq:
                        pos = seq.index(job_idx)
                        if pos > 0:
                            predecessors[str(machine_id)] = {
                                "job": seq[pos - 1],
                                "setup_time": setup3.get((seq[pos - 1], job_idx, machine_id), 0.0)
                            }
                        if pos < len(seq) - 1:
                            successors[str(machine_id)] = {
                                "job": seq[pos + 1],
                                "setup_time": setup3.get((job_idx, seq[pos + 1], machine_id), 0.0)
                            }
                
                # Termino
                termino_dict = {}
                for machine_id in sequences.keys():
                    t = completion.get((job_idx, machine_id))
                    if t is not None:
                        termino_dict[str(machine_id)] = round(t, 2)
                
                jobs_list.append({
                    "priority_position": seq_num,
                    "job_index": job_idx,
                    "type": job_data.get("type", "unknown"),
                    "product_name": job_data.get("product_name", "N/A"),
                    "mold_name": job_data.get("mold_name", ""),
                    "client_name": client_name,
                    "priority": job_data.get("priority", 99),
                    "deadline": due.get(job_idx, 0.0),
                    "tardiness": tardiness.get(job_idx, 0.0),
                    "termino": termino_dict,
                    "precede_predecessors": predecessors,
                    "precede_successors": successors
                })
            
            json_data["lines"][str(pl_id)] = {
                "production_line_id": pl_id,
                "production_line_name": result.get("production_line_name", f"Linha {pl_id}"),
                "status": result.get("status", "Unknown"),
                "objective": result.get("objective", 0.0),
                "jobs": jobs_list
            }
        
        with open(json_log_file, "w", encoding="utf-8") as jf:
            json.dump(json_data, jf, indent=2, ensure_ascii=False)
        
        print(f"[LOG] Log JSON de sequenciamento concluído: {json_log_file}")
    except Exception as e:
        print(f"[LOG] Erro ao gerar log JSON: {e}")
        import traceback
        traceback.print_exc()
    
    return str(log_file)

