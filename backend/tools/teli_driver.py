"""
Shim — re-exports teli.driver for use within Pulpo's tools/ layout.

    import tools.teli_driver as td   →   same as   import teli.driver as td

Requires: pip install teli  (or PYTHONPATH pointing to the teli source tree)
"""
from teli.driver import (  # noqa: F401
    connect,
    check_updates,
    send,
    status,
    list_session_names,
    stop,
    daemon_running_by_pid,
    add_handler,
)
