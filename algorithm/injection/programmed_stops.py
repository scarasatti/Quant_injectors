"""
Função para criar jobs falsos representando paradas programadas (manutenção, etc).

Essas paradas são tratadas como jobs especiais com:
- Prioridade 99 (muito alta, para serem executadas no horário correto)
- Tempo de processamento = duração da parada (calculado considerando jornada de trabalho)
- Apenas na máquina afetada (outras máquinas recebem 9999)
- Prazo = data de início da parada
"""

from datetime import datetime, date, time
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session

from app.models.regular_shift import RegularShift
from app.models.holiday import Holiday


class ProgrammedStop:
    """
    Representa uma parada programada.
    """
    def __init__(
        self,
        reason: str,
        start_datetime: datetime,
        end_datetime: datetime,
        machine_id: int
    ):
        self.reason = reason
        self.start_datetime = start_datetime
        self.end_datetime = end_datetime
        self.machine_id = machine_id


def calculate_stop_duration(
    start_datetime: datetime,
    end_datetime: datetime,
    db: Session,
    reference_date: Optional[date] = None
) -> float:
    """
    Calcula a duração de uma parada em horas úteis.
    
    Considera a jornada de trabalho regular (turnos) para calcular
    apenas as horas úteis dentro do período da parada.
    
    Args:
        start_datetime: Data e horário de início da parada
        end_datetime: Data e horário de fim da parada
        db: Sessão do banco de dados
        reference_date: Data de referência para cálculo quinzenal
    
    Returns:
        Duração em horas úteis (float)
    """
    if end_datetime <= start_datetime:
        return 0.0
    
    # Usar data de início como referência para cálculo quinzenal
    if reference_date is None:
        reference_date = start_datetime.date()
    
    # Buscar turnos regulares do banco
    regular_shifts = db.query(RegularShift).all()
    
    # Buscar feriados do banco
    holidays = [h.date for h in db.query(Holiday).all()]
    
    # Calcular horas úteis entre início e fim da parada
    from .due_date_calculator import calculate_working_hours_between
    
    duration_hours = calculate_working_hours_between(
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        regular_shifts=regular_shifts,
        holidays=holidays,
        reference_date=reference_date
    )
    
    return max(0.0, duration_hours)


def create_stop_jobs(
    stops: List[ProgrammedStop],
    sequencing_date: datetime,
    machines: List[int],
    db: Session,
    reference_date: Optional[date] = None
) -> Dict:
    """
    Cria jobs falsos representando paradas programadas.
    
    Cada parada vira um job com:
    - Prioridade 99 (muito alta)
    - Tempo de processamento = duração da parada (apenas na máquina afetada)
    - Tempo de processamento = 9999 nas outras máquinas (impossível)
    - Prazo = data de início da parada (calculado considerando jornada de trabalho)
    
    Args:
        stops: Lista de paradas programadas
        sequencing_date: Data e horário de início do sequenciamento
        machines: Lista de IDs das máquinas disponíveis
        db: Sessão do banco de dados
        reference_date: Data de referência para cálculo quinzenal
    
    Returns:
        Dicionário com:
        - stop_jobs: Lista de índices dos jobs de parada (para adicionar aos jobs normais)
        - processing: Dict[(stop_index, machine_id)] -> tempo de processamento
        - due: Dict[stop_index] -> prazo em horas úteis
        - priority: Dict[stop_index] -> prioridade (99)
        - stop_info: Dict[stop_index] -> informações da parada (reason, machine_id, etc)
    """
    if not stops:
        return {
            "stop_jobs": [],
            "processing": {},
            "due": {},
            "priority": {},
            "setup3": {},
            "stop_info": {}
        }
    
    # Usar data de sequenciamento como referência para cálculo quinzenal
    if reference_date is None:
        reference_date = sequencing_date.date()
    
    stop_jobs = []
    processing = {}
    due = {}
    priority = {}
    stop_info = {}
    
    # Buscar turnos regulares e feriados para cálculo de prazo
    regular_shifts = db.query(RegularShift).all()
    holidays = [h.date for h in db.query(Holiday).all()]
    
    from .due_date_calculator import calculate_working_hours_between
    
    for stop_index, stop in enumerate(stops):
        stop_jobs.append(stop_index)
        
        # Calcular duração da parada em horas úteis
        duration_hours = calculate_stop_duration(
            start_datetime=stop.start_datetime,
            end_datetime=stop.end_datetime,
            db=db,
            reference_date=reference_date
        )
        
        # Calcular prazo (horas úteis até o início da parada)
        if stop.start_datetime < sequencing_date:
            # Parada já começou antes do sequenciamento
            due_hours = 0.0
        else:
            due_hours = calculate_working_hours_between(
                start_datetime=sequencing_date,
                end_datetime=stop.start_datetime,
                regular_shifts=regular_shifts,
                holidays=holidays,
                reference_date=reference_date
            )
        
        # Para cada máquina
        for machine_id in machines:
            if machine_id == stop.machine_id:
                # Máquina afetada: tempo de processamento = duração da parada
                processing[(stop_index, machine_id)] = round(duration_hours, 2)
            else:
                # Outras máquinas: impossível processar (9999)
                processing[(stop_index, machine_id)] = 9999.0
        
        # Prazo = horas úteis até o início da parada
        due[stop_index] = round(due_hours, 2)
        
        # Prioridade 99 (muito alta)
        priority[stop_index] = 99.0
        
        # Informações da parada
        stop_info[stop_index] = {
            "reason": stop.reason,
            "machine_id": stop.machine_id,
            "start_datetime": stop.start_datetime,
            "end_datetime": stop.end_datetime
        }
    
    # Calcular setups entre paradas e jobs normais
    # Por padrão, setups entre paradas são 0 (não há setup necessário)
    # Setups de jobs normais para paradas também são 0
    # Setups de paradas para jobs normais também são 0
    setup3 = {}
    # Preencher com 0 para todas as combinações (será sobrescrito pelos setups reais)
    # Isso será mesclado com os setups dos jobs normais no job_calculator
    
    return {
        "stop_jobs": stop_jobs,
        "processing": processing,
        "due": due,
        "priority": priority,
        "setup3": setup3,
        "stop_info": stop_info
    }


def merge_stop_jobs_with_normal_jobs(
    normal_jobs_data: Dict,
    stop_jobs_data: Dict,
    normal_jobs_count: int
) -> Dict:
    """
    Mescla os dados dos jobs normais com os jobs de parada.
    
    Os jobs de parada são adicionados aos jobs normais, com índices
    começando após os jobs normais.
    
    Args:
        normal_jobs_data: Dados dos jobs normais (do calculate_injection_jobs_data)
        stop_jobs_data: Dados dos jobs de parada (do create_stop_jobs)
        normal_jobs_count: Número de jobs normais
    
    Returns:
        Dicionário mesclado com todos os dados
    """
    if not stop_jobs_data["stop_jobs"]:
        return normal_jobs_data
    
    # Ajustar índices dos jobs de parada (começam após os jobs normais)
    stop_jobs_adjusted = [normal_jobs_count + idx for idx in stop_jobs_data["stop_jobs"]]
    
    # Mesclar jobs
    all_jobs = normal_jobs_data["jobs"] + stop_jobs_adjusted
    
    # Mesclar processing (ajustar índices)
    all_processing = dict(normal_jobs_data["processing"])
    for (stop_idx, machine_id), proc_time in stop_jobs_data["processing"].items():
        adjusted_idx = normal_jobs_count + stop_idx
        all_processing[(adjusted_idx, machine_id)] = proc_time
    
    # Mesclar due (ajustar índices)
    all_due = dict(normal_jobs_data["due"])
    for stop_idx, due_time in stop_jobs_data["due"].items():
        adjusted_idx = normal_jobs_count + stop_idx
        all_due[adjusted_idx] = due_time
    
    # Mesclar priority (ajustar índices)
    all_priority = dict(normal_jobs_data["priority"])
    for stop_idx, prio in stop_jobs_data["priority"].items():
        adjusted_idx = normal_jobs_count + stop_idx
        all_priority[adjusted_idx] = prio
    
    # Mesclar setup3
    # Setups entre jobs normais permanecem
    all_setup3 = dict(normal_jobs_data["setup3"])
    
    # Setups envolvendo jobs de parada são 0 (não há setup necessário)
    # Adicionar setups de jobs normais para paradas
    for normal_idx in normal_jobs_data["jobs"]:
        for stop_idx in stop_jobs_data["stop_jobs"]:
            adjusted_stop_idx = normal_jobs_count + stop_idx
            for machine_id in normal_jobs_data["machines"]:
                all_setup3[(normal_idx, adjusted_stop_idx, machine_id)] = 0.0
                all_setup3[(adjusted_stop_idx, normal_idx, machine_id)] = 0.0
    
    # Setups entre paradas também são 0
    for stop_idx1 in stop_jobs_data["stop_jobs"]:
        for stop_idx2 in stop_jobs_data["stop_jobs"]:
            if stop_idx1 != stop_idx2:
                adjusted_idx1 = normal_jobs_count + stop_idx1
                adjusted_idx2 = normal_jobs_count + stop_idx2
                for machine_id in normal_jobs_data["machines"]:
                    all_setup3[(adjusted_idx1, adjusted_idx2, machine_id)] = 0.0
    
    # Mesclar stop_info (ajustar índices)
    all_stop_info = {}
    for stop_idx, info in stop_jobs_data["stop_info"].items():
        adjusted_idx = normal_jobs_count + stop_idx
        all_stop_info[adjusted_idx] = info
    
    return {
        "jobs": all_jobs,
        "machines": normal_jobs_data["machines"],
        "processing": all_processing,
        "due": all_due,
        "priority": all_priority,
        "setup3": all_setup3,
        "job_to_composition_line": normal_jobs_data.get("job_to_composition_line", {}),
        "composition_line_to_machines": normal_jobs_data.get("composition_line_to_machines", {}),
        "errors": normal_jobs_data.get("errors", []),
        "stop_info": all_stop_info
    }

