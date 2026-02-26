"""
Teste: Verificar se a ordem do log respeita a sequência do solver

SEQUÊNCIA DO SOLVER (linha 1, máquina 1): [6, 8, 2, 3, 5, 0]
ESPERADO NO LOG:
  Ordem 1: Job 6
  Ordem 2: Job 8
  Ordem 3: Job 2
  Ordem 4: Job 3
  Ordem 5: Job 5
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.database import get_db
from app.models.production_schedule_run import ProductionScheduleRun
from app.models.production_schedule_result import ProductionScheduleResult


def test_sequence_order(run_id: int = None):
    """
    Testa se a ordem no BD respeita a sequência do solver.
    """
    db = next(get_db())
    
    try:
        # Se não especificou run_id, buscar o mais recente
        if run_id is None:
            latest_run = db.query(ProductionScheduleRun).order_by(
                ProductionScheduleRun.created_at.desc()
            ).first()
            
            if not latest_run:
                print("Nenhum run encontrado no banco de dados")
                return
            
            run_id = latest_run.id
        
        print("\n")
        print("=" * 100)
        print(f"TESTE DE ORDEM - RUN ID: {run_id}")
        print("=" * 100)
        print()
        
        # Buscar resultados com ordenação correta
        results = db.query(ProductionScheduleResult).filter(
            ProductionScheduleResult.run_id == run_id
        ).order_by(
            ProductionScheduleResult.production_line_id.asc(),
            ProductionScheduleResult.machine_id.asc(),
            ProductionScheduleResult.sequence_pos.asc()
        ).all()
        
        if not results:
            print(f"Nenhum resultado para run_id={run_id}")
            return
        
        print("ORDEM NO BANCO DE DADOS (após ORDER BY production_line_id, machine_id, sequence_pos):")
        print()
        print(f"{'#':<5} {'PL':<5} {'Maq':<5} {'Seq':<5} {'Job_Solver':<12} {'Produto':<40}")
        print("-" * 100)
        
        for idx, result in enumerate(results, start=1):
            job_solver = result.job_index_solver if result.job_index_solver is not None else "NULL"
            product = (result.product_name or "-")[:40]
            pl_id = result.production_line_id if result.production_line_id is not None else "NULL"
            maq_id = result.machine_id if result.machine_id is not None else "NULL"
            seq_pos = result.sequence_pos if result.sequence_pos is not None else "NULL"
            
            print(f"{idx:<5} {pl_id:<5} {maq_id:<5} {seq_pos:<5} {job_solver:<12} {product:<40}")
        
        print("-" * 100)
        print()
        
        # Análise por máquina
        print("ANÁLISE POR MÁQUINA:")
        print()
        
        from collections import defaultdict
        by_machine = defaultdict(list)
        
        for result in results:
            if result.production_line_id is not None and result.machine_id is not None:
                key = (result.production_line_id, result.machine_id)
                by_machine[key].append(result.job_index_solver)
        
        for (pl_id, maq_id), job_sequence in sorted(by_machine.items()):
            print(f"  Linha {pl_id}, Máquina {maq_id}: {job_sequence}")
        
        print()
        print("=" * 100)
        print()
        
        # Verificar se job 6 está primeiro na linha 1, máquina 1
        linha1_maq1 = by_machine.get((1, 1), [])
        if linha1_maq1 and linha1_maq1[0] == 6:
            print("✅ CORRETO: Job 6 é o PRIMEIRO na Linha 1, Máquina 1")
        elif linha1_maq1:
            print(f"❌ ERRADO: Job {linha1_maq1[0]} é o primeiro, deveria ser Job 6")
        else:
            print("⚠️  Nenhum dado para Linha 1, Máquina 1")
        
        print()
        
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Testar ordem de sequência")
    parser.add_argument("--run-id", type=int, help="ID do run")
    
    args = parser.parse_args()
    
    test_sequence_order(args.run_id)


