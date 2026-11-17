# Feature: MCP Copilot Agents
Feature Name: mcp_copilot_agents
Description: Implement intelligent agents using Model Context Protocol (MCP) core with multi-tenant isolation and integrated SaaS web Copilot.

## Specs
- S1: "MCP es para que al agente no tenga acceso directo a la base de datos" - The agent must not execute raw SQL or direct database queries; every action must pass through an isolated, role-verified tool with strictly enforced multi-tenant `suscriptor_id` filtering.
- S2: "el núcleo (MCP) será utilizable para externos si en un futuro decidimos implementar" - The core tools must be exposed via standard MCP JSON-RPC 2.0 endpoints (`tools/list`, `tools/call`, `initialize`), capable of authentication via Bearer token.
- S3: "integrado como chat o chatbot en el sistema" - A web Copilot service with LLM tool calling (Gemini) that allows Empresa users to chat, query metrics, inspect campaigns, and review fraud alerts with audit logging in `AgenteDecision`.
- S4: Copilot HTTP Endpoint: `POST /copilot/chat` (alias `POST /agente/copilot`) authenticated with JWT Bearer token, accepting message and conversation history, returning answer, tools executed, and suggested actions.
- S5: "al finalizar todo con pruebas correspondientes si sale bien me das el prompt para el Frontend" - Full automated tests verifying MCP protocol and Copilot endpoints, followed by a complete prompt for the Frontend team.

## Tasks
- [x] T1: (S1) Create MCP Registry, Actor Context, and Empresa Tools (metrics, campaigns, fraud) [route: inline] [commit: 9d36d32]
- [x] T2: (S2) Implement MCP Protocol JSON-RPC 2.0 Router with Bearer Authentication [route: inline] [commit: 9d36d32]
- [x] T3: (S3) Implement Copilot Orchestrator Service with Gemini Function Calling & Decision Audit [route: inline] [commit: 9d36d32]
- [x] T4: (S4) Implement Copilot Router and Register in FastAPI main application [route: inline] [commit: 9d36d32]
- [x] T5: (S5) Write unit/integration test suite in tests/test_copilot_mcp.py, verify pass, commit, and prepare Frontend prompt [route: inline] [commit: 9d36d32]

## Log
- L1: "Analiza el alcance para implementar 'Agentes inteligentes con MCP', aquí no se si sería para el dueño del SAAS, empresa u operador, incluso para los 3, esto igual debes analizar, MCP es para que al agente no tenga acceso directo a la base de datos"
- L2: "Si, pero como dijiste el núcleo (MCP) será utilizable para externos si en un futuro decidimos implementar, al finalizar todo con pruebas correspondientes si sale bien me das el prompt para el Frontend"
