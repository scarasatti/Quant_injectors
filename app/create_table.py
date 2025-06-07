from app.database import Base, engine
from app.models import user, enterprise, password_reset_token  # importe o novo modelo

Base.metadata.create_all(bind=engine)
