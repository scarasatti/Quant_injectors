"""
Teste: Query após migração

Verifica se a query funciona corretamente após adicionar machine_id e sequence_pos.
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.database import get_db
from app.models.production_schedule_run import ProductionScheduleRun
from sqlalchemy import text


def test_query(run_id: int = None):
    """
    Testa a query de ordenação.
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
            print(f"Usando run mais recente: {run_id}")
            print()
        
        # QUERY DE TESTE
        print("=" * 120)
        print("EXECUTANDO QUERY DE TESTE")
        print("=" * 120)
        print()
        print("SELECT production_line_id, machine_id, sequence_pos, job_index_solver, product_name")
        print("FROM production_schedule_result")
        print(f"WHERE run_id = {run_id}")
        print("ORDER BY production_line_id, machine_id, sequence_pos;")
        print()
        
        query = text("""
            SELECT 
                production_line_id,
                machine_id,
                sequence_pos,
                job_index_solver,
                product_name
            FROM production_schedule_result
            WHERE run_id = :run_id
            ORDER BY production_line_id, machine_id, sequence_pos
        """)
        
        results = db.execute(query, {"run_id": run_id}).fetchall()
        
        if not results:
            print(f"Nenhum resultado para run_id={run_id}")
            print()
            print("AVISO: Execute um novo solve para popular os dados com machine_id e sequence_pos")
            return
        
        print("=" * 120)
        print(f"RESULTADOS ({len(results)} registros)")
        print("=" * 120)
        print()
        
        # Cabeçalho
        header = f"{'#':<5} {'PL_ID':<10} {'Mach_ID':<10} {'Seq_Pos':<10} {'Job_Idx':<10} {'Produto':<60}"
        print(header)
        print("-" * 120)
        
        # Mostrar primeiras 10 linhas
        for idx, row in enumerate(results[:10], 1):
            pl_id, mach_id, seq_pos, job_idx, product = row
            product_str = (product or "-")[:60]
            
            # Destacar problemas
            warning = ""
            if job_idx == 0:
                warning = " <-- ERRO: DUMMY NAO DEVE ESTAR AQUI!"
            if mach_id is None or seq_pos is None:
                warning = " <-- AVISO: NULL (dados antigos)"
            
            print(f"{idx:<5} {pl_id or '-':<10} {mach_id or 'NULL':<10} {seq_pos if seq_pos is not None else 'NULL':<10} {job_idx or '-':<10} {product_str:<60}{warning}")
        
        if len(results) > 10:
            print(f"... e mais {len(results) - 10} registros")
        
        print("-" * 120)
        print()
        
        # ANÁLISE
        print("=" * 120)
        print("ANALISE")
        print("=" * 120)
        print()
        
        # Verificar dummy
        dummy_count = sum(1 for row in results if row[3] == 0)
        if dummy_count > 0:
            print(f"ERRO: {dummy_count} registros com job_index_solver=0 (dummy)")
            print("      Dummy NAO deve ser salvo!")
        else:
            print("OK: Nenhum dummy encontrado")
        print()
        
        # Verificar NULLs
        null_machine = sum(1 for row in results if row[1] is None)
        null_seq = sum(1 for row in results if row[2] is None)
        
        if null_machine > 0 or null_seq > 0:
            print(f"AVISO: {null_machine} registros com machine_id NULL")
            print(f"       {null_seq} registros com sequence_pos NULL")
            print("       Estes sao dados antigos (antes da migracao)")
            print("       Execute um novo solve para popular os campos")
        else:
            print("OK: Todos os registros tem machine_id e sequence_pos")
        print()
        
        # Verificar ordenação
        print("Verificando ordenacao por maquina...")
        from collections import defaultdict
        by_machine = defaultdict(list)
        
        for row in results:
            pl_id, mach_id, seq_pos, job_idx, product = row
            if mach_id is not None and seq_pos is not None:
                key = (pl_id, mach_id)
                by_machine[key].append(seq_pos)
        
        all_ok = True
        for (pl_id, mach_id), seq_positions in sorted(by_machine.items()):
            expected = list(range(len(seq_positions)))
            if seq_positions != expected:
                print(f"  ERRO: Linha {pl_id}, Maquina {mach_id}")
                print(f"        Esperado: {expected}")
                print(f"        Recebido: {seq_positions}")
                all_ok = False
        
        if all_ok and by_machine:
            print("  OK: sequence_pos esta correto para todas as maquinas")
        elif not by_machine:
            print("  SKIP: Nenhum dado com machine_id/sequence_pos para verificar")
        print()
        
        print("=" * 120)
        
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Testar query apos migracao")
    parser.add_argument("--run-id", type=int, help="ID do run")
    
    args = parser.parse_args()
    
    print("\n")
    print("=" * 120)
    print("TESTE: Query apos migracao".center(120))
    print("=" * 120)
    print()
    
    test_query(args.run_id)
    
    print("=" * 120)
    print("Teste concluido")
    print("=" * 120)
    print()



