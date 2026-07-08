"""
Dominio de conversación — cuándo una ejecución de flow acumula turnos.

Un flow NO es intrínsecamente una conversación: es un grafo genérico de nodos,
puede disparar por un webhook y no involucrar a ningún humano (un circuito
eléctrico que prende una luz es tan "flow" como un chat). El engine
(graphs/compiler.py) no sabe nada de esto — es agnóstico a mensajería.

Este módulo es el dueño de esa decisión: una conversación arranca cuando un
flow entra por un trigger de canal humano (BaseMessageTriggerNode — WhatsApp,
Telegram, y los que se agreguen a futuro) y continúa cuando un wait_user
reanuda esa misma ejecución. compiler.py llama a estas funciones en esos dos
puntos exactos; el resto del engine no necesita saber que "conversation" existe.

Ver graphs/nodes/state.py para el shape de data["conversation"].
"""
from .nodes.state import FlowState, append_conversation_entry


def start_conversation(state: FlowState) -> None:
    """Primer turno de una conversación nueva: el mensaje que la disparó.

    Llamar solo cuando el flow entra por un trigger de BaseMessageTriggerNode
    (o el legacy __start__, message-based desde antes de que existieran los
    triggers) — ver compiler.py.

    Idempotente: un mismo mensaje entrante puede matchear más de un flow (el
    engine llama execute_flow() una vez por flow sobre el mismo FlowState) —
    no hay que duplicar el primer turno si la conversación ya arrancó.
    """
    if "conversation" in state.data:
        return
    append_conversation_entry(state, "user", state.message)


def continue_conversation(state: FlowState) -> None:
    """Turno siguiente al reanudar un wait_user.

    El resto de la conversación ya viaja en data (restaurada desde slots_json
    antes de esta llamada) — acá solo se agrega el mensaje nuevo que trajo
    la reanudación.
    """
    append_conversation_entry(state, "user", state.message)


def record_bot_reply(state: FlowState, content: str) -> None:
    """Registra la respuesta del bot — solo si esta ejecución ya es una
    conversación (evita que un flow no-conversacional, ej. api_trigger,
    termine con un data["conversation"] huérfano de un solo turno)."""
    if "conversation" in state.data:
        append_conversation_entry(state, "bot_reply", content)
