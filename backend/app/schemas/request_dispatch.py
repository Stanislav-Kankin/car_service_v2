from datetime import datetime
from pydantic import BaseModel


class RequestDispatchBase(BaseModel):
    request_id: int
    service_center_id: int


class RequestDispatchCreate(RequestDispatchBase):
    pass


class RequestDispatchRead(RequestDispatchBase):
    id: int
    sent_at: datetime

    class Config:
        orm_mode = True
s