# app/services/mcp/registry.py
import inspect
import logging
from typing import Dict, Any, List, Callable, Awaitable, Optional
from sqlalchemy.orm import Session

from .context import ActorContext

logger = logging.getLogger(__name__)

class MCPTool:
    def __init__(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        roles_permitidos: List[str],
        handler: Callable[[Session, ActorContext, Dict[str, Any]], Awaitable[Dict[str, Any]]]
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.roles_permitidos = roles_permitidos
        self.handler = handler

    def es_permitida_para(self, actor: ActorContext) -> bool:
        if "*" in self.roles_permitidos or "all" in self.roles_permitidos:
            return True
        if actor.es_admin():
            return True
        return actor.role in self.roles_permitidos

    def to_mcp_format(self) -> Dict[str, Any]:
        """Formato oficial del Model Context Protocol (MCP) v1"""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema
        }

    def to_gemini_format(self) -> Dict[str, Any]:
        """Formato compatible con Function Calling de Gemini y OpenAI"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema
            }
        }


class MCPRegistry:
    """
    Registro central desacoplado de herramientas MCP.
    Garantiza que el agente LLM solo descubra y ejecute herramientas
    para las cuales el actor autenticado tiene privilegios explícitos.
    """
    def __init__(self):
        self._tools: Dict[str, MCPTool] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        roles_permitidos: List[str]
    ):
        """Decorador para registrar herramientas MCP de manera declarativa."""
        def decorator(fn: Callable[[Session, ActorContext, Dict[str, Any]], Awaitable[Dict[str, Any]]]):
            tool = MCPTool(
                name=name,
                description=description,
                input_schema=input_schema,
                roles_permitidos=roles_permitidos,
                handler=fn
            )
            self._tools[name] = tool
            return fn
        return decorator

    def get_tool(self, name: str) -> Optional[MCPTool]:
        return self._tools.get(name)

    def list_tools_for_actor(self, actor: ActorContext) -> List[Dict[str, Any]]:
        """Devuelve las herramientas autorizadas en formato oficial MCP tools/list."""
        return [
            tool.to_mcp_format()
            for tool in self._tools.values()
            if tool.es_permitida_para(actor)
        ]

    def list_tools_for_gemini(self, actor: ActorContext) -> List[Dict[str, Any]]:
        """Devuelve las herramientas autorizadas para el cliente de IA Gemini."""
        return [
            tool.to_gemini_format()
            for tool in self._tools.values()
            if tool.es_permitida_para(actor)
        ]

    async def execute_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        actor: ActorContext,
        db: Session
    ) -> Dict[str, Any]:
        """
        Ejecuta una herramienta de forma segura verificando contexto de autorización.
        Retorna siempre un diccionario con resultado estructurado.
        """
        tool = self._tools.get(name)
        if not tool:
            return {
                "success": False,
                "error": f"Herramienta '{name}' no existe en el catálogo MCP.",
                "data": None
            }

        if not tool.es_permitida_para(actor):
            logger.warning(
                "Intento no autorizado de ejecutar tool '%s' por usuario %s con rol '%s'",
                name, actor.user_id, actor.role
            )
            return {
                "success": False,
                "error": f"Acceso denegado: tu rol '{actor.role}' no tiene permiso para ejecutar '{name}'.",
                "data": None
            }

        try:
            if inspect.iscoroutinefunction(tool.handler):
                result = await tool.handler(db, actor, arguments)
            else:
                result = tool.handler(db, actor, arguments)

            return {
                "success": True,
                "error": None,
                "data": result
            }
        except Exception as e:
            logger.exception("Error ejecutando tool MCP '%s': %s", name, str(e))
            return {
                "success": False,
                "error": f"Error interno en herramienta '{name}': {str(e)}",
                "data": None
            }


mcp_registry = MCPRegistry()
