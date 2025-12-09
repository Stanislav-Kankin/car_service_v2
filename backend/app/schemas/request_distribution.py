from typing import List
from pydantic import BaseModel, Field


class RequestDistributeIn(BaseModel):
    """
    Список ID сервисов, которым была отправлена заявка.
    """
    service_center_ids: List[int] = Field(
        ...,
        description="Список ID СТО, получивших эту заявку.",
        min_items=1,
    )
