from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ResponseMeta(BaseModel):
    source: Optional[str] = None
    delay: Optional[str] = None
    unit: Optional[str] = None
    version: int = 1


class APIResponse(BaseModel):
    data: Any
    meta: ResponseMeta = Field(default_factory=ResponseMeta)
    updated_at: datetime
