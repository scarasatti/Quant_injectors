"""
Testes unitários para o sistema de configuração de faturamento.
"""

import pytest
from datetime import datetime, date, time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models.billing_configuration import BillingConfiguration, BillingRuleType
from app.models.holiday import Holiday
from algorithm.injection.due_date_calculator import (
    is_billing_allowed,
    is_weekday,
    validate_billing_date,
    get_next_billing_allowed_datetime
)


# Configuração do banco de dados de teste
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    """Cria uma sessão de banco de dados para testes."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def holidays_list():
    """Lista de feriados para testes."""
    return [
        date(2026, 1, 1),   # Ano Novo (quinta)
        date(2026, 4, 21),  # Tiradentes (terça)
        date(2026, 12, 25), # Natal (sexta)
    ]


@pytest.fixture
def holidays_in_db(db_session, holidays_list):
    """Adiciona feriados no banco de dados de teste."""
    for holiday_date in holidays_list:
        holiday = Holiday(
            name=f"Feriado {holiday_date}",
            date=holiday_date,
            level="Nacional"
        )
        db_session.add(holiday)
    db_session.commit()
    return holidays_list


class TestIsWeekday:
    """Testes para função is_weekday."""
    
    def test_monday_is_weekday(self):
        """Segunda-feira deve ser dia útil."""
        check_date = date(2026, 1, 26)  # Segunda
        assert is_weekday(check_date) is True
    
    def test_friday_is_weekday(self):
        """Sexta-feira deve ser dia útil."""
        check_date = date(2026, 1, 30)  # Sexta
        assert is_weekday(check_date) is True
    
    def test_saturday_is_not_weekday(self):
        """Sábado não deve ser dia útil."""
        check_date = date(2026, 1, 31)  # Sábado
        assert is_weekday(check_date) is False
    
    def test_sunday_is_not_weekday(self):
        """Domingo não deve ser dia útil."""
        check_date = date(2026, 2, 1)  # Domingo
        assert is_weekday(check_date) is False


class TestWeekdaysNoHolidaysRule:
    """Testes para regra WEEKDAYS_NO_HOLIDAYS."""
    
    @pytest.fixture
    def config(self, db_session):
        """Configuração de dias úteis."""
        config = BillingConfiguration(
            rule_type=BillingRuleType.WEEKDAYS_NO_HOLIDAYS,
            billing_deadline_time=time(18, 0, 0),
            is_active=True
        )
        db_session.add(config)
        db_session.commit()
        return config
    
    def test_weekday_within_hours(self, config, holidays_list):
        """Deve permitir faturamento em dia útil dentro do horário."""
        check_datetime = datetime(2026, 1, 28, 17, 30)  # Quarta 17:30
        assert is_billing_allowed(check_datetime, config, holidays_list) is True
    
    def test_weekday_after_hours(self, config, holidays_list):
        """Não deve permitir faturamento em dia útil após horário."""
        check_datetime = datetime(2026, 1, 28, 18, 30)  # Quarta 18:30
        assert is_billing_allowed(check_datetime, config, holidays_list) is False
    
    def test_saturday_not_allowed(self, config, holidays_list):
        """Não deve permitir faturamento em sábado."""
        check_datetime = datetime(2026, 1, 31, 10, 0)  # Sábado 10:00
        assert is_billing_allowed(check_datetime, config, holidays_list) is False
    
    def test_sunday_not_allowed(self, config, holidays_list):
        """Não deve permitir faturamento em domingo."""
        check_datetime = datetime(2026, 2, 1, 10, 0)  # Domingo 10:00
        assert is_billing_allowed(check_datetime, config, holidays_list) is False
    
    def test_holiday_not_allowed(self, config, holidays_list):
        """Não deve permitir faturamento em feriado."""
        check_datetime = datetime(2026, 1, 1, 10, 0)  # Ano Novo (quinta) 10:00
        assert is_billing_allowed(check_datetime, config, holidays_list) is False


class TestAllDaysWithHolidaysRule:
    """Testes para regra ALL_DAYS_WITH_HOLIDAYS."""
    
    @pytest.fixture
    def config(self, db_session):
        """Configuração de todos os dias com feriados."""
        config = BillingConfiguration(
            rule_type=BillingRuleType.ALL_DAYS_WITH_HOLIDAYS,
            billing_deadline_time=time(23, 59, 0),
            is_active=True
        )
        db_session.add(config)
        db_session.commit()
        return config
    
    def test_weekday_allowed(self, config, holidays_list):
        """Deve permitir faturamento em dia útil."""
        check_datetime = datetime(2026, 1, 28, 20, 0)  # Quarta 20:00
        assert is_billing_allowed(check_datetime, config, holidays_list) is True
    
    def test_saturday_allowed(self, config, holidays_list):
        """Deve permitir faturamento em sábado."""
        check_datetime = datetime(2026, 1, 31, 20, 0)  # Sábado 20:00
        assert is_billing_allowed(check_datetime, config, holidays_list) is True
    
    def test_sunday_allowed(self, config, holidays_list):
        """Deve permitir faturamento em domingo."""
        check_datetime = datetime(2026, 2, 1, 20, 0)  # Domingo 20:00
        assert is_billing_allowed(check_datetime, config, holidays_list) is True
    
    def test_holiday_allowed(self, config, holidays_list):
        """Deve permitir faturamento em feriado."""
        check_datetime = datetime(2026, 1, 1, 20, 0)  # Ano Novo 20:00
        assert is_billing_allowed(check_datetime, config, holidays_list) is True
    
    def test_after_deadline_not_allowed(self, config, holidays_list):
        """Não deve permitir após horário limite."""
        check_datetime = datetime(2026, 1, 28, 23, 59, 30)  # Após 23:59
        assert is_billing_allowed(check_datetime, config, holidays_list) is False


class TestAllDaysNoHolidaysRule:
    """Testes para regra ALL_DAYS_NO_HOLIDAYS."""
    
    @pytest.fixture
    def config(self, db_session):
        """Configuração de todos os dias sem feriados."""
        config = BillingConfiguration(
            rule_type=BillingRuleType.ALL_DAYS_NO_HOLIDAYS,
            billing_deadline_time=time(20, 0, 0),
            is_active=True
        )
        db_session.add(config)
        db_session.commit()
        return config
    
    def test_weekday_allowed(self, config, holidays_list):
        """Deve permitir faturamento em dia útil."""
        check_datetime = datetime(2026, 1, 28, 19, 0)  # Quarta 19:00
        assert is_billing_allowed(check_datetime, config, holidays_list) is True
    
    def test_saturday_allowed(self, config, holidays_list):
        """Deve permitir faturamento em sábado."""
        check_datetime = datetime(2026, 1, 31, 19, 0)  # Sábado 19:00
        assert is_billing_allowed(check_datetime, config, holidays_list) is True
    
    def test_holiday_not_allowed(self, config, holidays_list):
        """Não deve permitir faturamento em feriado."""
        check_datetime = datetime(2026, 1, 1, 15, 0)  # Ano Novo 15:00
        assert is_billing_allowed(check_datetime, config, holidays_list) is False


class TestAlwaysRule:
    """Testes para regra ALWAYS."""
    
    @pytest.fixture
    def config(self, db_session):
        """Configuração 24/7."""
        config = BillingConfiguration(
            rule_type=BillingRuleType.ALWAYS,
            billing_deadline_time=None,
            is_active=True
        )
        db_session.add(config)
        db_session.commit()
        return config
    
    def test_weekday_allowed(self, config, holidays_list):
        """Deve permitir faturamento em qualquer dia útil."""
        check_datetime = datetime(2026, 1, 28, 23, 59)
        assert is_billing_allowed(check_datetime, config, holidays_list) is True
    
    def test_weekend_allowed(self, config, holidays_list):
        """Deve permitir faturamento em fim de semana."""
        check_datetime = datetime(2026, 1, 31, 23, 59)  # Sábado
        assert is_billing_allowed(check_datetime, config, holidays_list) is True
    
    def test_holiday_allowed(self, config, holidays_list):
        """Deve permitir faturamento em feriado."""
        check_datetime = datetime(2026, 1, 1, 23, 59)  # Ano Novo
        assert is_billing_allowed(check_datetime, config, holidays_list) is True
    
    def test_midnight_allowed(self, config, holidays_list):
        """Deve permitir faturamento à meia-noite."""
        check_datetime = datetime(2026, 1, 28, 0, 0)
        assert is_billing_allowed(check_datetime, config, holidays_list) is True


class TestValidateBillingDate:
    """Testes para função validate_billing_date."""
    
    def test_valid_date(self, db_session, holidays_in_db):
        """Deve validar data correta."""
        config = BillingConfiguration(
            rule_type=BillingRuleType.WEEKDAYS_NO_HOLIDAYS,
            billing_deadline_time=time(18, 0, 0),
            is_active=True
        )
        db_session.add(config)
        db_session.commit()
        
        promised_date = datetime(2026, 1, 28, 17, 0)  # Quarta 17:00
        is_valid, error_msg, next_valid = validate_billing_date(promised_date, db_session)
        
        assert is_valid is True
        assert error_msg is None
        assert next_valid is None
    
    def test_invalid_date_returns_error(self, db_session, holidays_in_db):
        """Deve retornar erro para data inválida."""
        config = BillingConfiguration(
            rule_type=BillingRuleType.WEEKDAYS_NO_HOLIDAYS,
            billing_deadline_time=time(18, 0, 0),
            is_active=True
        )
        db_session.add(config)
        db_session.commit()
        
        promised_date = datetime(2026, 1, 31, 10, 0)  # Sábado
        is_valid, error_msg, next_valid = validate_billing_date(promised_date, db_session)
        
        assert is_valid is False
        assert error_msg is not None
        assert next_valid is not None


class TestGetNextBillingAllowedDatetime:
    """Testes para função get_next_billing_allowed_datetime."""
    
    def test_weekdays_rule_finds_next_monday(self, db_session, holidays_list):
        """Deve encontrar próxima segunda-feira."""
        config = BillingConfiguration(
            rule_type=BillingRuleType.WEEKDAYS_NO_HOLIDAYS,
            billing_deadline_time=time(18, 0, 0),
            is_active=True
        )
        db_session.add(config)
        db_session.commit()
        
        # Sábado
        start = datetime(2026, 1, 31, 10, 0)
        next_valid = get_next_billing_allowed_datetime(start, config, holidays_list)
        
        assert next_valid is not None
        assert next_valid.weekday() == 0  # Segunda-feira
    
    def test_always_rule_returns_immediately(self, db_session, holidays_list):
        """Regra ALWAYS deve retornar imediatamente."""
        config = BillingConfiguration(
            rule_type=BillingRuleType.ALWAYS,
            billing_deadline_time=None,
            is_active=True
        )
        db_session.add(config)
        db_session.commit()
        
        start = datetime(2026, 1, 31, 23, 59)
        next_valid = get_next_billing_allowed_datetime(start, config, holidays_list)
        
        assert next_valid == start


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

