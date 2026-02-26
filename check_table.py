import sqlite3

# Verificar no local.db
conn = sqlite3.connect('local.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()
conn.close()

print("Tabelas no local.db:")
for table in tables:
    print(f"  - {table[0]}")

if any('billing_configuration' in str(t) for t in tables):
    print("\n✅ billing_configuration EXISTE")
else:
    print("\n❌ billing_configuration NÃO EXISTE")
