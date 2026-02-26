from pydantic import BaseModel, Field, field_validator
from datetime import time
from typing import Optional
from app.models.billing_configuration import BillingRuleType


class BillingConfigurationBase(BaseModel):
    """Schema base para configuração de faturamento"""
    rule_type: BillingRuleType = Field(
        ..., 
        description="Tipo de regra de faturamento"
    )
    billing_deadline_time: Optional[time] = Field(
        None,
        description="Horário limite para faturamento (HH:MM:SS). Obrigatório exceto para regra ALWAYS"
    )

    @field_validator('billing_deadline_time')
    @classmethod
    def validate_deadline_time(cls, v, info):
        """
        Valida o horário limite baseado no tipo de regra:
        - Se rule_type = ALWAYS, billing_deadline_time deve ser None
        - Para outros tipos, billing_deadline_time é obrigatório
        """
        rule_type = info.data.get('rule_type')
        
        if rule_type == BillingRuleType.ALWAYS:
            if v is not None:
                raise ValueError(
                    "Horário limite não deve ser informado quando a regra é '24/7 (sempre disponível)'"
                )
        else:
            if v is None:
                raise ValueError(
                    "Horário limite é obrigatório para este tipo de regra"
                )
        
        return v


class BillingConfigurationCreate(BillingConfigurationBase):
    """Schema para criação de configuração de faturamento"""
    pass


class BillingConfigurationUpdate(BaseModel):
    """Schema para atualização de configuração de faturamento"""
    rule_type: Optional[BillingRuleType] = Field(
        None,
        description="Tipo de regra de faturamento"
    )
    billing_deadline_time: Optional[time] = Field(
        None,
        description="Horário limite para faturamento (HH:MM:SS)"
    )

    @field_validator('billing_deadline_time')
    @classmethod
    def validate_deadline_time(cls, v, info):
        """Valida o horário limite ao atualizar"""
        rule_type = info.data.get('rule_type')
        
        # Se rule_type não foi fornecido, não podemos validar completamente aqui
        # A validação completa será feita na rota
        if rule_type == BillingRuleType.ALWAYS and v is not None:
            raise ValueError(
                "Horário limite não deve ser informado quando a regra é '24/7 (sempre disponível)'"
            )
        
        return v


class BillingConfigurationResponse(BillingConfigurationBase):
    """Schema de resposta para configuração de faturamento"""
    id: int
    is_active: bool

    class Config:
        from_attributes = True

