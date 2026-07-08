"""
Dominio de conversación — cuándo una ejecución de flow acumula turnos.

Un flow NO es intrínsecamente una conversación: es un grafo genérico de nodos,
puede disparar por un webhook y no involucrar a ningún humano (un circuito
eléctrico que prende una luz es tan "flow" como un chat). El engine
(graphs/compiler.py) no sabe nada de esto — es agnóstico a mensajería.

Este módulo es el dueño de esa decisión: toda ejecución de flow arranca una
conversación de al menos un turno (el mensaje/payload que la disparó, sea un
trigger de canal humano, el legacy __start__, o un api_trigger externo) y
continúa cuando un wait_user reanuda esa misma ejecución. compiler.py llama a
estas funciones en esos puntos exactos; el resto del engine no necesita saber
que "conversation" existe.

Ver graphs/nodes/state.py para el shape de data["conversation"].
"""
from .nodes.state import FlowState, append_conversation_entry


def start_conversation(state: FlowState) -> None:
    """Primer turno de una conversación nueva: el mensaje que la disparó.

    Se llama en todo punto de entrada de execute_flow() (trigger de canal
    humano, legacy __start__, o api_trigger) — ver compiler.py. Si state.message
    viene vacío (algún trigger futuro sin mensaje real) simplemente no se crea
    "conversation": append_conversation_entry no agrega turnos sin content.

    Idempotente: un mismo mensaje entrante puede matchear más de un flow (el
    engine llama execute_flow() una vez por flow sobre el mismo FlowState) —
    no hay que duplicar el primer turno si la conversación ya arrancó.
    """
    if "conversation" in state.data:
        return
    append_conversation_entry(state, "user", state.message, state.message_type)


def continue_conversation(state: FlowState) -> None:
    """Turno siguiente al reanudar un wait_user.

    El resto de la conversación ya viaja en data (restaurada desde slots_json
    antes de esta llamada) — acá solo se agrega el mensaje nuevo que trajo
    la reanudación.
    """
    append_conversation_entry(state, "user", state.message, state.message_type)


def record_bot_reply(state: FlowState, content: str) -> None:
    """Registra la respuesta del bot — solo si esta ejecución ya tiene
    conversación (guard defensivo: si start_conversation no la creó porque
    state.message vino vacío, no hay dónde appendear la respuesta)."""
    if "conversation" in state.data:
        append_conversation_entry(state, "bot_reply", content)
