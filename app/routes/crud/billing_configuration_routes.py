from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.billing_configuration import BillingConfiguration, BillingRuleType
from app.schemas.billing_configuration_schema import (
    BillingConfigurationCreate,
    BillingConfigurationUpdate,
    BillingConfigurationResponse
)

router = APIRouter(
    prefix="/billing-configuration",
    tags=["Billing Configuration"]
)


@router.get("/", response_model=List[BillingConfigurationResponse])
def list_billing_configurations(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Lista todas as configurações de faturamento.
    Normalmente deve existir apenas uma configuração ativa.
    """
    configurations = db.query(BillingConfiguration).offset(skip).limit(limit).all()
    return configurations


@router.get("/active", response_model=BillingConfigurationResponse)
def get_active_billing_configuration(db: Session = Depends(get_db)):
    """
    Retorna a configuração de faturamento ativa.
    Esta é a configuração que está sendo usada atualmente pelo sistema.
    """
    active_config = db.query(BillingConfiguration).filter(
        BillingConfiguration.is_active == True
    ).first()
    
    if not active_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhuma configuração de faturamento ativa encontrada"
        )
    
    return active_config


@router.get("/{config_id}", response_model=BillingConfigurationResponse)
def get_billing_configuration(
    config_id: int,
    db: Session = Depends(get_db)
):
    """Retorna uma configuração específica por ID"""
    config = db.query(BillingConfiguration).filter(
        BillingConfiguration.id == config_id
    ).first()
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuração com ID {config_id} não encontrada"
        )
    
    return config


@router.post("/", response_model=BillingConfigurationResponse, status_code=status.HTTP_201_CREATED)
def create_billing_configuration(
    config: BillingConfigurationCreate,
    db: Session = Depends(get_db)
):
    """
    Cria uma nova configuração de faturamento.
    Automaticamente desativa todas as outras configurações e ativa a nova.
    """
    # Desativar todas as configurações existentes
    db.query(BillingConfiguration).update({"is_active": False})
    
    # Criar nova configuração
    db_config = BillingConfiguration(
        rule_type=config.rule_type,
        billing_deadline_time=config.billing_deadline_time,
        is_active=True
    )
    
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    
    return db_config


@router.put("/{config_id}", response_model=BillingConfigurationResponse)
def update_billing_configuration(
    config_id: int,
    config: BillingConfigurationUpdate,
    db: Session = Depends(get_db)
):
    """
    Atualiza uma configuração de faturamento existente.
    """
    db_config = db.query(BillingConfiguration).filter(
        BillingConfiguration.id == config_id
    ).first()
    
    if not db_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuração com ID {config_id} não encontrada"
        )
    
    # Atualizar campos fornecidos
    update_data = config.model_dump(exclude_unset=True)
    
    # Validação adicional: se está mudando rule_type para ALWAYS, remover billing_deadline_time
    if "rule_type" in update_data:
        if update_data["rule_type"] == BillingRuleType.ALWAYS:
            db_config.billing_deadline_time = None
        elif "billing_deadline_time" not in update_data and db_config.billing_deadline_time is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Horário limite é obrigatório para este tipo de regra"
            )
    
    # Se está mudando de ALWAYS para outro tipo, validar que billing_deadline_time foi fornecido
    if db_config.rule_type == BillingRuleType.ALWAYS:
        if "rule_type" in update_data and update_data["rule_type"] != BillingRuleType.ALWAYS:
            if "billing_deadline_time" not in update_data or update_data["billing_deadline_time"] is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Ao mudar de '24/7' para outro tipo, é necessário fornecer um horário limite"
                )
    
    for key, value in update_data.items():
        setattr(db_config, key, value)
    
    db.commit()
    db.refresh(db_config)
    
    return db_config


@router.put("/{config_id}/activate", response_model=BillingConfigurationResponse)
def activate_billing_configuration(
    config_id: int,
    db: Session = Depends(get_db)
):
    """
    Ativa uma configuração específica e desativa todas as outras.
    Útil para alternar entre diferentes configurações pré-definidas.
    """
    db_config = db.query(BillingConfiguration).filter(
        BillingConfiguration.id == config_id
    ).first()
    
    if not db_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuração com ID {config_id} não encontrada"
        )
    
    # Desativar todas as configurações
    db.query(BillingConfiguration).update({"is_active": False})
    
    # Ativar a configuração selecionada
    db_config.is_active = True
    
    db.commit()
    db.refresh(db_config)
    
    return db_config


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_billing_configuration(
    config_id: int,
    db: Session = Depends(get_db)
):
    """
    Deleta uma configuração de faturamento.
    Atenção: Se deletar a configuração ativa, nenhuma outra será ativada automaticamente.
    """
    db_config = db.query(BillingConfiguration).filter(
        BillingConfiguration.id == config_id
    ).first()
    
    if not db_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuração com ID {config_id} não encontrada"
        )
    
    # Avisar se está deletando a configuração ativa
    if db_config.is_active:
        # Não vamos impedir a deleção, mas em produção você pode querer adicionar validação
        pass
    
    db.delete(db_config)
    db.commit()
    
    return None

