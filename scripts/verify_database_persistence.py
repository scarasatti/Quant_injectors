"""
Script para verificar a persistência no banco de dados.

Executa query e mostra os dados salvos para análise.
"""

import sys
from pathlib import Path

# Adicionar raiz do projeto ao path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.database import get_db
from app.models.production_schedule_run import ProductionScheduleRun
from app.models.production_schedule_result import ProductionScheduleResult
from sqlalchemy import text


def verify_persistence(run_id: int = None):
    """
    Verifica a persistência dos dados no banco.
    
    Args:
        run_id: ID do run (se None, usa o mais recente)
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
            print(f"🔍 Usando run mais recente: {run_id}")
            print(f"   Criado em: {latest_run.created_at}")
            print()
        
        # ========== QUERY SQL ==========
        query = text("""
            SELECT 
                production_line_id,
                machine_id,
                sequence_pos,
                job_index_solver,
                product_name,
                mold_name,
                client_name,
                order_index
            FROM production_schedule_result
            WHERE run_id = :run_id
            ORDER BY production_line_id, machine_id, sequence_pos
        """)
        
        results = db.execute(query, {"run_id": run_id}).fetchall()
        
        if not results:
            print(f"❌ Nenhum resultado encontrado para run_id={run_id}")
            return
        
        print(f"✅ Total de registros: {len(results)}")
        print()
        
        # ========== MOSTRAR 10 PRIMEIRAS LINHAS ==========
        print("=" * 150)
        print("10 PRIMEIRAS LINHAS (ordenadas por production_line_id, machine_id, sequence_pos)")
        print("=" * 150)
        print()
        
        header = f"{'#':<5} {'PL_ID':<7} {'Mach_ID':<9} {'Seq_Pos':<9} {'Job_Idx':<9} {'Order':<7} {'Produto':<30} {'Molde':<15} {'Cliente':<20}"
        print(header)
        print("-" * 150)
        
        for idx, row in enumerate(results[:10], 1):
            pl_id, mach_id, seq_pos, job_idx, prod, mold, client, order = row
            
            # Truncar strings longas
            prod_str = (prod or "-")[:30]
            mold_str = (mold or "-")[:15]
            client_str = (client or "-")[:20]
            
            print(f"{idx:<5} {pl_id or '-':<7} {mach_id or '-':<9} {seq_pos if seq_pos is not None else '-':<9} {job_idx or '-':<9} {order or '-':<7} {prod_str:<30} {mold_str:<15} {client_str:<20}")
        
        print("-" * 150)
        print()
        
        # ========== ANÁLISE DE PROBLEMAS ==========
        print("=" * 150)
        print("ANÁLISE DE PROBLEMAS")
        print("=" * 150)
        print()
        
        # Verificar job_index_solver = 0 (dummy)
        dummy_count = sum(1 for row in results if row[3] == 0)  # job_index_solver
        
        if dummy_count > 0:
            print(f"❌ PROBLEMA 1: Encontrados {dummy_count} registros com job_index_solver = 0 (DUMMY)")
            print(f"   DUMMY NÃO DEVE SER SALVO NO BANCO!")
            print()
        else:
            print(f"✅ OK: Nenhum dummy (job_index_solver=0) encontrado")
            print()
        
        # Verificar tipos de dados
        print("Verificando tipos de dados...")
        first_row = results[0]
        pl_id_type = type(first_row[0]).__name__
        mach_id_type = type(first_row[1]).__name__
        seq_pos_type = type(first_row[2]).__name__
        
        print(f"  production_line_id: {pl_id_type}")
        print(f"  machine_id: {mach_id_type}")
        print(f"  sequence_pos: {seq_pos_type}")
        print()
        
        if pl_id_type == 'int' and mach_id_type == 'int':
            print("✅ OK: production_line_id e machine_id são inteiros")
        else:
            print(f"❌ PROBLEMA 2: Tipos incorretos! Esperado: int, Recebido: {pl_id_type}, {mach_id_type}")
        print()
        
        # Verificar sequence_pos para primeira máquina
        first_machine_jobs = [
            row for row in results 
            if row[0] == results[0][0] and row[1] == results[0][1]  # Mesma linha e máquina do primeiro job
        ]
        
        if first_machine_jobs:
            print(f"Verificando sequence_pos para Linha {first_machine_jobs[0][0]}, Máquina {first_machine_jobs[0][1]}:")
            seq_positions = [row[2] for row in first_machine_jobs]
            print(f"  Valores: {seq_positions}")
            
            expected = list(range(len(seq_positions)))
            if seq_positions == expected:
                print(f"  ✅ OK: sequence_pos sequencial (0, 1, 2, ...)")
            else:
                print(f"  ❌ PROBLEMA 3: sequence_pos não é sequencial!")
                print(f"  Esperado: {expected}")
                print(f"  Recebido: {seq_positions}")
        print()
        
        # Verificar se existe NULL
        null_counts = {
            "production_line_id": sum(1 for row in results if row[0] is None),
            "machine_id": sum(1 for row in results if row[1] is None),
            "sequence_pos": sum(1 for row in results if row[2] is None),
            "job_index_solver": sum(1 for row in results if row[3] is None),
            "product_name": sum(1 for row in results if row[4] is None),
        }
        
        print("Verificando valores NULL:")
        for field, count in null_counts.items():
            if count > 0:
                print(f"  ⚠️  {field}: {count} NULLs encontrados")
            else:
                print(f"  ✅ {field}: sem NULLs")
        print()
        
        # ========== TODOS OS RESULTADOS ==========
        print("=" * 150)
        print(f"TODOS OS REGISTROS ({len(results)} total)")
        print("=" * 150)
        print()
        
        print(header)
        print("-" * 150)
        
        for idx, row in enumerate(results, 1):
            pl_id, mach_id, seq_pos, job_idx, prod, mold, client, order = row
            
            prod_str = (prod or "-")[:30]
            mold_str = (mold or "-")[:15]
            client_str = (client or "-")[:20]
            
            # Destacar problemas
            prefix = "⚠️ " if job_idx == 0 else "   "
            
            print(f"{prefix}{idx:<5} {pl_id or '-':<7} {mach_id or '-':<9} {seq_pos if seq_pos is not None else '-':<9} {job_idx or '-':<9} {order or '-':<7} {prod_str:<30} {mold_str:<15} {client_str:<20}")
        
        print("-" * 150)
        print()
        
        # ========== RESUMO ==========
        print("=" * 150)
        print("RESUMO")
        print("=" * 150)
        print()
        
        linhas = set(row[0] for row in results if row[0] is not None)
        print(f"Linhas de produção encontradas: {sorted(linhas)}")
        
        for linha in sorted(linhas):
            maquinas = set(row[1] for row in results if row[0] == linha and row[1] is not None)
            print(f"  Linha {linha}: {len(maquinas)} máquinas - {sorted(maquinas)}")
            
            for maquina in sorted(maquinas):
                jobs_nesta_maquina = [row for row in results if row[0] == linha and row[1] == maquina]
                print(f"    Máquina {maquina}: {len(jobs_nesta_maquina)} jobs")
        
        print()
        print("=" * 150)
        
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Verificar persistência no banco de dados")
    parser.add_argument("--run-id", type=int, help="ID do run (se não especificado, usa o mais recente)")
    
    args = parser.parse_args()
    
    print("\n")
    print("╔" + "═" * 148 + "╗")
    print("║" + "VERIFICAÇÃO DE PERSISTÊNCIA NO BANCO DE DADOS".center(148) + "║")
    print("╚" + "═" * 148 + "╝")
    print()
    
    verify_persistence(args.run_id)
    
    print("\n" + "="*150)
    print("✅ Verificação concluída")
    print("="*150 + "\n")



