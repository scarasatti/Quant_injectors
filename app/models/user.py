from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    enterprise_id = Column(Integer, ForeignKey("enterprises.id"))
    token_version = Column(Integer, default=0)

    enterprise = relationship("Enterprise", back_populates="users")
    reset_tokens = relationship("PasswordResetToken", back_populates="user")
    sessions = relationship("UserSession", back_populates="user")