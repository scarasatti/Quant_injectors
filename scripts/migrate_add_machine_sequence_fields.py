"""
Script de migração para adicionar campos machine_id e sequence_pos
à tabela production_schedule_result.

IMPORTANTE: Execute este script UMA VEZ antes de usar o novo sistema.

Uso:
    python scripts/migrate_add_machine_sequence_fields.py
"""

import sys
from pathlib import Path

# Adicionar raiz do projeto ao path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, Column, Integer, inspect
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from app.models.production_schedule_result import ProductionScheduleResult
import sqlite3


def migrate_sqlite():
    """Migração para SQLite (local.db)"""
    db_path = project_root / "local.db"
    
    if not db_path.exists():
        print(f"⚠️  Banco de dados não encontrado: {db_path}")
        print("   Se você está usando outro banco, ajuste este script.")
        return
    
    print(f"📊 Conectando ao banco: {db_path}")
    
    # Conectar diretamente com sqlite3
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Verificar se os campos já existem
    cursor.execute("PRAGMA table_info(production_schedule_result)")
    columns = [row[1] for row in cursor.fetchall()]
    
    needs_machine_id = "machine_id" not in columns
    needs_sequence_pos = "sequence_pos" not in columns
    
    if not needs_machine_id and not needs_sequence_pos:
        print("✅ Campos machine_id e sequence_pos já existem. Nenhuma migração necessária.")
        conn.close()
        return
    
    print("\n🔧 Adicionando novos campos...")
    
    try:
        if needs_machine_id:
            print("   - Adicionando campo machine_id...")
            cursor.execute("""
                ALTER TABLE production_schedule_result 
                ADD COLUMN machine_id INTEGER DEFAULT 1
            """)
            print("   ✅ Campo machine_id adicionado")
        
        if needs_sequence_pos:
            print("   - Adicionando campo sequence_pos...")
            cursor.execute("""
                ALTER TABLE production_schedule_result 
                ADD COLUMN sequence_pos INTEGER DEFAULT 0
            """)
            print("   ✅ Campo sequence_pos adicionado")
        
        # Atualizar registros existentes com valores padrão baseados em order_index
        print("\n   - Atualizando registros existentes...")
        cursor.execute("""
            UPDATE production_schedule_result 
            SET 
                machine_id = COALESCE(machine_id, 1),
                sequence_pos = COALESCE(sequence_pos, order_index)
            WHERE machine_id IS NULL OR sequence_pos IS NULL
        """)
        
        affected_rows = cursor.rowcount
        print(f"   ✅ {affected_rows} registros atualizados")
        
        conn.commit()
        print("\n✅ Migração concluída com sucesso!")
        
    except Exception as e:
        print(f"\n❌ Erro na migração: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_postgres():
    """Migração para PostgreSQL (produção)"""
    print("\n🐘 MIGRAÇÃO POSTGRESQL")
    print("=" * 60)
    print("Para PostgreSQL (produção), execute os seguintes comandos SQL:")
    print()
    print("-- Adicionar campos machine_id e sequence_pos")
    print("ALTER TABLE production_schedule_result")
    print("    ADD COLUMN IF NOT EXISTS machine_id INTEGER DEFAULT 1,")
    print("    ADD COLUMN IF NOT EXISTS sequence_pos INTEGER DEFAULT 0;")
    print()
    print("-- Atualizar registros existentes")
    print("UPDATE production_schedule_result")
    print("SET ")
    print("    machine_id = COALESCE(machine_id, 1),")
    print("    sequence_pos = COALESCE(sequence_pos, order_index)")
    print("WHERE machine_id IS NULL OR sequence_pos IS NULL;")
    print()
    print("=" * 60)


if __name__ == "__main__":
    print("=" * 60)
    print("MIGRAÇÃO: Adicionar machine_id e sequence_pos")
    print("=" * 60)
    print()
    
    # Migrar SQLite local
    migrate_sqlite()
    
    # Mostrar comandos para PostgreSQL
    print()
    migrate_postgres()
    
    print("\n✅ Script de migração finalizado!")
    print("\nPRÓXIMOS PASSOS:")
    print("1. Se você usa PostgreSQL em produção, execute os comandos SQL acima")
    print("2. Reinicie a aplicação para carregar os novos campos")
    print("3. Teste a geração de schedule reports com generate_schedule_report(run_id, db)")



