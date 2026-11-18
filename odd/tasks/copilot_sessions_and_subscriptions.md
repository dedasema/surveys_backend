# Feature: Copilot Sessions, RAG MCP Tool and Subscription Lifecycle
Feature Name: copilot_sessions_and_subscriptions
Description: Implement server-side chat session persistence for Copilot, integrate RAG qualitative search as an official MCP tool, and enforce subscription billing lifecycle (proration on upgrade, end-of-period downgrade validation, and renewal extensions).

## Specs
- S1: "Crear las tablas para almacenar las sesiones de chat y sus mensajes asociados al tenant: CopilotSesion y CopilotMensaje"
- S2: "Montar en app/routers/copilot_router.py: GET /copilot/sessions, POST /copilot/sessions, GET /copilot/sessions/{session_id}/messages, DELETE /copilot/sessions/{session_id}"
- S3: "Actualización de POST /copilot/chat: Aceptar en el payload session_id, persistir mensajes de usuario y asistente, pasar historial y actualizar título de sesión"
- S4: "En app/services/mcp/tools/, registrar la función RAG existente como una Tool oficial en mcp_registry: consultar_conocimiento_rag"
- S5: Subscription billing lifecycle: Proration credit for unused days on plan upgrades, resource validation and scheduled transition for downgrades, and expiration date extension on renewals.
- S6: Full automated test coverage verifying multi-tenant session isolation, RAG MCP tool invocation, and subscription upgrade/downgrade logic.

## Tasks
- T1: (S1) Create CopilotSesion and CopilotMensaje models and DDL migrations in startup [route: inline] [commit: pending]
- T2: (S4) Register consultar_conocimiento_rag in MCP registry with multi-tenant filtering [route: inline] [commit: pending]
- T3: (S2, S3) Implement session management endpoints and update POST /copilot/chat with persistence [route: inline] [commit: pending]
- T4: (S5) Implement subscription transition validations (upgrade proration, downgrade resource checks, renewal extension) [route: inline] [commit: pending]
- T5: (S6) Create comprehensive test suite in tests/test_copilot_sessions.py and tests/test_subscription_lifecycle.py, verify pass, commit, and deliver [route: inline] [commit: pending]

## Log
- L1: "Supongamos que pagó el 1 de enero el plan Pro, y luego el 5 de enero quiere pagar el plan Plus... Si, también implementa lo siguiente: Desde el Frontend de SurveySaaS acabamos de unificar el Asistente RAG y el Copiloto Inteligente MCP..."
