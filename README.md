<div align="center">

# Quant Injectors API

Orquestração de sequenciamento de produção com FastAPI, SQLAlchemy e modelos de otimização (PuLP).

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)
[![Status](https://img.shields.io/badge/status-active-success.svg)](#)

</div>

---

## 🚀 Visão Geral

O projeto centraliza cadastros (clientes, produtos, setups, máquinas, linhas de produção, calendários), executa otimizações de fila via PuLP e expõe a operação como API REST com FastAPI.  
Os resultados do solver são persistidos e disponibilizados em tempo real via SSE.

Para detalhes do schema de banco, consulte `DATABASE_SCHEMA.md`.

---

## 🧱 Stack Principal

- **FastAPI** para APIs REST e SSE  
- **SQLAlchemy** + **Alembic-like setup** (via `init_db.py`)  
- **PuLP** para modelos de sequenciamento e injetoras  
- **SQLite/Postgres** (definido por `DATABASE_URL`)  
- **Pydantic** para schemas e validações

---

## 🧑‍💻 Como rodar localmente

```bash
# 1. Crie o ambiente e instale dependências
python -m venv venv
source venv/Scripts/activate  # Windows PowerShell
pip install -r requirements.txt

# 2. Configure o banco (opcional para SQLite)
python init_db.py

# 3. Execute a API
uvicorn main:app --reload
```

A documentação interativa estará em `http://localhost:8000/docs`.

---

## 📁 Estrutura de Pastas

```
app/
├── auth/                 # Autenticação e JWT
├── models/               # Tabelas SQLAlchemy
├── routes/               # Rotas FastAPI
├── schemas/              # Schemas Pydantic
├── utils/                # SSE, email, helpers
algorithm/                # Solvers e modelos PuLP
DATABASE_SCHEMA.md        # Documentação completa do banco
main.py                   # Entrada FastAPI
init_db.py                # Bootstrap das tabelas
```

---

## 🔌 Principais Rotas

- `POST /auth/login` – autenticação
- `GET /sequenciamento/stream` – SSE do solver
- `POST /sequenciamento/solve` – solver principal
- CRUDs para `clients`, `products`, `jobs`, `setup`, `maquinas`, `production-lines`
- Uploads de planilhas (`/upload_*`)
- `GET /init-db` – criação das tabelas (ambiente dev)

Consulte `app/routes` para os endpoints completos.

---

## 🧠 Documentação do Banco

Toda a modelagem (18 tabelas, relacionamentos, validações) está descrita em `DATABASE_SCHEMA.md`.  
Use esse arquivo como referência para integrações, migrações e análises.

---

## 🧪 Testes e Qualidade

Atualmente não há suite automatizada. Recomenda-se:
- Validar respostas das rotas com `pytest` + `httpx`
- Rodar linters (`ruff`, `flake8`) e formatadores (`black`) antes do commit
- Monitorar warnings do solver via logs

---

## 📬 Contato e Suporte

Para dúvidas ou sugestões, utilize os canais internos do time ou abra um issue no repositório.

---

**Happy hacking!** 🛠️