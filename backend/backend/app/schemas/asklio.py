from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class VendorDocument(BaseModel):
    id: int
    filename: str
    file_type: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(extra="ignore")


class Vendor(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    behavioral_prompt: Optional[str] = None
    is_predefined: Optional[bool] = None
    documents: Optional[List[VendorDocument]] = None

    model_config = ConfigDict(extra="ignore")


class Conversation(BaseModel):
    id: int
    vendor_id: int
    team_id: Optional[int] = None
    title: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class Message(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: datetime

    model_config = ConfigDict(extra="ignore")
