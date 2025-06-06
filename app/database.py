from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# URL de conexão (ajuste se for MySQL, PostgreSQL, etc.)
SQLALCHEMY_DATABASE_URL = "sqlite:///./lindo.db"

# Conexão com SQLite (para testes locais)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Gerenciador de sessões
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base usada para declarar os modelos
Base = declarative_base()
