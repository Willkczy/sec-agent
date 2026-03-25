from pydantic import BaseModel
from typing import Optional, Any


class AskRequest(BaseModel):
    query: str
    max_iters: Optional[int] = 3
    org_id: Optional[str] = None


class AskResponse(BaseModel):
    answer: str
    debug: dict[str, Any]

    class Config:
        arbitrary_types_allowed = True
