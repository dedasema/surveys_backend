# app/routers/mcp_router.py
import json
import logging
from typing import Dict, Any, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user, TokenData
from app.services.mcp import mcp_registry
from app.services.mcp.context import resolver_actor_context

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/mcp",
    tags=["Model Context Protocol (MCP)"]
)

class MCPJsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[Union[int, str]] = 1
    method: str
    params: Optional[Dict[str, Any]] = None

@router.post("", summary="Endpoint oficial MCP JSON-RPC 2.0")
@router.post("/rpc", summary="Alias endpoint oficial MCP JSON-RPC 2.0")
async def mcp_jsonrpc_endpoint(
    rpc_req: MCPJsonRpcRequest,
    db: Session = Depends(get_db),
    token_data: TokenData = Depends(get_current_user)
):
    """
    Punto de entrada estándar Model Context Protocol (MCP) para clientes externos
    (Claude Desktop, Cursor, Goose, etc.) y agentes orquestadores.
    Aplica autorización estricta multi-tenant y expone tools según el rol del actor.
    """
    actor = resolver_actor_context(db, token_data)
    req_id = rpc_req.id
    method = rpc_req.method
    params = rpc_req.params or {}

    # 1. Handshake de inicialización
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False}
                },
                "serverInfo": {
                    "name": "surveys-saas-mcp-server",
                    "version": "1.0.0"
                },
                "actor": {
                    "user_id": str(actor.user_id),
                    "role": actor.role,
                    "suscriptor_id": str(actor.suscriptor_id) if actor.suscriptor_id else None
                }
            }
        }

    # 2. Catálogo de herramientas autorizadas
    if method in ("tools/list", "tools_list"):
        tools = mcp_registry.list_tools_for_actor(actor)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": tools
            }
        }

    # 3. Invocación de herramientas
    if method in ("tools/call", "tools_call"):
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        if not tool_name:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32602,
                    "message": "Falta parámetro 'name' en params"
                }
            }

        res = await mcp_registry.execute_tool(tool_name, arguments, actor, db)
        is_error = not res["success"]
        payload_text = json.dumps(res["data"] if not is_error else {"error": res["error"]}, ensure_ascii=False)

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": payload_text
                    }
                ],
                "isError": is_error
            }
        }

    # Método no soportado
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {
            "code": -32601,
            "message": f"Método MCP '{method}' no soportado."
        }
    }


@router.get("/tools", summary="Listado REST rápido de herramientas MCP autorizadas")
async def list_mcp_tools_rest(
    db: Session = Depends(get_db),
    token_data: TokenData = Depends(get_current_user)
):
    actor = resolver_actor_context(db, token_data)
    tools = mcp_registry.list_tools_for_actor(actor)
    return {
        "actor": {
            "user_id": str(actor.user_id),
            "role": actor.role,
            "suscriptor_id": str(actor.suscriptor_id) if actor.suscriptor_id else None
        },
        "total_tools": len(tools),
        "tools": tools
    }
