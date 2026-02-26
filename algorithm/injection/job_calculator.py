"""
Função para calcular e preparar os dados dos jobs para o solver de injetoras.

Esta função adapta os dados do banco de dados para o formato esperado pelo solver,
considerando a nova estrutura de tabelas (CompositionLine, ProductionTime, Setup, etc.).
"""

from datetime import datetime
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session, joinedload
import math

from app.models.job import Job
from app.models.composition_line import CompositionLine
from app.models.production_time import ProductionTime
from app.models.machine import Machine
from app.models.setup import Setup
from .due_date_calculator import calculate_due_date
from .programmed_stops import ProgrammedStop, create_stop_jobs, merge_stop_jobs_with_normal_jobs


def calculate_injection_jobs_data(
    jobs_data: List[Job],
    sequencing_date: datetime,
    machine_availability: Optional[int] = None,
    db: Session = None,
    programmed_stops: Optional[List[ProgrammedStop]] = None,
) -> Dict:
    """
    Calcula todos os dados necessários para o solver de injetoras a partir dos jobs do banco.
    
    Esta função adapta a função antiga calculate_processing_time para o novo sistema,
    considerando:
    - CompositionLine (liga product, mold, production_line)
    - ProductionTime (tempo_ciclo por machine+product+mold)
    - Setup (tempos entre composition_lines)
    - Mold (scrap percentual)
    - Machine (availability)
    
    Args:
        jobs_data: Lista de objetos Job do banco de dados
        sequencing_date: Data e hora de início do sequenciamento
        machine_availability: Percentual de disponibilidade da máquina (1-100). 
                            Se None, usa a disponibilidade de cada máquina individual.
        db: Sessão do banco de dados (necessária para buscar dados relacionados)
    
    Returns:
        Dicionário com as seguintes chaves:
        - jobs: Lista de IDs dos jobs (índices 0, 1, 2, ...)
        - machines: Lista de IDs das máquinas disponíveis
        - processing: Dict[(job_index, machine_id)] -> tempo de processamento em horas
        - due: Dict[job_index] -> prazo em horas
        - priority: Dict[job_index] -> prioridade do job
        - setup3: Dict[(job_i_index, job_j_index, machine_id)] -> tempo de setup em horas
        - job_to_composition_line: Dict[job_index] -> composition_line_id
        - composition_line_to_machines: Dict[composition_line_id] -> List[machine_id]
        - errors: Lista de erros encontrados durante o cálculo
    """
    errors = []
    
    # Mapear jobs para índices
    jobs = list(range(len(jobs_data)))
    
    # Buscar composition_lines para cada job
    job_to_composition_line = {}
    job_to_composition_line_obj = {}
    
    for i, job in enumerate(jobs_data):
        # Busca a primeira composition_line que tem o produto do job
        composition_line = db.query(CompositionLine).filter_by(
            product_id=job.fk_id_product
        ).options(
            joinedload(CompositionLine.mold),
            joinedload(CompositionLine.product),
            joinedload(CompositionLine.machines).joinedload("machine")
        ).first()
        
        if not composition_line:
            errors.append(
                f"Job {job.id} ({job.name}): Nenhuma composition line encontrada para o produto {job.product.name}"
            )
            continue
        
        job_to_composition_line[i] = composition_line.id
        job_to_composition_line_obj[i] = composition_line
    
    if errors:
        return {
            "jobs": jobs,
            "machines": [],
            "processing": {},
            "due": {},
            "priority": {},
            "setup3": {},
            "job_to_composition_line": job_to_composition_line,
            "composition_line_to_machines": {},
            "errors": errors
        }
    
    # Coletar todas as máquinas disponíveis (das composition_lines)
    all_machines = set()
    composition_line_to_machines = {}
    
    for i, comp_line_id in job_to_composition_line.items():
        comp_line = job_to_composition_line_obj[i]
        machine_ids = [clm.machine_id for clm in comp_line.machines]
        composition_line_to_machines[comp_line_id] = machine_ids
        all_machines.update(machine_ids)
    
    machines = sorted(list(all_machines))
    
    if not machines:
        errors.append("Nenhuma máquina encontrada nas composition lines")
        return {
            "jobs": jobs,
            "machines": [],
            "processing": {},
            "due": {},
            "priority": {},
            "setup3": {},
            "job_to_composition_line": job_to_composition_line,
            "composition_line_to_machines": composition_line_to_machines,
            "errors": errors
        }
    
    # Calcular tempos de processamento para cada (job, máquina)
    processing = {}
    
    for i, job in enumerate(jobs_data):
        comp_line = job_to_composition_line_obj[i]
        mold = comp_line.mold
        product = comp_line.product
        
        # Cálculo do refugo (agora vem do Mold)
        scrap_percent = float(mold.scrap) if mold.scrap else 0.0
        scrap_factor = 1 + scrap_percent / 100
        demand_with_scrap = job.demand * scrap_factor
        
        # Para cada máquina possível
        for machine_id in machines:
            # Verificar se a máquina está disponível para esta composition_line
            if machine_id not in composition_line_to_machines[comp_line.id]:
                # Se a máquina não está disponível, tempo de processamento é 9999
                processing[(i, machine_id)] = 9999
                continue
            
            # Buscar ProductionTime para (machine, product, mold)
            production_time = db.query(ProductionTime).filter_by(
                machine_id=machine_id,
                product_id=product.id,
                mold_id=mold.id
            ).first()
            
            if not production_time:
                errors.append(
                    f"Job {job.id} ({job.name}): ProductionTime não encontrado para "
                    f"máquina {machine_id}, produto {product.name}, molde {mold.name}"
                )
                processing[(i, machine_id)] = 0.0
                continue
            
            # Tempo de ciclo (em segundos) - tempo por unidade
            cycle_time = production_time.tempo_ciclo
            
            # Tempo pós-injeção (em segundos) - tempo por ciclo (bottleneck)
            # Este é o tempo de processamento pós-injeção, que é um gargalo
            post_injection_time = comp_line.post_injection_cycle_time
            
            # Fator de disponibilidade da máquina
            if machine_availability is not None:
                # Usa o valor fornecido
                available_factor = (100 - machine_availability) / 100 + 1
            else:
                # Busca a disponibilidade da máquina específica
                machine = db.query(Machine).filter_by(id=machine_id).first()
                if machine:
                    available_factor = (100 - float(machine.availability)) / 100 + 1
                else:
                    available_factor = 1.0
            
            # Tempo de processamento no gargalo (in-bottleneck)
            # Ciclo * demanda_com_refugo * fator_disponibilidade
            in_bottleneck_time_seconds = cycle_time * demand_with_scrap * available_factor
            
            # Converter para horas e arredondar (apenas o tempo no gargalo)
            # O tempo pós-injeção (bottleneck) será tratado separadamente se necessário
            total_time_hours = math.ceil((in_bottleneck_time_seconds / 3600) * 10) / 10
            
            processing[(i, machine_id)] = round(total_time_hours, 2)
    
    # Calcular prazos (due dates) considerando jornada de trabalho
    due = {}
    for i, job in enumerate(jobs_data):
        promised_date = job.promised_date
        if promised_date:
            # Usar a função que considera a jornada regular de trabalho
            deadline_hours = calculate_due_date(
                promised_date=promised_date,
                sequencing_date=sequencing_date,
                db=db
            )
            due[i] = max(round(deadline_hours, 2), 0.0)
        else:
            due[i] = 0.0
    
    # Calcular prioridades (vem do cliente)
    priority = {}
    for i, job in enumerate(jobs_data):
        if job.client and job.client.priority:
            priority[i] = float(job.client.priority)
        else:
            priority[i] = 1.0  # Prioridade padrão
    
    # Calcular tempos de setup entre jobs (por máquina)
    setup3 = {}
    setups_faltando = []
    
    for i, job_i in enumerate(jobs_data):
        for j, job_j in enumerate(jobs_data):
            if i == j:
                continue
            
            comp_line_i_id = job_to_composition_line[i]
            comp_line_j_id = job_to_composition_line[j]
            
            # Para cada máquina, buscar o setup entre as composition_lines
            for machine_id in machines:
                # Buscar setup entre as composition_lines
                # Nota: Setup é por production_line, então precisamos verificar se ambas
                # composition_lines pertencem à mesma production_line
                comp_line_i = job_to_composition_line_obj[i]
                comp_line_j = job_to_composition_line_obj[j]
                
                if comp_line_i.production_line_id != comp_line_j.production_line_id:
                    # Se estão em production_lines diferentes, setup pode ser 0 ou precisar de outra lógica
                    setup3[(i, j, machine_id)] = 0.0
                    continue
                
                setup = db.query(Setup).filter_by(
                    production_line_id=comp_line_i.production_line_id,
                    from_composition_line_id=comp_line_i_id,
                    to_composition_line_id=comp_line_j_id
                ).first()
                
                if setup:
                    # Converter de segundos para horas
                    setup_hours = math.ceil((setup.setup_time / 3600) * 10) / 10
                    setup3[(i, j, machine_id)] = round(setup_hours, 2)
                else:
                    # Setup não encontrado
                    setup3[(i, j, machine_id)] = 0.0
                    # Adicionar à lista de setups faltando (apenas uma vez por par)
                    if machine_id == machines[0]:  # Só adiciona uma vez por par de jobs
                        from_label = f"M{comp_line_i.mold_id}-{comp_line_i.product.name}"
                        to_label = f"M{comp_line_j.mold_id}-{comp_line_j.product.name}"
                        setups_faltando.append(f"{from_label} ➜ {to_label}")
    
    if setups_faltando:
        errors.append(
            f"Setups faltando entre os seguintes produtos: {', '.join(set(setups_faltando))}"
        )
    
    # Dados dos jobs normais
    normal_jobs_data = {
        "jobs": jobs,
        "machines": machines,
        "processing": processing,
        "due": due,
        "priority": priority,
        "setup3": setup3,
        "job_to_composition_line": job_to_composition_line,
        "composition_line_to_machines": composition_line_to_machines,
        "errors": errors
    }
    
    # Se há paradas programadas, criar jobs falsos e mesclar
    if programmed_stops:
        stop_jobs_data = create_stop_jobs(
            stops=programmed_stops,
            sequencing_date=sequencing_date,
            machines=machines,
            db=db
        )
        
        # Mesclar jobs normais com jobs de parada
        merged_data = merge_stop_jobs_with_normal_jobs(
            normal_jobs_data=normal_jobs_data,
            stop_jobs_data=stop_jobs_data,
            normal_jobs_count=len(jobs)
        )
        
        return merged_data
    
    return normal_jobs_data

