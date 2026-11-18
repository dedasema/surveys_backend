# app/schemas/copilot.py
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from uuid import UUID

class CopilotMessageItem(BaseModel):
    sender: str  # "user", "assistant", "system"
    text: str

class CopilotSessionCreate(BaseModel):
    title: Optional[str] = "Nueva conversación"
    campana_id: Optional[UUID] = None

class CopilotSessionOut(BaseModel):
    id: UUID
    title: str
    campana_id: Optional[UUID] = None
    created_at: str
    updated_at: str
    message_count: int = 0

class CopilotMessageOut(BaseModel):
    id: UUID
    sender: str
    text: str
    tools_used: Optional[List[Dict[str, Any]]] = None
    fuentes_citadas: Optional[List[Dict[str, Any]]] = None
    created_at: str

class CopilotChatIn(BaseModel):
    message: str
    history: Optional[List[CopilotMessageItem]] = None
    campana_id: Optional[UUID] = None
    session_id: Optional[UUID] = None

class ToolExecutionRecord(BaseModel):
    tool: str
    arguments: Dict[str, Any]
    result_summary: str

class CopilotChatOut(BaseModel):
    answer: str
    session_id: Optional[UUID] = None
    tools_used: Optional[List[ToolExecutionRecord]] = None
    fuentes_citadas: Optional[List[Dict[str, Any]]] = None
    suggested_actions: Optional[List[str]] = None
