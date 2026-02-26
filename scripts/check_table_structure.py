"""
Script para verificar a estrutura REAL da tabela no banco de dados.

Executa: PRAGMA table_info(production_schedule_result);
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.database import engine
from sqlalchemy import text


def check_table_structure():
    """
    Executa PRAGMA table_info para ver a estrutura real da tabela.
    """
    
    with engine.connect() as conn:
        print("=" * 100)
        print("EXECUTANDO: PRAGMA table_info(production_schedule_result);")
        print("=" * 100)
        print()
        
        result = conn.execute(text("PRAGMA table_info(production_schedule_result)"))
        rows = result.fetchall()
        
        if not rows:
            print("ERRO: Tabela 'production_schedule_result' nao existe no banco!")
            return
        
        print(f"{'CID':<5} {'NAME':<35} {'TYPE':<20} {'NOTNULL':<10} {'DEFAULT':<15} {'PK':<5}")
        print("-" * 100)
        
        for row in rows:
            cid, name, type_, notnull, dflt_value, pk = row
            dflt_str = str(dflt_value) if dflt_value is not None else "NULL"
            print(f"{cid:<5} {name:<35} {type_:<20} {notnull:<10} {dflt_str:<15} {pk:<5}")
        
        print("-" * 100)
        print()
        print(f"Total de colunas: {len(rows)}")
        print()
        
        # Verificar colunas críticas
        print("=" * 100)
        print("VERIFICAÇÃO DE COLUNAS CRÍTICAS")
        print("=" * 100)
        print()
        
        column_names = [row[1] for row in rows]
        
        critical_columns = [
            "production_line_id",
            "machine_id",
            "sequence_pos",
            "job_index_solver",
            "product_name",
            "mold_name",
            "client_name",
            "order_index"
        ]
        
        for col in critical_columns:
            if col in column_names:
                print(f"OK  {col:<30} -> EXISTE")
            else:
                print(f"ERRO {col:<30} -> NAO EXISTE")
        
        print()
        print("=" * 100)
        print()


if __name__ == "__main__":
    print("\n")
    print("=" * 100)
    print("ESTRUTURA REAL DA TABELA production_schedule_result".center(100))
    print("=" * 100)
    print()
    
    check_table_structure()
    
    print("=" * 100)
    print("Diagnostico concluido")
    print("=" * 100)
    print()

