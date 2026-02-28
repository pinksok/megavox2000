"""Service registry and dispatcher."""

import json as json_mod
import os

import state

SERVICE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "service.json")

_registry = {}


def register(module):
    """Register a service module."""
    _registry[module.SERVICE_NAME] = module


def get_service():
    """Return the currently active service module."""
    return _registry.get(state.active_service)


def get_all_services():
    """Return dict of all registered services."""
    return _registry


def load_active_service():
    """Load persisted service choice, default to 'youtube'."""
    try:
        if os.path.exists(SERVICE_FILE):
            with open(SERVICE_FILE) as f:
                data = json_mod.load(f)
                name = data.get("active", "youtube")
                if name in _registry:
                    state.active_service = name
                    return
    except Exception:
        pass
    state.active_service = "youtube"


def set_active_service(name):
    """Switch active service and persist."""
    if name not in _registry:
        return False
    state.active_service = name
    try:
        with open(SERVICE_FILE, "w") as f:
            json_mod.dump({"active": name}, f)
    except Exception:
        pass
    return True
