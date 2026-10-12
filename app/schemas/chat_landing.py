# app/schemas/chat_landing.py
from pydantic import BaseModel, ConfigDict
from typing import List, Optional

class ChatMessageItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sender: str  # "user" o "bot"
    text: str

class ChatLandingIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    message: str
    history: Optional[List[ChatMessageItem]] = None

class ActionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    label: str
    href: Optional[str] = None
    action: Optional[str] = None

class ChatLandingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    answer: str
    actions: Optional[List[ActionItem]] = None
