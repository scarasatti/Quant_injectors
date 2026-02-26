"""
Script para inicializar a configuração de faturamento no banco de dados.

Este script pode ser executado para criar uma configuração padrão de faturamento.
"""

import sys
from pathlib import Path

# Adicionar o diretório raiz ao path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from datetime import time
from app.database import SessionLocal
from app.models.billing_configuration import BillingConfiguration, BillingRuleType


def init_default_billing_config():
    """
    Cria uma configuração padrão de faturamento se não existir nenhuma.
    
    Configuração padrão:
    - Segunda a Sexta (sem feriados)
    - Horário limite: 18:00
    """
    db = SessionLocal()
    
    try:
        # Verificar se já existe alguma configuração
        existing_config = db.query(BillingConfiguration).first()
        
        if existing_config:
            print("⚠️  Já existe uma configuração de faturamento no banco de dados.")
            print(f"   Configuração ativa: {existing_config.rule_type.value}")
            if existing_config.billing_deadline_time:
                print(f"   Horário limite: {existing_config.billing_deadline_time.strftime('%H:%M')}")
            
            response = input("\nDeseja criar uma nova configuração padrão mesmo assim? (s/n): ")
            if response.lower() not in ['s', 'sim', 'y', 'yes']:
                print("Operação cancelada.")
                return
        
        # Desativar todas as configurações existentes
        db.query(BillingConfiguration).update({"is_active": False})
        
        # Criar configuração padrão
        default_config = BillingConfiguration(
            rule_type=BillingRuleType.WEEKDAYS_NO_HOLIDAYS,
            billing_deadline_time=time(18, 0, 0),
            is_active=True
        )
        
        db.add(default_config)
        db.commit()
        db.refresh(default_config)
        
        print("\n✅ Configuração padrão de faturamento criada com sucesso!")
        print(f"   Tipo: {default_config.rule_type.value}")
        print(f"   Horário limite: {default_config.billing_deadline_time.strftime('%H:%M')}")
        print(f"   Status: {'Ativa' if default_config.is_active else 'Inativa'}")
        print(f"   ID: {default_config.id}")
        
    except Exception as e:
        print(f"\n❌ Erro ao criar configuração: {str(e)}")
        db.rollback()
    finally:
        db.close()


def create_custom_config():
    """
    Cria uma configuração customizada de forma interativa.
    """
    db = SessionLocal()
    
    try:
        print("\n=== Criar Configuração Customizada de Faturamento ===\n")
        
        # Escolher tipo de regra
        print("Escolha o tipo de regra:")
        print("1. Segunda a Sexta (sem feriados)")
        print("2. Todos os dias (incluindo feriados)")
        print("3. Todos os dias (sem feriados)")
        print("4. 24/7 (sempre disponível)")
        
        choice = input("\nOpção (1-4): ")
        
        rule_type_map = {
            '1': BillingRuleType.WEEKDAYS_NO_HOLIDAYS,
            '2': BillingRuleType.ALL_DAYS_WITH_HOLIDAYS,
            '3': BillingRuleType.ALL_DAYS_NO_HOLIDAYS,
            '4': BillingRuleType.ALWAYS,
        }
        
        if choice not in rule_type_map:
            print("❌ Opção inválida!")
            return
        
        rule_type = rule_type_map[choice]
        
        # Definir horário limite (se necessário)
        billing_deadline = None
        if rule_type != BillingRuleType.ALWAYS:
            print("\nDefina o horário limite para faturamento:")
            hour = int(input("Hora (0-23): "))
            minute = int(input("Minuto (0-59): "))
            
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                print("❌ Horário inválido!")
                return
            
            billing_deadline = time(hour, minute, 0)
        
        # Desativar configurações existentes
        db.query(BillingConfiguration).update({"is_active": False})
        
        # Criar nova configuração
        new_config = BillingConfiguration(
            rule_type=rule_type,
            billing_deadline_time=billing_deadline,
            is_active=True
        )
        
        db.add(new_config)
        db.commit()
        db.refresh(new_config)
        
        print("\n✅ Configuração criada com sucesso!")
        print(f"   Tipo: {new_config.rule_type.value}")
        if new_config.billing_deadline_time:
            print(f"   Horário limite: {new_config.billing_deadline_time.strftime('%H:%M')}")
        else:
            print("   Horário limite: Não aplicável (24/7)")
        print(f"   ID: {new_config.id}")
        
    except ValueError as e:
        print(f"\n❌ Erro: {str(e)}")
        db.rollback()
    except Exception as e:
        print(f"\n❌ Erro ao criar configuração: {str(e)}")
        db.rollback()
    finally:
        db.close()


def list_all_configs():
    """
    Lista todas as configurações de faturamento cadastradas.
    """
    db = SessionLocal()
    
    try:
        configs = db.query(BillingConfiguration).all()
        
        if not configs:
            print("\n⚠️  Nenhuma configuração de faturamento encontrada.")
            return
        
        print("\n=== Configurações de Faturamento ===\n")
        
        for config in configs:
            status = "🟢 ATIVA" if config.is_active else "⚪ Inativa"
            print(f"{status} - ID: {config.id}")
            print(f"  Tipo: {config.rule_type.value}")
            if config.billing_deadline_time:
                print(f"  Horário limite: {config.billing_deadline_time.strftime('%H:%M')}")
            else:
                print("  Horário limite: Não aplicável (24/7)")
            print()
        
    finally:
        db.close()


def main():
    """
    Menu principal do script.
    """
    print("=" * 60)
    print("  INICIALIZAÇÃO DE CONFIGURAÇÃO DE FATURAMENTO")
    print("=" * 60)
    
    while True:
        print("\nEscolha uma opção:")
        print("1. Criar configuração padrão (Segunda a Sexta, até 18:00)")
        print("2. Criar configuração customizada")
        print("3. Listar todas as configurações")
        print("4. Sair")
        
        choice = input("\nOpção: ")
        
        if choice == '1':
            init_default_billing_config()
        elif choice == '2':
            create_custom_config()
        elif choice == '3':
            list_all_configs()
        elif choice == '4':
            print("\nEncerrando...")
            break
        else:
            print("❌ Opção inválida!")


if __name__ == "__main__":
    main()

