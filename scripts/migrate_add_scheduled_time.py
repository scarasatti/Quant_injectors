"""
Script de migração para adicionar a coluna scheduled_time
à tabela production_schedule_result (data + hora prometida da planilha).

Execute UMA VEZ antes de usar data/hora prometida no schedule report.

Uso:
    python scripts/migrate_add_scheduled_time.py
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import sqlite3


def migrate_sqlite():
    """Adiciona scheduled_time (TIME) em production_schedule_result."""
    db_path = project_root / "local.db"
    if not db_path.exists():
        print(f"⚠️  Banco não encontrado: {db_path}")
        return
    print(f"📊 Conectando: {db_path}")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(production_schedule_result)")
    columns = [row[1] for row in cursor.fetchall()]
    if "scheduled_time" in columns:
        print("✅ Coluna scheduled_time já existe. Nenhuma migração necessária.")
        conn.close()
        return
    print("🔧 Adicionando coluna scheduled_time (TIME)...")
    cursor.execute("""
        ALTER TABLE production_schedule_result
        ADD COLUMN scheduled_time TIME
    """)
    conn.commit()
    print("✅ Coluna scheduled_time adicionada.")
    conn.close()


def main():
    migrate_sqlite()
    print("\n✅ Migração concluída. Reinicie a aplicação se estiver rodando.")


if __name__ == "__main__":
    main()
