"""Public Python library interface for Pulpo.

Import from here to use Pulpo as a library:

    from pulpo.interfaces.lib import list_bots, get_flow, send_message

All functions are async where the underlying operation is async.
"""
from pulpo.business.bots import (
    list_bots,
    get_bot,
    create_bot,
    update_bot,
    delete_bot,
)
from pulpo.business.connections import (
    list_connections,
    create_connection,
    delete_connection,
    list_google_connections,
    create_google_connection,
    delete_google_connection,
)
from pulpo.business.flows import (
    list_flows,
    get_flow,
    create_flow,
    update_flow,
    delete_flow,
    list_node_types,
    trigger_flow,
)
from pulpo.business.messages import list_messages
from pulpo.business.contacts import (
    list_contacts,
    get_contact,
    create_contact,
    update_contact,
    delete_contact,
)
from pulpo.business.settings import read_settings, write_settings

__all__ = [
    "list_bots", "get_bot", "create_bot", "update_bot", "delete_bot",
    "list_connections", "create_connection", "delete_connection",
    "list_google_connections", "create_google_connection", "delete_google_connection",
    "list_flows", "get_flow", "create_flow", "update_flow", "delete_flow",
    "list_node_types", "trigger_flow",
    "list_messages",
    "list_contacts", "get_contact", "create_contact", "update_contact", "delete_contact",
    "read_settings", "write_settings",
]
