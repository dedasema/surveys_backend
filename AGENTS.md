# Reglas y Protocolos del Proyecto (surveys_backend)

## 📌 Protocolo Obligatorio de Sincronización en Engram

1. **Persistencia en Cada Commit/Feature**: Tras CADA implementación de código, refactorización o ejecución de `git commit` en este proyecto, el agente DEBE ejecutar inmediatamente `engram:mem_save` y `engram:mem_pin` para registrar el avance técnico.
2. **Comprobante Transparente en Chat**: Cada mensaje de entrega o conclusión de tarea DEBE finalizar con una firma visible conteniendo el `Memory ID` generado por Engram.

```markdown
---
🛡️ **Recibo de Persistencia Engram**:
- **Memory ID**: `#<ID>`
- **Proyecto**: `surveys_backend`
- **Estado**: ✅ Guardado y Fijado
---
```
Si el mensaje no contiene este recibo con su ID numérico real devuelto por la API de Engram, el usuario sabrá inmediatamente que se omitió la persistencia.
