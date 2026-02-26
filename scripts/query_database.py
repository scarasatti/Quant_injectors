"""
PROVA NO BANCO DE DADOS

Executa a query solicitada para verificar os dados persistidos.
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.database import get_db
from app.models.production_schedule_run import ProductionScheduleRun
from sqlalchemy import text


def run_query(run_id: int = None):
    """
    Executa a query para verificar dados no banco.
    """
    db = next(get_db())
    
    try:
        # Se não especificou run_id, buscar o mais recente
        if run_id is None:
            latest_run = db.query(ProductionScheduleRun).order_by(
                ProductionScheduleRun.created_at.desc()
            ).first()
            
            if not latest_run:
                print("❌ Nenhum run encontrado no banco de dados")
                return
            
            run_id = latest_run.id
            print(f"\n📌 Usando run mais recente: {run_id} (criado em {latest_run.created_at})\n")
        
        # ========== EXECUTAR QUERY ==========
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
            print(f"❌ Nenhum resultado encontrado para run_id={run_id}")
            return
        
        print("=" * 120)
        print(f"QUERY EXECUTADA (run_id = {run_id})")
        print("=" * 120)
        print()
        print("SELECT production_line_id, machine_id, sequence_pos, job_index_solver, product_name")
        print("FROM production_schedule_result")
        print(f"WHERE run_id = {run_id}")
        print("ORDER BY production_line_id, machine_id, sequence_pos;")
        print()
        print("=" * 120)
        print(f"PRIMEIRAS 10 LINHAS")
        print("=" * 120)
        print()
        
        # Cabeçalho
        header = f"{'#':<5} {'PL_ID':<10} {'Mach_ID':<10} {'Seq_Pos':<10} {'Job_Idx':<10} {'Produto':<60}"
        print(header)
        print("-" * 120)
        
        # Mostrar 10 primeiras linhas
        for idx, row in enumerate(results[:10], 1):
            pl_id, mach_id, seq_pos, job_idx, product = row
            product_str = (product or "-")[:60]
            print(f"{idx:<5} {pl_id or '-':<10} {mach_id or '-':<10} {seq_pos if seq_pos is not None else '-':<10} {job_idx or '-':<10} {product_str:<60}")
        
        print("-" * 120)
        print()
        
        # ========== CONFIRMAÇÕES ==========
        print("=" * 120)
        print("CONFIRMAÇÕES OBRIGATÓRIAS")
        print("=" * 120)
        print()
        
        # 1. Existe job_index_solver = 0 (dummy)?
        dummy_count = sum(1 for row in results if row[3] == 0)
        print(f"1) Existe job_index_solver = 0 salvo? {'❌ SIM (ERRO!)' if dummy_count > 0 else '✅ NÃO'}")
        if dummy_count > 0:
            print(f"   Total de dummies salvos: {dummy_count}")
            print(f"   🚨 PROBLEMA: Dummy NÃO deve ser salvo no banco!")
        print()
        
        # 2. Verificar sequence_pos da primeira máquina
        if results:
            first_pl = results[0][0]
            first_mach = results[0][1]
            first_job_idx = results[0][3]
            first_seq_pos = results[0][2]
            
            print(f"2) Para production_line_id={first_pl} e machine_id={first_mach}:")
            print(f"   sequence_pos=0 tem job_index_solver={first_job_idx}")
            
            # Buscar todos os jobs dessa linha/máquina
            same_machine = [row for row in results if row[0] == first_pl and row[1] == first_mach]
            print(f"   Total de jobs nessa máquina: {len(same_machine)}")
            print(f"   Sequence_pos values: {[row[2] for row in same_machine]}")
            
            # Verificar se sequence_pos está correto
            seq_positions = [row[2] for row in same_machine]
            expected = list(range(len(same_machine)))
            
            if seq_positions == expected:
                print(f"   ✅ sequence_pos está CORRETO (0, 1, 2, ..., {len(same_machine)-1})")
            else:
                print(f"   ❌ sequence_pos está ERRADO!")
                print(f"   Esperado: {expected}")
                print(f"   Recebido: {seq_positions}")
                print(f"   🚨 PROBLEMA: sequence_pos deve ser 0-indexed sem contar dummy!")
        print()
        
        # 3. Verificar tipos
        if results:
            first_row = results[0]
            pl_type = type(first_row[0]).__name__
            mach_type = type(first_row[1]).__name__
            
            print(f"3) Tipos de dados:")
            print(f"   production_line_id: {pl_type}")
            print(f"   machine_id: {mach_type}")
            
            if pl_type == 'int' and mach_type == 'int':
                print(f"   ✅ Tipos estão corretos (int)")
            else:
                print(f"   ❌ Tipos incorretos! Esperado: int")
        print()
        
        # 4. Mostrar todos os job_index_solver
        print(f"4) Todos os job_index_solver salvos:")
        job_indices = [row[3] for row in results]
        print(f"   {job_indices}")
        print()
        
        # ========== RESUMO ==========
        print("=" * 120)
        print("RESUMO")
        print("=" * 120)
        print()
        
        # Agrupar por linha e máquina
        from collections import defaultdict
        by_line_machine = defaultdict(list)
        
        for row in results:
            pl_id, mach_id, seq_pos, job_idx, product = row
            key = (pl_id, mach_id)
            by_line_machine[key].append((seq_pos, job_idx, product))
        
        for (pl_id, mach_id), jobs in sorted(by_line_machine.items()):
            print(f"Linha {pl_id}, Máquina {mach_id}: {len(jobs)} jobs")
            for seq_pos, job_idx, product in jobs[:5]:  # Mostrar 5 primeiros
                product_short = (product or "-")[:40]
                print(f"  seq_pos={seq_pos}, job_idx={job_idx}, produto={product_short}")
            if len(jobs) > 5:
                print(f"  ... e mais {len(jobs) - 5} jobs")
            print()
        
        print("=" * 120)
        
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Executar query de verificação no banco")
    parser.add_argument("--run-id", type=int, help="ID do run (se não especificado, usa o mais recente)")
    
    args = parser.parse_args()
    
    print("\n")
    print("╔" + "═" * 118 + "╗")
    print("║" + "PROVA NO BANCO DE DADOS".center(118) + "║")
    print("╚" + "═" * 118 + "╝")
    
    run_query(args.run_id)
    
    print("\n✅ Query executada com sucesso!\n")



