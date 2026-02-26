"""
Função para calcular o prazo (due date) considerando a jornada de trabalho regular.

O prazo é calculado como as horas úteis entre:
- Data e horário de início do sequenciamento
- Data limite de faturamento do job (promised_date)

Considera apenas as horas dentro da jornada de trabalho cadastrada nos turnos regulares.
Usa os horários reais de início/fim dos turnos quando disponíveis, senão usa fallback de 8 horas.
Se um turno está marcado como "Quinzenal", ele só existe a cada 15 dias.
Se a data limite for anterior ao início do sequenciamento, retorna 0.
"""

from datetime import datetime, date, time, timedelta
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session

from app.models.regular_shift import RegularShift, FrequenciaTurno, DiaSemana
from app.models.holiday import Holiday
from app.models.billing_configuration import BillingConfiguration, BillingRuleType

# Fallback: 8 horas por turno se não houver horários definidos
HORAS_POR_TURNO_FALLBACK = 8.0


def is_quinzenal_active(
    check_date: date,
    shift: RegularShift,
    reference_date: date,
    next_saturday_is_working: bool = False
) -> bool:
    """
    Verifica se um turno quinzenal está ativo em uma data específica.
    
    Para sábados quinzenais (alternado semanalmente - um sim, um não):
    - Se next_saturday_is_working == True: o próximo sábado após reference_date trabalha
    - Se next_saturday_is_working == False: pula o próximo sábado, o seguinte trabalha
    - Depois alterna a cada 7 dias (sábado sim, sábado não)
    
    Para outros dias quinzenais: múltiplo de 15 dias a partir de reference_date.
    
    Args:
        check_date: Data a verificar
        shift: Turno regular (para verificar frequência)
        reference_date: Data de referência (geralmente início do sequenciamento)
        next_saturday_is_working: Se True, o próximo sábado após reference_date é trabalhado
    
    Returns:
        True se o turno está ativo nesta data, False caso contrário
    """
    if shift.frequencia != FrequenciaTurno.QUINZENAL:
        return True  # Turnos diários sempre estão ativos
    
    # Lógica especial para sábados quinzenais (alternado semanalmente)
    if shift.dia_semana == DiaSemana.SABADO:
        # Encontrar o próximo sábado >= reference_date
        # weekday(): segunda=0 ... sábado=5, domingo=6
        dias_ate_sabado = (5 - reference_date.weekday()) % 7
        primeiro_sabado = reference_date + timedelta(days=dias_ate_sabado)
        
        # Se next_saturday_is_working == False, o primeiro sábado trabalhado é o seguinte
        if not next_saturday_is_working:
            primeiro_sabado = primeiro_sabado + timedelta(days=7)
        
        if check_date < primeiro_sabado:
            return False
        
        # Verificar se está a cada 14 dias (alternando semanalmente) a partir do primeiro sábado trabalhado
        # Para alternar: verifica se a diferença em semanas é par (múltiplos de 14 dias)
        dias_diff = (check_date - primeiro_sabado).days
        return dias_diff % 14 == 0
    
    # Outros dias quinzenais: múltiplo de 15 dias
    days_diff = (check_date - reference_date).days
    return days_diff % 15 == 0


def _get_shift_time(shift: RegularShift, turno: str) -> Optional[time]:
    """Tenta obter o horário de início/fim do turno do banco (mesmo que não esteja no modelo)."""
    try:
        # Tentar acessar os campos diretamente (podem existir no banco mas não no modelo)
        if turno == "manha_inicio":
            return getattr(shift, 'manha_inicio', None)
        elif turno == "manha_fim":
            return getattr(shift, 'manha_fim', None)
        elif turno == "tarde_inicio":
            return getattr(shift, 'tarde_inicio', None)
        elif turno == "tarde_fim":
            return getattr(shift, 'tarde_fim', None)
        elif turno == "noite_inicio":
            return getattr(shift, 'noite_inicio', None)
        elif turno == "noite_fim":
            return getattr(shift, 'noite_fim', None)
    except:
        pass
    return None


def _add_interval(
    intervals: List[Tuple[datetime, datetime]],
    start_dt: datetime,
    end_dt: datetime,
) -> None:
    """Adiciona um intervalo [start_dt, end_dt] se tiver duração positiva."""
    if end_dt > start_dt:
        intervals.append((start_dt, end_dt))


def get_work_intervals_for_date(
    current_date: date,
    regular_shifts: List[RegularShift],
    holidays: List[date],
    reference_date: date,
    next_saturday_is_working: bool,
) -> List[Tuple[datetime, datetime]]:
    """
    Retorna a lista de intervalos de trabalho (start_dt, end_dt) para o dia.
    
    Usa os horários reais de início/fim dos turnos quando disponíveis.
    Se não houver horários, usa fallback de 8 horas por turno.
    """
    if is_holiday(current_date, holidays):
        return []
    
    weekday_map = {
        0: DiaSemana.SEGUNDA,
        1: DiaSemana.TERCA,
        2: DiaSemana.QUARTA,
        3: DiaSemana.QUINTA,
        4: DiaSemana.SEXTA,
        5: DiaSemana.SABADO,
        6: DiaSemana.DOMINGO,
    }
    
    dia_semana = weekday_map[current_date.weekday()]
    shift = next((s for s in regular_shifts if s.dia_semana == dia_semana), None)
    
    if not shift:
        return []
    
    if shift.frequencia == FrequenciaTurno.NAO_TRABALHA:
        return []
    
    if shift.frequencia == FrequenciaTurno.QUINZENAL:
        if not is_quinzenal_active(current_date, shift, reference_date, next_saturday_is_working):
            return []
    
    intervals: List[Tuple[datetime, datetime]] = []
    
    # Turno da manhã
    if shift.manha:
        manha_inicio = _get_shift_time(shift, "manha_inicio")
        manha_fim = _get_shift_time(shift, "manha_fim")
        if manha_inicio and manha_fim:
            start_dt = datetime.combine(current_date, manha_inicio)
            end_dt = datetime.combine(current_date, manha_fim)
            _add_interval(intervals, start_dt, end_dt)
        else:
            # Fallback: 06:00-14:00 (8 horas)
            start_dt = datetime.combine(current_date, time(6, 0, 0))
            end_dt = start_dt + timedelta(hours=HORAS_POR_TURNO_FALLBACK)
            _add_interval(intervals, start_dt, end_dt)
    
    # Turno da tarde
    if shift.tarde:
        tarde_inicio = _get_shift_time(shift, "tarde_inicio")
        tarde_fim = _get_shift_time(shift, "tarde_fim")
        if tarde_inicio and tarde_fim:
            start_dt = datetime.combine(current_date, tarde_inicio)
            end_dt = datetime.combine(current_date, tarde_fim)
            _add_interval(intervals, start_dt, end_dt)
        else:
            # Fallback: 14:00-22:00 (8 horas)
            start_dt = datetime.combine(current_date, time(14, 0, 0))
            end_dt = start_dt + timedelta(hours=HORAS_POR_TURNO_FALLBACK)
            _add_interval(intervals, start_dt, end_dt)
    
    # Turno da noite (pode cruzar a meia-noite)
    if shift.noite:
        noite_inicio = _get_shift_time(shift, "noite_inicio")
        noite_fim = _get_shift_time(shift, "noite_fim")
        if noite_inicio and noite_fim:
            start_dt = datetime.combine(current_date, noite_inicio)
            end_dt = datetime.combine(current_date, noite_fim)
            # Se o fim for menor/igual ao início, assume que cruza meia-noite
            if end_dt <= start_dt:
                end_dt = end_dt + timedelta(days=1)
            _add_interval(intervals, start_dt, end_dt)
        else:
            # Fallback: 22:00-06:00 (8h cruzando meia-noite)
            start_dt = datetime.combine(current_date, time(22, 0, 0))
            end_dt = start_dt + timedelta(hours=HORAS_POR_TURNO_FALLBACK)
            _add_interval(intervals, start_dt, end_dt)
    
    return intervals


def is_holiday(check_date: date, holidays: List[date]) -> bool:
    """Verifica se uma data é feriado."""
    return check_date in holidays


def is_weekday(check_date: date) -> bool:
    """
    Verifica se uma data é dia de semana (segunda a sexta).
    
    Args:
        check_date: Data a verificar
        
    Returns:
        True se for dia de semana (segunda a sexta), False caso contrário
    """
    # weekday(): segunda=0, terça=1, quarta=2, quinta=3, sexta=4, sábado=5, domingo=6
    return check_date.weekday() < 5


def is_billing_allowed(
    check_datetime: datetime,
    billing_config: BillingConfiguration,
    holidays: List[date]
) -> bool:
    """
    Verifica se o faturamento é permitido em uma determinada data e horário.
    
    Args:
        check_datetime: Data e horário a verificar
        billing_config: Configuração de faturamento ativa
        holidays: Lista de datas de feriados
        
    Returns:
        True se o faturamento é permitido, False caso contrário
    """
    check_date = check_datetime.date()
    check_time = check_datetime.time()
    
    # Regra 1: Segunda a Sexta (sem feriados)
    if billing_config.rule_type == BillingRuleType.WEEKDAYS_NO_HOLIDAYS:
        # Deve ser dia de semana E não ser feriado E estar dentro do horário
        if not is_weekday(check_date):
            return False
        if is_holiday(check_date, holidays):
            return False
        if billing_config.billing_deadline_time and check_time > billing_config.billing_deadline_time:
            return False
        return True
    
    # Regra 2: Todos os dias (incluindo feriados)
    elif billing_config.rule_type == BillingRuleType.ALL_DAYS_WITH_HOLIDAYS:
        # Qualquer dia, mas deve estar dentro do horário
        if billing_config.billing_deadline_time and check_time > billing_config.billing_deadline_time:
            return False
        return True
    
    # Regra 3: Todos os dias (sem feriados)
    elif billing_config.rule_type == BillingRuleType.ALL_DAYS_NO_HOLIDAYS:
        # Qualquer dia exceto feriados E dentro do horário
        if is_holiday(check_date, holidays):
            return False
        if billing_config.billing_deadline_time and check_time > billing_config.billing_deadline_time:
            return False
        return True
    
    # Regra 4: 24/7 (sempre disponível)
    elif billing_config.rule_type == BillingRuleType.ALWAYS:
        # Sempre permitido, independente do dia ou horário
        return True
    
    # Caso não reconhecido (não deveria acontecer)
    return False


def get_next_billing_allowed_datetime(
    start_datetime: datetime,
    billing_config: BillingConfiguration,
    holidays: List[date],
    max_days_ahead: int = 365
) -> Optional[datetime]:
    """
    Encontra o próximo momento em que o faturamento é permitido.
    
    Útil para calcular quando um job pode ser faturado se o horário atual não permitir.
    
    Args:
        start_datetime: Data e horário de partida
        billing_config: Configuração de faturamento ativa
        holidays: Lista de datas de feriados
        max_days_ahead: Máximo de dias a procurar no futuro
        
    Returns:
        O próximo datetime onde faturamento é permitido, ou None se não encontrar
    """
    # Se a regra é ALWAYS, o faturamento já é permitido
    if billing_config.rule_type == BillingRuleType.ALWAYS:
        return start_datetime
    
    current = start_datetime
    
    for _ in range(max_days_ahead):
        # Se o faturamento é permitido neste momento, retornar
        if is_billing_allowed(current, billing_config, holidays):
            return current
        
        # Avançar para o próximo momento lógico
        current_date = current.date()
        
        # Se já passou do horário limite hoje, ir para o início do próximo dia permitido
        if billing_config.billing_deadline_time and current.time() >= billing_config.billing_deadline_time:
            # Ir para o início do próximo dia (00:00:00)
            current = datetime.combine(current_date + timedelta(days=1), time(0, 0, 0))
        else:
            # Ainda estamos dentro do horário do dia, então o dia que não é permitido
            # Ir para o início do próximo dia
            current = datetime.combine(current_date + timedelta(days=1), time(0, 0, 0))
    
    # Não encontrou um momento permitido dentro do limite de dias
    return None


def calculate_working_hours_between(
    start_datetime: datetime,
    end_datetime: datetime,
    regular_shifts: List[RegularShift],
    holidays: List[date],
    reference_date: Optional[date] = None,
    next_saturday_is_working: bool = False
) -> float:
    """
    Calcula o total de horas úteis entre duas datas/horários.
    
    Percorre dia a dia, monta os intervalos de trabalho reais usando horários de início/fim
    e soma apenas a interseção com [start_datetime, end_datetime].
    
    Args:
        start_datetime: Data e horário de início
        end_datetime: Data e horário de fim
        regular_shifts: Lista de RegularShift do banco
        holidays: Lista de datas de feriados
        reference_date: Data de referência para cálculo quinzenal (usa start_datetime.date() se None)
        next_saturday_is_working: Se True, o próximo sábado após reference_date é trabalhado
    
    Returns:
        Total de horas úteis (float)
    """
    if end_datetime <= start_datetime:
        return 0.0
    
    # Usar data de início como referência para cálculo quinzenal
    if reference_date is None:
        reference_date = start_datetime.date()
    
    total_hours = 0.0
    current_date = start_datetime.date()
    end_date = end_datetime.date()
    
    while current_date <= end_date:
        intervals = get_work_intervals_for_date(
            current_date=current_date,
            regular_shifts=regular_shifts,
            holidays=holidays,
            reference_date=reference_date,
            next_saturday_is_working=next_saturday_is_working,
        )
        
        for interval_start, interval_end in intervals:
            # Interseção com a janela global [start_datetime, end_datetime]
            start = max(interval_start, start_datetime)
            end = min(interval_end, end_datetime)
            if end > start:
                total_hours += (end - start).total_seconds() / 3600.0
        
        current_date += timedelta(days=1)
    
    return round(total_hours, 2)


def add_working_hours(
    start_datetime: datetime,
    hours_to_add: float,
    regular_shifts: List[RegularShift],
    holidays: List[date],
    reference_date: Optional[date] = None,
    next_saturday_is_working: bool = False
) -> datetime:
    """
    Adiciona horas ÚTEIS respeitando turnos, feriados e sábados quinzenais.
    """
    if hours_to_add <= 0:
        return start_datetime
    
    if reference_date is None:
        reference_date = start_datetime.date()
    
    remaining_hours = hours_to_add
    current_datetime = start_datetime
    current_date = start_datetime.date()
    max_days = 365
    days_searched = 0
    
    while remaining_hours > 0 and days_searched < max_days:
        intervals = get_work_intervals_for_date(
            current_date=current_date,
            regular_shifts=regular_shifts,
            holidays=holidays,
            reference_date=reference_date,
            next_saturday_is_working=next_saturday_is_working,
        )
        
        for interval_start, interval_end in intervals:
            if current_datetime < interval_start:
                current_datetime = interval_start
            
            if current_datetime >= interval_end:
                continue
            
            available_hours = (interval_end - current_datetime).total_seconds() / 3600.0
            
            if available_hours >= remaining_hours:
                current_datetime += timedelta(hours=remaining_hours)
                return current_datetime
            else:
                remaining_hours -= available_hours
                current_datetime = interval_end
        
        current_date += timedelta(days=1)
        current_datetime = datetime.combine(current_date, datetime.min.time())
        days_searched += 1
    
    return current_datetime


def validate_billing_date(
    promised_date: datetime,
    db: Session
) -> Tuple[bool, Optional[str], Optional[datetime]]:
    """
    Valida se uma data de faturamento prometida está dentro das regras de faturamento configuradas.
    
    Args:
        promised_date: Data e horário prometido para faturamento
        db: Sessão do banco de dados
        
    Returns:
        Tupla contendo:
        - bool: True se a data é válida, False caso contrário
        - str: Mensagem de erro (None se válido)
        - datetime: Sugestão de próxima data válida (None se a data original for válida)
    """
    # Buscar configuração ativa
    billing_config = db.query(BillingConfiguration).filter(
        BillingConfiguration.is_active == True
    ).first()
    
    # Se não houver configuração, permitir qualquer data (comportamento padrão)
    if not billing_config:
        return True, None, None
    
    # Buscar feriados
    holidays = [h.date for h in db.query(Holiday).all()]
    
    # Verificar se a data prometida está dentro das regras
    if is_billing_allowed(promised_date, billing_config, holidays):
        return True, None, None
    
    # A data não é permitida, encontrar a próxima data válida
    next_valid = get_next_billing_allowed_datetime(
        promised_date, 
        billing_config, 
        holidays
    )
    
    # Montar mensagem de erro apropriada
    if billing_config.rule_type == BillingRuleType.WEEKDAYS_NO_HOLIDAYS:
        error_msg = "Faturamento só é permitido de segunda a sexta-feira (excluindo feriados)"
        if billing_config.billing_deadline_time:
            error_msg += f" até às {billing_config.billing_deadline_time.strftime('%H:%M')}"
    elif billing_config.rule_type == BillingRuleType.ALL_DAYS_WITH_HOLIDAYS:
        error_msg = f"Faturamento só é permitido até às {billing_config.billing_deadline_time.strftime('%H:%M')}"
    elif billing_config.rule_type == BillingRuleType.ALL_DAYS_NO_HOLIDAYS:
        error_msg = "Faturamento não é permitido em feriados"
        if billing_config.billing_deadline_time:
            error_msg += f" e deve ser realizado até às {billing_config.billing_deadline_time.strftime('%H:%M')}"
    else:
        error_msg = "Data de faturamento não permitida pela configuração atual"
    
    return False, error_msg, next_valid


def calculate_due_date(
    promised_date: datetime,
    sequencing_date: datetime,
    db: Session,
    reference_date: Optional[date] = None,
    next_saturday_is_working: bool = False,
    validate_billing_rules: bool = False
) -> float:
    """
    Calcula o prazo (due date) em horas úteis.
    
    O prazo é calculado como as horas úteis entre a data de início do sequenciamento
    e a data limite de faturamento (promised_date), considerando a jornada regular de trabalho.
    
    Usa os horários reais de início/fim dos turnos quando disponíveis.
    Turnos quinzenais só são considerados quando estão ativos (a cada 15 dias).
    Para sábados quinzenais, considera next_saturday_is_working.
    
    Se a data limite for anterior à data do início do sequenciamento, retorna 0.
    
    NOTA: Esta função calcula o prazo baseado nas horas de trabalho regulares.
    Se desejar validar se a data de faturamento está dentro das regras de faturamento
    configuradas, use a função validate_billing_date() separadamente.
    
    Args:
        promised_date: Data e horário limite de faturamento do job
        sequencing_date: Data e horário de início do sequenciamento
        db: Sessão do banco de dados
        reference_date: Data de referência para cálculo quinzenal (usa sequencing_date.date() se None)
        next_saturday_is_working: Se True, o próximo sábado após sequencing_date é trabalhado
        validate_billing_rules: Se True, valida se promised_date está dentro das regras de faturamento
                               (levanta exceção se não estiver)
    
    Returns:
        Prazo em horas úteis (float). Retorna 0 se o job já está atrasado.
        
    Raises:
        ValueError: Se validate_billing_rules=True e a data não estiver dentro das regras
    """
    # Validar regras de faturamento se solicitado
    if validate_billing_rules:
        is_valid, error_msg, next_valid = validate_billing_date(promised_date, db)
        if not is_valid:
            suggestion = ""
            if next_valid:
                suggestion = f" Próxima data válida: {next_valid.strftime('%d/%m/%Y %H:%M')}"
            raise ValueError(f"{error_msg}.{suggestion}")
    
    # Se a data limite for anterior ao início do sequenciamento, retorna 0
    if promised_date < sequencing_date:
        return 0.0
    
    # Usar data de sequenciamento como referência para cálculo quinzenal
    if reference_date is None:
        reference_date = sequencing_date.date()
    
    # Buscar turnos regulares do banco
    regular_shifts = db.query(RegularShift).all()
    
    # Buscar feriados do banco
    holidays = [h.date for h in db.query(Holiday).all()]
    
    # Calcular horas úteis
    working_hours = calculate_working_hours_between(
        start_datetime=sequencing_date,
        end_datetime=promised_date,
        regular_shifts=regular_shifts,
        holidays=holidays,
        reference_date=reference_date,
        next_saturday_is_working=next_saturday_is_working
    )
    
    return max(0.0, working_hours)


def calculate_billing_date(
    production_completion: datetime,
    db: Session
) -> date:
    """
    Calcula a data de faturamento baseada na data/hora de conclusão da produção
    e nas regras de configuração de faturamento.
    
    Regras:
    1. WEEKDAYS_NO_HOLIDAYS (Segunda a sexta excluindo feriados até horário limite):
       - Se conclusão for em dia útil e dentro do horário: fatura no mesmo dia
       - Se fim de semana, feriado ou após horário: fatura no próximo dia útil permitido
    
    2. ALL_DAYS_WITH_HOLIDAYS (Qualquer dia incluindo feriados dentro do horário limite):
       - Se dentro do horário limite: fatura no mesmo dia
       - Se após horário limite: fatura no próximo dia (às 00:00)
    
    3. ALL_DAYS_NO_HOLIDAYS (Qualquer dia excluindo feriados dentro do horário limite):
       - Similar ao ALL_DAYS_WITH_HOLIDAYS mas pula feriados
    
    4. ALWAYS (24/7 - qualquer dia a qualquer horário):
       - Sempre fatura no dia e horário de conclusão
    
    Args:
        production_completion: Data e horário de conclusão da produção
        db: Sessão do banco de dados
        
    Returns:
        Data de faturamento (date)
    """
    # Buscar configuração ativa
    billing_config = db.query(BillingConfiguration).filter(
        BillingConfiguration.is_active == True
    ).first()
    
    # Se não houver configuração, usar comportamento padrão (mesmo dia)
    if not billing_config:
        return production_completion.date()
    
    # Buscar feriados
    holidays = [h.date for h in db.query(Holiday).all()]
    
    # Verificar se o faturamento é permitido na data/hora de conclusão
    if is_billing_allowed(production_completion, billing_config, holidays):
        # Faturamento permitido no momento da conclusão
        return production_completion.date()
    
    # Faturamento não permitido, encontrar próximo momento válido
    next_billing = get_next_billing_allowed_datetime(
        production_completion,
        billing_config,
        holidays
    )
    
    if next_billing:
        return next_billing.date()
    
    # Caso não encontre (não deveria acontecer), retornar a data de conclusão
    return production_completion.date()
