"""
Wrapper para o solver de sequenciamento de injetoras.
Prepara os dados de calculate_processing_time e roda o solver para cada linha de produção.
"""

from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime

from app.models.client import Client
from app.models.composition_line import CompositionLine
from algorithm.injetoras_modelo import build_and_solve
from algorithm.injection.setup_matrix_calculator import build_setup_matrix


def get_client_priority(client_name: str, db: Session) -> int:
    """Busca a prioridade do cliente pelo nome. Retorna 99 se não encontrar."""
    if not client_name:
        return 99
    
    client = db.query(Client).filter(Client.name == client_name).first()
    if client:
        return client.priority
    return 99




def prepare_solver_inputs(
    jobs_by_line: Dict[int, Dict],
    db: Session
) -> Dict[int, Dict]:
    """
    Prepara os inputs do solver para cada linha de produção.
    
    Retorna: {production_line_id: {
        'jobs': [0, 1, 2, ...],
        'machines': [1, 2, ...],
        'processing': {(j, k): tempo},
        'due': {j: deadline_in_injection},
        'priority': {j: priority},
        'setup3': {(i, j, k): tempo}
    }}
    """
    solver_inputs = {}
    
    for pl_id, line_data in jobs_by_line.items():
        jobs_list = line_data["jobs"]
        if not jobs_list:
            continue
        
        # Converter "machines" para "processing_time_by_machine" para compatibilidade interna
        for job in jobs_list:
            if "machines" in job and "processing_time_by_machine" not in job:
                job["processing_time_by_machine"] = job["machines"]
        
        # Separar jobs por tipo
        excel_jobs = []
        state_machine_jobs = []
        programmed_stops_jobs = []
        
        for job in jobs_list:
            # Jobs do Excel têm composition_line_id
            if job.get("composition_line_id") is not None:
                excel_jobs.append(job)
            else:
                # Jobs falsos: verificar se é programmed_stop ou state_machine
                row_data = job.get("row_data", {})
                product_name = job.get("product_name", "")
                
                # Programmed stops têm "reason" no product_name e não têm mold_id/product_id válidos
                # State machines têm mold_id e product_id válidos
                if job.get("mold_id") is None and job.get("product_id") is None:
                    # Provavelmente é programmed_stop (reason aparece como product_name)
                    programmed_stops_jobs.append(job)
                elif job.get("mold_id") is not None or job.get("product_id") is not None:
                    # State machine tem mold/product
                    state_machine_jobs.append(job)
                else:
                    # Fallback: se não tem composition_line_id, assume state_machine
                    state_machine_jobs.append(job)
        
        # Ordenar: Job 0 (dummy) -> Excel -> State Machine -> Programmed Stops
        ordered_jobs = []
        
        # Job 0 (dummy) - sempre primeiro
        # Buscar todas as máquinas da linha (das composition_lines ou dos jobs)
        all_machines = set()
        for job in jobs_list:
            processing_time_by_machine = job.get("processing_time_by_machine", [])
            if isinstance(processing_time_by_machine, list):
                # Se for lista de dicionários
                for machine in processing_time_by_machine:
                    if isinstance(machine, dict):
                        all_machines.add(machine.get("machine_id"))
            elif isinstance(processing_time_by_machine, dict):
                # Se for dicionário {m_idx: prod_time}, usar as chaves
                all_machines.update(processing_time_by_machine.keys())
        
        # Se não encontrou máquinas nos jobs, buscar da linha de produção
        if not all_machines:
            from app.models.production_line import ProductionLine
            from app.models.composition_line_machine import CompositionLineMachine
            
            production_line = db.query(ProductionLine).filter(ProductionLine.id == pl_id).first()
            if production_line:
                comp_lines = db.query(CompositionLine).filter(
                    CompositionLine.production_line_id == pl_id
                ).all()
                for comp_line in comp_lines:
                    for clm in comp_line.machines:
                        all_machines.add(clm.machine_id)
        
        machine_id_to_idx = {m_id: idx for idx, m_id in enumerate(sorted(all_machines), start=1)}
        machine_idx_to_id = {idx: m_id for m_id, idx in machine_id_to_idx.items()}
        
        # Criar job dummy
        dummy_job = {
            "job_index": 0,
            "processing_time_by_machine": {m_idx: 0.0 for m_idx in machine_id_to_idx.values()},
            "priority": 99,
            "deadline_in_injection": 0.0,
            "composition_line_id": None,
            "type": "dummy"
        }
        ordered_jobs.append(dummy_job)
        
        # Jobs do Excel
        job_idx = 1
        composition_lines_for_setup = []
        for job in excel_jobs:
            comp_line_id = job.get("composition_line_id")
            if comp_line_id:
                # Buscar CompositionLine para setup
                comp_line = db.query(CompositionLine).filter(CompositionLine.id == comp_line_id).first()
                if comp_line and comp_line not in composition_lines_for_setup:
                    composition_lines_for_setup.append(comp_line)
            
            # Buscar priority do cliente
            client_name = None
            # row_data pode ser do Excel original ou serializado
            row_data = job.get("row_data", {})
            if isinstance(row_data, dict):
                # Tentar encontrar nome do cliente (case-insensitive)
                for key, value in row_data.items():
                    if key and value:
                        key_lower = str(key).lower().strip()
                        if key_lower in ["cliente", "client"]:
                            client_name = str(value).strip()
                            break
            
            priority = get_client_priority(client_name, db) if client_name else 99
            
            # Montar máquinas e production_time
            machines_dict = {}
            for machine in job.get("processing_time_by_machine", []):
                m_id = machine["machine_id"]
                if m_id in machine_id_to_idx:
                    m_idx = machine_id_to_idx[m_id]
                    production_time = machine.get("production_time", 0.0)
                    machines_dict[m_idx] = production_time
            
            # IMPORTANTE: Preservar product_name, mold_name, promised_date e dados do Excel completos
            promised_date = job.get("promised_date")  # datetime da planilha (Data + Horário Limite Faturamento)
            ordered_jobs.append({
                "job_index": job_idx,
                "processing_time_by_machine": machines_dict,
                "priority": priority,
                "deadline_in_injection": job.get("deadline_in_injection", 0.0),
                "composition_line_id": comp_line_id,
                "type": "excel",
                "promised_date": promised_date,  # Data+hora prometida (colunas F e G da planilha)
                # NOVOS CAMPOS PRESERVADOS do calculate_processing_time:
                "product_name": job.get("product_name"),
                "mold_name": job.get("mold_name"),
                "mold_id": job.get("mold_id"),
                "product_id": job.get("product_id"),
                "demand": job.get("demand"),
                "unit_value": job.get("unit_value", 0.0),  # Valor unitário da planilha (acesso direto)
                "client_name": client_name,  # Extraído acima
                "row_data": row_data,  # Dados completos da linha do Excel
                "excel_data": {
                    "demand": job.get("demand"),
                    "unit_value": job.get("unit_value", 0.0),  # Valor unitário da planilha
                    "scrap_percent": job.get("scrap_percent"),
                    "closed_cavity_risk_percent": job.get("closed_cavity_risk_percent"),
                    "scrap_factor": job.get("scrap_factor"),
                    "demand_with_scrap": job.get("demand_with_scrap"),
                    "deadline_hours": job.get("deadline_hours"),
                    "total_post_injection_time": job.get("total_post_injection_time"),
                }
            })
            job_idx += 1
        
        # Jobs de State Machine
        for job in state_machine_jobs:
            # Inicializar todas as máquinas com 99999.0
            machines_dict = {m_idx: 99999.0 for m_idx in machine_id_to_idx.values()}
            deadline_in_injection = None
            used_machine_idx = None
            
            # deadline_in_injection = production_time da máquina utilizada (não 9999)
            # Buscar o production_time que não é 99999
            for machine in job.get("processing_time_by_machine", []):
                m_id = machine["machine_id"]
                if m_id in machine_id_to_idx:
                    m_idx = machine_id_to_idx[m_id]
                    production_time = machine.get("production_time", 99999.0)
                    machines_dict[m_idx] = production_time
                    # Apenas considerar máquinas que não têm 99999 para deadline
                    if production_time != 99999.0 and deadline_in_injection is None:
                        deadline_in_injection = production_time
                        used_machine_idx = m_idx
            
            # Se não encontrou nenhuma máquina utilizada, usar 0
            if deadline_in_injection is None:
                deadline_in_injection = 0.0
            
            ordered_jobs.append({
                "job_index": job_idx,
                "processing_time_by_machine": machines_dict,
                "priority": 99,
                "deadline_in_injection": deadline_in_injection,
                "composition_line_id": None,
                "type": "state_machine",
                "mold_name": job.get("mold_name"),
                "product_name": job.get("product_name"),
                "client_name": job.get("client_name"),  # ADICIONAR CLIENT_NAME
                "order_number": job.get("order_number"),  # ADICIONAR NÚMERO DO PEDIDO
                "demand": job.get("demand"),  # ADICIONAR DEMAND
                "billing_value": job.get("billing_value"),  # ADICIONAR BILLING_VALUE
                # Preservar data e hora prometida da state_machine (vem do mesmo JSON)
                "billing_deadline_date": job.get("billing_deadline_date"),
                "billing_deadline_time": job.get("billing_deadline_time"),
                "completed": job.get("completed", False),  # ADICIONAR COMPLETED
                "remaining_post_injection_hours": job.get("remaining_post_injection_hours"),  # Preservar para cálculo
                # Máquina onde o state_machine está realmente rodando (para ocupar posição 0 na matriz dessa máquina)
                "used_machine_idx": used_machine_idx,
            })
            job_idx += 1
        
        # Jobs de Programmed Stops
        for job in programmed_stops_jobs:
            # Inicializar todas as máquinas com 99999.0
            machines_dict = {m_idx: 99999.0 for m_idx in machine_id_to_idx.values()}
            
            # Atualizar apenas as máquinas que têm dados no job
            for machine in job.get("processing_time_by_machine", []):
                m_id = machine["machine_id"]
                if m_id in machine_id_to_idx:
                    m_idx = machine_id_to_idx[m_id]
                    production_time = machine.get("production_time", 99999.0)
                    machines_dict[m_idx] = production_time
            
            ordered_jobs.append({
                "job_index": job_idx,
                "processing_time_by_machine": machines_dict,
                "priority": 99,
                "deadline_in_injection": job.get("deadline_in_injection", 0.0),
                "composition_line_id": None,
                "type": "programmed_stop",
                "product_name": job.get("product_name"),  # reason vai aqui
                # Preservar dados completos da parada para salvar data+hora prometida no BD/log
                "row_data": job.get("row_data", {}),
                "start_date": job.get("row_data", {}).get("start_date") if isinstance(job.get("row_data", {}), dict) else None,
                "start_time": job.get("row_data", {}).get("start_time") if isinstance(job.get("row_data", {}), dict) else None,
                "end_date": job.get("row_data", {}).get("end_date") if isinstance(job.get("row_data", {}), dict) else None,
                "end_time": job.get("row_data", {}).get("end_time") if isinstance(job.get("row_data", {}), dict) else None,
            })
            job_idx += 1
        
        # Montar inputs do solver
        jobs = [j["job_index"] for j in ordered_jobs]
        machines = sorted(machine_id_to_idx.values())
        
        processing = {}
        for job_data in ordered_jobs:
            j_idx = job_data["job_index"]
            for m_idx, prod_time in job_data["processing_time_by_machine"].items():
                processing[(j_idx, m_idx)] = prod_time
        
        due = {j["job_index"]: j["deadline_in_injection"] for j in ordered_jobs}
        priority_dict = {j["job_index"]: j["priority"] for j in ordered_jobs}
        
        # Montar setup matrix baseada nos PRODUTOS dos jobs
        setup3 = build_setup_matrix(ordered_jobs, machine_id_to_idx, db)
        
        solver_inputs[pl_id] = {
            "jobs": jobs,
            "machines": machines,
            "processing": processing,
            "due": due,
            "priority": priority_dict,
            "setup3": setup3,
            "machine_idx_to_id": machine_idx_to_id,  # índice interno do solver -> machine_id real
            "ordered_jobs": ordered_jobs,  # Para referência no log
        }
    
    return solver_inputs


def solve_line(
    pl_id: int,
    solver_input: Dict,
    pl_name: str
) -> Tuple[int, Dict]:
    """
    Roda o solver para uma linha de produção.
    
    Retorna: (production_line_id, {
        'status': str,
        'objective': float,
        'sequences': {machine_id: [job_indices]},
        'completion': {(job, machine): time},
        'tardiness': {job: tardiness}
    })
    """
    try:
        status, obj, sequences, completion, tard = build_and_solve(
            jobs=solver_input["jobs"],
            machines=solver_input["machines"],
            processing=solver_input["processing"],
            due=solver_input["due"],
            priority=solver_input["priority"],
            setup3=solver_input["setup3"],
            dummy=0
        )
        
        # CALCULAR final_completion_time_hours para cada job E PARA CADA MÁQUINA
        ordered_jobs_with_final_time = []
        for job_data in solver_input["ordered_jobs"]:
            job_idx = job_data["job_index"]
            job_type = job_data.get("type", "excel")
            
            final_completion_time_hours = None
            
            # Jobs falsos (state_machine): usar remaining_post_injection_hours + deadline_in_injection
            if job_type == "state_machine":
                remaining_post_injection = job_data.get("remaining_post_injection_hours")
                deadline_in_injection = job_data.get("deadline_in_injection", 0.0)
                if remaining_post_injection is not None:
                    # final_completion_time_hours = (remaining_post_injection_hours / 60) + deadline_in_injection
                    post_injection_hours = float(remaining_post_injection) / 60.0
                    deadline_hours = float(deadline_in_injection) if deadline_in_injection is not None else 0.0
                    final_completion_time_hours = round(post_injection_hours + deadline_hours, 2)
            
            # Jobs normais (excel) e programmed_stop: usar completion do solver
            if final_completion_time_hours is None:
                # Pegar total_post_injection_time do excel_data
                excel_data = job_data.get("excel_data", {})
                post_injection_time = excel_data.get("total_post_injection_time", 0.0) if excel_data else 0.0
                
                # Buscar a máquina que realmente processou este job (completion_time > 0)
                # O solver atribui cada job a UMA única máquina
                for machine_idx in solver_input["machines"]:
                    comp_time = completion.get((job_idx, machine_idx), 0.0)
                    if comp_time > 0:
                        # Esta é a máquina que processou o job
                        final_completion = comp_time + post_injection_time
                        final_completion_time_hours = round(final_completion, 2)
                        break  # Só pode ter uma máquina processando o job
            
            # Adicionar apenas o valor final ao job_data
            job_data_with_final = job_data.copy()
            job_data_with_final["final_completion_time_hours"] = final_completion_time_hours
            ordered_jobs_with_final_time.append(job_data_with_final)
        
        # Atualizar solver_input com os jobs que têm final_completion_time_hours
        solver_input_updated = solver_input.copy()
        solver_input_updated["ordered_jobs"] = ordered_jobs_with_final_time
        
        return (pl_id, {
            "production_line_id": pl_id,
            "production_line_name": pl_name,
            "status": status,
            "objective": obj,
            "sequences": sequences,
            "completion": completion,
            "tardiness": tard,
            "inputs": solver_input_updated  # Para log - com final_completion_time_hours
        })
    except Exception as e:
        return (pl_id, {
            "production_line_id": pl_id,
            "production_line_name": pl_name,
            "error": str(e),
            "inputs": solver_input
        })


def solve_all_lines(
    jobs_by_line: Dict[int, Dict],
    db: Session,
    max_workers: Optional[int] = None
) -> Dict[int, Dict]:
    """
    Roda o solver para todas as linhas de produção em paralelo.
    
    Retorna: {production_line_id: resultado_do_solver}
    """
    solver_inputs = prepare_solver_inputs(jobs_by_line, db)
    
    if not solver_inputs:
        return {}
    
    print(f"\n[SOLVER] Preparando {len(solver_inputs)} solvers para execução paralela")
    for pl_id in solver_inputs.keys():
        print(f"[SOLVER] - Linha {pl_id}: {jobs_by_line[pl_id]['production_line_name']}")
    
    results = {}
    
    # Rodar solvers em paralelo
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for pl_id, solver_input in solver_inputs.items():
            pl_name = jobs_by_line[pl_id]["production_line_name"]
            future = executor.submit(solve_line, pl_id, solver_input, pl_name)
            futures[future] = pl_id
            print(f"[SOLVER] Submetido solver para Linha {pl_id}")
        
        print(f"[SOLVER] Aguardando conclusão de {len(futures)} solvers...")
        completed_count = 0
        for future in as_completed(futures):
            completed_count += 1
            pl_id = futures[future]  # Pegar pl_id antes de chamar result()
            pl_name = jobs_by_line[pl_id]["production_line_name"]
            print(f"[SOLVER] ({completed_count}/{len(futures)}) Coletando resultado da Linha {pl_id}...")
            try:
                _, result = future.result()  # Descartar pl_id retornado, usar o do dict
                results[pl_id] = result
                print(f"[SOLVER] ✓ Linha {pl_id} ({pl_name}): {result.get('status', 'Unknown')}")
            except Exception as e:
                # Capturar erro e continuar processando outras linhas
                import traceback
                print(f"\n{'!'*80}")
                print(f"[SOLVER] ✗ ERRO no solver da {pl_name} (ID: {pl_id}):")
                traceback.print_exc()
                print(f"{'!'*80}\n")
                results[pl_id] = {
                    "production_line_id": pl_id,
                    "production_line_name": pl_name,
                    "error": f"Erro ao processar solver: {str(e)}"
                }
    
    print(f"[SOLVER] Concluído! Total de resultados coletados: {len(results)}/{len(solver_inputs)}")
    for pl_id, res in results.items():
        status_str = f"ERRO: {res.get('error', 'Unknown')}" if "error" in res else res.get("status", "Unknown")
        print(f"[SOLVER] - Linha {pl_id}: {status_str}")
    
    return results





