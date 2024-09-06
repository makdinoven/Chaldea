from pydantic import BaseModel

class CharacterRequestBase(BaseModel):
    name: str
    id_subrace: int
    biography: str
    personality: str
    id_class: int

class CharacterRequestCreate(CharacterRequestBase):
    pass

class CharacterRequest(CharacterRequestBase):
    id: int
    status: str

    class Config:
        orm_mode = True
