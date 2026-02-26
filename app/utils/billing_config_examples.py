"""
Exemplos e utilitários para configuração de faturamento.

Este arquivo contém exemplos de como criar e usar diferentes configurações de faturamento.
"""

from datetime import time
from sqlalchemy.orm import Session
from app.models.billing_configuration import BillingConfiguration, BillingRuleType


def create_weekdays_config(db: Session, deadline_hour: int = 18, deadline_minute: int = 0) -> BillingConfiguration:
    """
    Cria configuração para faturamento apenas em dias úteis (segunda a sexta, sem feriados).
    
    Args:
        db: Sessão do banco de dados
        deadline_hour: Hora limite para faturamento (0-23)
        deadline_minute: Minuto limite para faturamento (0-59)
        
    Returns:
        Configuração criada
        
    Exemplo:
        # Permitir faturamento de segunda a sexta até as 18:00
        config = create_weekdays_config(db, deadline_hour=18, deadline_minute=0)
    """
    # Desativar configurações existentes
    db.query(BillingConfiguration).update({"is_active": False})
    
    config = BillingConfiguration(
        rule_type=BillingRuleType.WEEKDAYS_NO_HOLIDAYS,
        billing_deadline_time=time(deadline_hour, deadline_minute, 0),
        is_active=True
    )
    
    db.add(config)
    db.commit()
    db.refresh(config)
    
    return config


def create_everyday_with_holidays_config(db: Session, deadline_hour: int = 23, deadline_minute: int = 59) -> BillingConfiguration:
    """
    Cria configuração para faturamento todos os dias, incluindo feriados.
    
    Args:
        db: Sessão do banco de dados
        deadline_hour: Hora limite para faturamento (0-23)
        deadline_minute: Minuto limite para faturamento (0-59)
        
    Returns:
        Configuração criada
        
    Exemplo:
        # Permitir faturamento todos os dias até as 23:59
        config = create_everyday_with_holidays_config(db, deadline_hour=23, deadline_minute=59)
    """
    # Desativar configurações existentes
    db.query(BillingConfiguration).update({"is_active": False})
    
    config = BillingConfiguration(
        rule_type=BillingRuleType.ALL_DAYS_WITH_HOLIDAYS,
        billing_deadline_time=time(deadline_hour, deadline_minute, 0),
        is_active=True
    )
    
    db.add(config)
    db.commit()
    db.refresh(config)
    
    return config


def create_everyday_no_holidays_config(db: Session, deadline_hour: int = 20, deadline_minute: int = 0) -> BillingConfiguration:
    """
    Cria configuração para faturamento todos os dias, exceto feriados.
    
    Args:
        db: Sessão do banco de dados
        deadline_hour: Hora limite para faturamento (0-23)
        deadline_minute: Minuto limite para faturamento (0-59)
        
    Returns:
        Configuração criada
        
    Exemplo:
        # Permitir faturamento todos os dias (exceto feriados) até as 20:00
        config = create_everyday_no_holidays_config(db, deadline_hour=20, deadline_minute=0)
    """
    # Desativar configurações existentes
    db.query(BillingConfiguration).update({"is_active": False})
    
    config = BillingConfiguration(
        rule_type=BillingRuleType.ALL_DAYS_NO_HOLIDAYS,
        billing_deadline_time=time(deadline_hour, deadline_minute, 0),
        is_active=True
    )
    
    db.add(config)
    db.commit()
    db.refresh(config)
    
    return config


def create_always_available_config(db: Session) -> BillingConfiguration:
    """
    Cria configuração para faturamento 24/7 (sempre disponível).
    
    Args:
        db: Sessão do banco de dados
        
    Returns:
        Configuração criada
        
    Exemplo:
        # Permitir faturamento a qualquer momento
        config = create_always_available_config(db)
    """
    # Desativar configurações existentes
    db.query(BillingConfiguration).update({"is_active": False})
    
    config = BillingConfiguration(
        rule_type=BillingRuleType.ALWAYS,
        billing_deadline_time=None,  # Sem horário limite
        is_active=True
    )
    
    db.add(config)
    db.commit()
    db.refresh(config)
    
    return config


def get_active_config(db: Session) -> BillingConfiguration:
    """
    Retorna a configuração de faturamento ativa no momento.
    
    Args:
        db: Sessão do banco de dados
        
    Returns:
        Configuração ativa, ou None se não houver nenhuma
        
    Raises:
        ValueError: Se não houver configuração ativa
    """
    config = db.query(BillingConfiguration).filter(
        BillingConfiguration.is_active == True
    ).first()
    
    if not config:
        raise ValueError("Nenhuma configuração de faturamento ativa encontrada")
    
    return config


def switch_to_config(db: Session, config_id: int) -> BillingConfiguration:
    """
    Alterna para uma configuração específica, desativando as demais.
    
    Args:
        db: Sessão do banco de dados
        config_id: ID da configuração a ser ativada
        
    Returns:
        Configuração ativada
        
    Raises:
        ValueError: Se a configuração não existir
    """
    config = db.query(BillingConfiguration).filter(
        BillingConfiguration.id == config_id
    ).first()
    
    if not config:
        raise ValueError(f"Configuração com ID {config_id} não encontrada")
    
    # Desativar todas as configurações
    db.query(BillingConfiguration).update({"is_active": False})
    
    # Ativar a configuração selecionada
    config.is_active = True
    
    db.commit()
    db.refresh(config)
    
    return config


# Exemplos de uso em código:
"""
from app.database import get_db
from app.utils.billing_config_examples import create_weekdays_config, create_always_available_config
from algorithm.injection.due_date_calculator import validate_billing_date, is_billing_allowed

# 1. Criar configuração de dias úteis (segunda a sexta até 18:00)
db = next(get_db())
config = create_weekdays_config(db, deadline_hour=18, deadline_minute=0)
print(f"Configuração criada: {config.rule_type.value}")

# 2. Validar uma data de faturamento
from datetime import datetime
promised_date = datetime(2026, 1, 29, 17, 30)  # Quarta-feira 17:30
is_valid, error_msg, next_valid = validate_billing_date(promised_date, db)
if is_valid:
    print("Data de faturamento válida!")
else:
    print(f"Data inválida: {error_msg}")
    if next_valid:
        print(f"Próxima data válida: {next_valid}")

# 3. Verificar se faturamento é permitido agora
from datetime import datetime
from app.models.holiday import Holiday

now = datetime.now()
holidays = [h.date for h in db.query(Holiday).all()]
if is_billing_allowed(now, config, holidays):
    print("Faturamento permitido agora!")
else:
    print("Faturamento não permitido neste momento")

# 4. Alternar para configuração 24/7
always_config = create_always_available_config(db)
print("Sistema agora permite faturamento 24/7")
"""

