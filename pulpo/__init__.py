"""Pulpo — bot orchestration engine.

Use as a library:
    from pulpo import list_bots, get_flow, create_flow

Start servers:
    pulpo server ui --port 8000
    pulpo server api --port 8001
"""
from pulpo.interfaces.lib import (
    list_bots, get_bot, create_bot, update_bot, delete_bot,
    list_connections, create_connection, delete_connection,
    list_google_connections, create_google_connection, delete_google_connection,
    list_flows, get_flow, create_flow, update_flow, delete_flow,
    list_node_types, trigger_flow,
    list_messages,
    list_contacts, get_contact, create_contact, update_contact, delete_contact,
    read_settings, write_settings,
)

__version__ = "0.1.0"
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
