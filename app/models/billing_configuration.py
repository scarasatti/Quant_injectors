from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, Time, Boolean
from sqlalchemy import Enum as SqlEnum
from app.database import Base


class BillingRuleType(str, PyEnum):
    """Tipos de regras de faturamento disponíveis"""
    WEEKDAYS_NO_HOLIDAYS = "Segunda a Sexta (sem feriados)"
    ALL_DAYS_WITH_HOLIDAYS = "Todos os dias (incluindo feriados)"
    ALL_DAYS_NO_HOLIDAYS = "Todos os dias (sem feriados)"
    ALWAYS = "24/7 (sempre disponível)"


class BillingConfiguration(Base):
    """
    Configuração de dias e horários permitidos para faturamento.
    
    Esta tabela deve ter apenas um registro ativo por vez (singleton).
    A configuração define quando é permitido realizar o faturamento baseado em:
    - Tipo de regra (dias da semana, feriados)
    - Horário limite (quando aplicável)
    
    Esta configuração substitui o horário de faturamento atual e passa a executar
    a regra definida, verificando feriados através do calendário previamente cadastrado.
    """
    __tablename__ = "billing_configuration"

    id = Column(Integer, primary_key=True, index=True)
    
    # Tipo de regra de faturamento
    rule_type = Column(SqlEnum(BillingRuleType), nullable=False)
    
    # Horário limite para faturamento (NULL quando rule_type = ALWAYS)
    # Representa a hora máxima do dia em que o faturamento pode ser realizado
    billing_deadline_time = Column(Time, nullable=True)
    
    # Flag para indicar se esta é a configuração ativa
    # Apenas um registro pode ter is_active = True por vez
    is_active = Column(Boolean, default=True, nullable=False)

