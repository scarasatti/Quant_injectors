from pydantic import BaseModel

class ClientBase(BaseModel):
    name: str
    priority: int


class ClientCreate(ClientBase):
    pass

class ClientUpdate(ClientBase):
    pass

class ClientResponse(ClientBase):
    id: int

    class Config:
        from_attributes = True
