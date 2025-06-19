from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base

class Enterprise(Base):
    __tablename__ = "enterprises"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    representative_email = Column(String, nullable=False)
    access_count = Column(Integer, nullable=False)
    model_type = Column(String, nullable=False)
    users = relationship("User", back_populates="enterprise")

    # Este será o relacionamento com os tokens
    access_tokens = relationship("AccessToken", back_populates="enterprise")
