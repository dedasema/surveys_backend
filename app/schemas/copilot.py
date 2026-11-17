# app/schemas/copilot.py
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from uuid import UUID

class CopilotMessageItem(BaseModel):
    sender: str  # "user", "assistant", "system"
    text: str

class CopilotChatIn(BaseModel):
    message: str
    history: Optional[List[CopilotMessageItem]] = None
    campana_id: Optional[UUID] = None

class ToolExecutionRecord(BaseModel):
    tool: str
    arguments: Dict[str, Any]
    result_summary: str

class CopilotChatOut(BaseModel):
    answer: str
    tools_used: Optional[List[ToolExecutionRecord]] = None
    suggested_actions: Optional[List[str]] = None
