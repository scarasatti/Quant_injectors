"""
Script para validar a persistência correta dos jobs no banco de dados.
Verifica se todos os jobs do tipo Excel têm product_name, mold_name e dados completos.

Uso:
    python scripts/validate_job_persistence.py [run_id]
    
Se run_id não for fornecido, valida o último run_id disponível.
"""

import sys
from pathlib import Path

# Adicionar o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models.production_schedule_run import ProductionScheduleRun
from app.models.production_schedule_result import ProductionScheduleResult


def validate_job_persistence(run_id: int = None):
    """
    Valida a persistência de jobs para um run_id específico ou o último disponível.
    """
    db = SessionLocal()
    
    try:
        # Se run_id não for fornecido, buscar o último
        if run_id is None:
            last_run = db.query(ProductionScheduleRun).order_by(ProductionScheduleRun.id.desc()).first()
            if not last_run:
                print("❌ Nenhum run encontrado no banco de dados")
                return False
            run_id = last_run.id
            print(f"ℹ️  Usando último run_id: {run_id}")
        else:
            # Verificar se o run_id existe
            run = db.query(ProductionScheduleRun).filter_by(id=run_id).first()
            if not run:
                print(f"❌ Run ID {run_id} não encontrado no banco de dados")
                return False
        
        # Buscar todos os resultados deste run
        results = db.query(ProductionScheduleResult).filter_by(run_id=run_id).order_by(
            ProductionScheduleResult.order_index
        ).all()
        
        if not results:
            print(f"❌ Nenhum resultado encontrado para run_id={run_id}")
            return False
        
        print(f"\n{'='*80}")
        print(f"VALIDAÇÃO DE PERSISTÊNCIA - Run ID: {run_id}")
        print(f"{'='*80}\n")
        print(f"Total de jobs encontrados: {len(results)}")
        
        # Contadores
        total_jobs = len(results)
        jobs_with_errors = 0
        jobs_ok = 0
        
        errors = []
        
        # Validar cada job
        for idx, result in enumerate(results, 1):
            job_errors = []
            
            # Validações obrigatórias
            if not result.product_name or result.product_name == "N/A":
                job_errors.append("product_name vazio ou N/A")
            
            if not result.mold_name or result.mold_name == "N/A":
                job_errors.append("mold_name vazio ou N/A")
            
            if not result.client_name or result.client_name == "Cliente Desconhecido":
                job_errors.append("client_name vazio ou genérico")
            
            if not result.quantity or result.quantity <= 0:
                job_errors.append("quantity <= 0")
            
            if not result.machine_name or result.machine_name == "N/A":
                job_errors.append("machine_name vazio ou N/A")
            
            # Se houver erros, registrar
            if job_errors:
                jobs_with_errors += 1
                error_msg = (
                    f"❌ Job #{idx} (order_index={result.order_index}, job_id={result.job_id}): "
                    f"{', '.join(job_errors)}"
                )
                errors.append(error_msg)
                print(error_msg)
                print(f"   Dados: product={result.product_name}, mold={result.mold_name}, "
                      f"client={result.client_name}, quantity={result.quantity}, machine={result.machine_name}")
            else:
                jobs_ok += 1
                print(f"✅ Job #{idx} (order_index={result.order_index}): {result.client_name} - "
                      f"{result.product_name} ({result.mold_name}) - {result.quantity} unidades")
        
        # Resumo
        print(f"\n{'='*80}")
        print("RESUMO DA VALIDAÇÃO")
        print(f"{'='*80}")
        print(f"Total de jobs: {total_jobs}")
        print(f"Jobs válidos: {jobs_ok} ({jobs_ok/total_jobs*100:.1f}%)")
        print(f"Jobs com erros: {jobs_with_errors} ({jobs_with_errors/total_jobs*100:.1f}%)")
        
        if jobs_with_errors == 0:
            print(f"\n✅ VALIDAÇÃO PASSOU! Todos os jobs estão com dados completos.")
            return True
        else:
            print(f"\n❌ VALIDAÇÃO FALHOU! {jobs_with_errors} jobs com dados incompletos.")
            print(f"\nErros encontrados:")
            for error in errors:
                print(f"  {error}")
            return False
            
    finally:
        db.close()


if __name__ == "__main__":
    # Verificar se foi fornecido um run_id como argumento
    run_id = None
    if len(sys.argv) > 1:
        try:
            run_id = int(sys.argv[1])
            print(f"Validando run_id: {run_id}")
        except ValueError:
            print(f"❌ Argumento inválido: '{sys.argv[1]}' não é um número inteiro")
            sys.exit(1)
    
    # Executar validação
    success = validate_job_persistence(run_id)
    
    # Retornar código de saída apropriado
    sys.exit(0 if success else 1)

