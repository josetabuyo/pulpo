# Plan: IA y agentes (Etapa 3)

## Objetivo

Activar el Feature #6 del modelo de features: un agente con IA que responde con contexto, reemplazando o asistiendo al operador humano.

## Por qué Python primero

El ecosistema de IA es Python-first. Al haber migrado el backend a Python, este feature se puede implementar sin cambiar el stack:

- **LangGraph** — orquestación de flujos de agente con estado
- **Claude SDK / OpenAI SDK** — modelos de lenguaje
- **LlamaIndex** — RAG, búsqueda en documentos de la empresa
- **Playwright** — el agente puede usar el browser como herramienta

## Modelo de activación

El agente es una feature activable por empresa (igual que auto-reply hoy):
- `feature_ai_enabled: true` en la config de la empresa
- Si está activo, el bot no responde con texto fijo — invoca al agente
- El agente tiene contexto: historial de conversación, info de la empresa, documentos
- El operador puede seguir respondiendo manualmente desde el panel — el agente asiste, no reemplaza

## Componentes a construir

1. **Integración LangGraph** — flujo de agente con memoria de conversación
2. **RAG por empresa** — cada empresa puede subir documentos (FAQ, catálogo, políticas)
3. **Handoff agente → humano** — si el agente no sabe responder, escala al operador
4. **Panel admin** — activar/desactivar IA por empresa, ver las conversaciones del agente

## Dependencias

- `PLAN_CONTACTOS.md` implementado — el agente necesita saber quién es el contacto
- Conversaciones unificadas — el agente necesita historial por contacto

## Estado

Horizonte lejano. No empezar hasta tener estabilizado el pipeline de mensajes y contactos.
