# Nuevo Diseño: Sistema Data-Driven de Triggers

## Problema Actual
- `__start__` es un marcador implícito sin configuración
- `input_text` es específico para mensajes de texto
- No hay forma de disparar flows por otros eventos (timer, webhook, sensor)

## Objetivo
Sistema donde **cada tipo de trigger es un nodo explícito** que:
1. Define qué tipo de evento dispara el flow
2. Contiene configuración específica para ese tipo
3. Permite composición de features reutilizables

## Arquitectura Propuesta

### 1. Nodos Trigger Específicos (no genéricos)

```python
# message_trigger.py
class MessageTriggerNode(BaseNode):
    config_schema() -> {
        "connection_id": {"type": "string", "required": True},
        "contact_phone": {"type": "string", "required": False},
        "message_pattern": {"type": "string", "required": False},  # regex opcional
    }

# timer_trigger.py  
class TimerTriggerNode(BaseNode):
    config_schema() -> {
        "cron_expression": {"type": "string", "required": True},
        "timezone": {"type": "string", "required": False},
    }

# webhook_trigger.py
class WebhookTriggerNode(BaseNode):
    config_schema() -> {
        "path": {"type": "string", "required": True},
        "method": {"type": "select", "options": ["GET", "POST", "PUT"]},
        "secret": {"type": "string", "required": False},  # para validación
    }
```

### 2. Engine Modificado

El engine necesita:
1. **Resolver qué flows están activos** para un tipo de evento
2. **Verificar match** con la configuración del trigger
3. **Ejecutar** solo los flows que matchean

```python
async def find_flows_for_event(event_type: str, event_data: dict) -> list[dict]:
    """
    Encuentra flows cuyo trigger node matchea el evento.
    
    event_type: "message", "timer", "webhook", "sensor"
    event_data: datos específicos del evento
    """
    # 1. Obtener todos los flows activos
    # 2. Para cada flow, encontrar su trigger node
    # 3. Verificar si el trigger matchea el evento
    # 4. Retornar flows que matchean
```

### 3. Estado Genérico (FlowState Expandido)

```python
@dataclass
class FlowState:
    # Metadata del evento
    event_type: str  # "message", "timer", "webhook", "sensor"
    event_data: dict  # datos crudos del evento
    
    # Para mensajes (backward compatibility)
    message: str = ""
    contact_phone: str = ""
    bot_id: str = ""
    
    # Para webhooks
    webhook_payload: Optional[dict] = None
    
    # Para timers
    trigger_time: Optional[datetime] = None
    
    # Para sensores
    sensor_value: Optional[float] = None
    
    # Salida
    reply: Optional[str] = None
    actions: list[dict] = field(default_factory=list)  # acciones a ejecutar
```

### 4. Sistema de Registro de Triggers

```python
TRIGGER_REGISTRY: dict[str, type] = {
    "message_trigger": MessageTriggerNode,
    "timer_trigger": TimerTriggerNode,
    "webhook_trigger": WebhookTriggerNode,
}

def register_trigger(trigger_type: str, node_class: type):
    """API para plugins/extensions"""
    TRIGGER_REGISTRY[trigger_type] = node_class
```

## Ventajas

### 1. Data-Driven
- Cada empresa puede componer flows con diferentes triggers
- Nuevos tipos de triggers se agregan como plugins
- Configuración declarativa en JSON

### 2. Reutilización
- Features como "notificar por Telegram cuando temperatura > 30°C" son flows reutilizables
- Se pueden exportar/importar flows completos entre empresas
- Biblioteca de flows templates

### 3. Escalabilidad
- Engine centralizado maneja todos los tipos de eventos
- Sistema de colas para procesamiento async
- Métricas por tipo de trigger

### 4. Compatibilidad con LangGraph
- Cada flow es un grafo ejecutable
- Podemos migrar gradualmente a StateGraph de LangGraph
- Los nodos actuales pueden wrappear funciones de LangGraph

## Migración desde Sistema Actual

### Paso 1: Mantener `input_text` como alias de `message_trigger`
```python
# En __init__.py
NODE_REGISTRY["input_text"] = MessageTriggerNode
```

### Paso 2: Actualizar engine para soportar múltiples triggers
- Modificar `execute_flow()` para encontrar cualquier trigger node
- Actualizar `run_flows()` para aceptar `event_type` y `event_data`

### Paso 3: Migrar flows existentes
- Script automático convierte `input_text` → `message_trigger`
- Mantener backward compatibility durante transición

### Paso 4: Agregar nuevos triggers
- Implementar `timer_trigger`, `webhook_trigger`
- Agregar endpoints/schedulers correspondientes

## Ejemplo de Uso

### Flow: "Notificar pedidos urgentes"
```
[message_trigger] → [router] → [notify_telegram]
      ↓                    ↓
[summarize]        [reply_confirmacion]
```

**message_trigger config:**
```json
{
  "connection_id": "whatsapp_business",
  "message_pattern": ".*urgente.*"
}
```

### Flow: "Reporte diario de ventas"
```
[timer_trigger] → [fetch_sales] → [llm_analyze] → [notify_email]
```

**timer_trigger config:**
```json
{
  "cron_expression": "0 9 * * *",  # 9 AM daily
  "timezone": "America/Argentina/Buenos_Aires"
}
```

## Implementación Inmediata (Fase 1.5)

1. **Renombrar `input_text.py` → `message_trigger.py`**
2. **Actualizar `NODE_REGISTRY` y tests**
3. **Modificar `compiler.py` para buscar cualquier trigger node**
4. **Mantener alias `input_text` para backward compatibility**
5. **Actualizar documentación y scripts de migración**

Esto nos da la base para un sistema data-driven sin romper lo que ya funciona.