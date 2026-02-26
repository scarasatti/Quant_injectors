"""
Migração: Adicionar machine_id e sequence_pos à tabela production_schedule_result

Execução direta no banco SQLite.
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.database import engine
from sqlalchemy import text


def run_migration():
    """
    Adiciona machine_id e sequence_pos + índice de performance.
    """
    
    with engine.connect() as conn:
        print("=" * 100)
        print("INICIANDO MIGRACAO: adicionar machine_id e sequence_pos")
        print("=" * 100)
        print()
        
        # 1. Adicionar machine_id
        print("1) Adicionando coluna machine_id...")
        try:
            conn.execute(text("ALTER TABLE production_schedule_result ADD COLUMN machine_id INTEGER"))
            conn.commit()
            print("   OK: machine_id adicionado")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("   SKIP: machine_id ja existe")
            else:
                print(f"   ERRO: {e}")
                raise
        print()
        
        # 2. Adicionar sequence_pos
        print("2) Adicionando coluna sequence_pos...")
        try:
            conn.execute(text("ALTER TABLE production_schedule_result ADD COLUMN sequence_pos INTEGER"))
            conn.commit()
            print("   OK: sequence_pos adicionado")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("   SKIP: sequence_pos ja existe")
            else:
                print(f"   ERRO: {e}")
                raise
        print()
        
        # 3. Criar índice
        print("3) Criando indice de performance...")
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_psr_run_line_machine_seq
                ON production_schedule_result (run_id, production_line_id, machine_id, sequence_pos)
            """))
            conn.commit()
            print("   OK: indice criado")
        except Exception as e:
            print(f"   ERRO ao criar indice: {e}")
            raise
        print()
        
        # 4. Verificar estrutura final
        print("4) Verificando estrutura final...")
        result = conn.execute(text("PRAGMA table_info(production_schedule_result)"))
        rows = result.fetchall()
        
        column_names = [row[1] for row in rows]
        
        if "machine_id" in column_names:
            print("   OK: machine_id existe")
        else:
            print("   ERRO: machine_id NAO existe")
            
        if "sequence_pos" in column_names:
            print("   OK: sequence_pos existe")
        else:
            print("   ERRO: sequence_pos NAO existe")
        print()
        
        # 5. Verificar índice
        print("5) Verificando indices...")
        result = conn.execute(text("PRAGMA index_list(production_schedule_result)"))
        indexes = result.fetchall()
        
        index_names = [idx[1] for idx in indexes]
        if "idx_psr_run_line_machine_seq" in index_names:
            print("   OK: indice idx_psr_run_line_machine_seq existe")
        else:
            print("   AVISO: indice nao encontrado")
        print()
        
        print("=" * 100)
        print("MIGRACAO CONCLUIDA COM SUCESSO")
        print("=" * 100)
        print()
        print(f"Total de colunas apos migracao: {len(rows)}")
        print()


if __name__ == "__main__":
    print("\n")
    print("=" * 100)
    print("MIGRACAO: Adicionar machine_id e sequence_pos".center(100))
    print("=" * 100)
    print()
    
    run_migration()
    
    print("=" * 100)
    print("Migracao executada com sucesso!")
    print("=" * 100)
    print()
