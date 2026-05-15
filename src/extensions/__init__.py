"""
Extension discovery and loading system for ITL Attestation Platform.

Extensions provide modular functionality on top of the core attestation service.
Extensions can contribute:
- REST API routes
- Database models
- CLI commands
- Background tasks

Built-in extensions are discovered automatically from extensions.builtin.
External extensions can be registered via entry_points.
"""

from typing import Dict
from .base import AttestationExtension

_registry: Dict[str, AttestationExtension] = {}


def discover_extensions() -> Dict[str, AttestationExtension]:
    """
    Auto-discover and load extensions.
    
    Discovery order:
    1. Built-in extensions from extensions.builtin.*
    2. External extensions from entry_points(group="attestation_extensions")
    
    Returns:
        Dictionary mapping extension name to extension instance
    """
    global _registry
    
    if _registry:
        return _registry
    
    # Load built-in extensions
    _load_builtin_extensions()
    
    # Load external extensions via entry points
    _load_external_extensions()
    
    return _registry


def _load_builtin_extensions() -> None:
    """Load built-in extensions from extensions.builtin.*"""
    import importlib
    import pkgutil
    from . import builtin
    
    for importer, modname, ispkg in pkgutil.iter_modules(builtin.__path__, "extensions.builtin."):
        if ispkg:
            try:
                # Import extension.py from package
                mod = importlib.import_module(f"{modname}.extension")
                
                # Find AttestationExtension subclass
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, AttestationExtension)
                        and attr is not AttestationExtension
                    ):
                        instance = attr()
                        _registry[instance.name] = instance
                        print(f"[Extension] Loaded built-in: {instance.name} v{instance.version}")
                        break
            except Exception as e:
                print(f"[Extension] Failed to load {modname}: {e}")


def _load_external_extensions() -> None:
    """Load external extensions via entry_points."""
    try:
        from importlib.metadata import entry_points
        
        # Get entry points for group "attestation_extensions"
        eps = entry_points()
        if hasattr(eps, "select"):  # Python 3.10+
            ext_eps = eps.select(group="attestation_extensions")
        else:  # Python 3.9
            ext_eps = eps.get("attestation_extensions", [])
        
        for ep in ext_eps:
            try:
                extension_class = ep.load()
                instance = extension_class()
                _registry[instance.name] = instance
                print(f"[Extension] Loaded external: {instance.name} v{instance.version}")
            except Exception as e:
                print(f"[Extension] Failed to load {ep.name}: {e}")
    except ImportError:
        pass  # importlib.metadata not available (Python < 3.8)


def get_extension(name: str) -> AttestationExtension | None:
    """
    Get extension by name.
    
    Args:
        name: Extension identifier (snake_case)
    
    Returns:
        Extension instance or None if not found
    """
    return _registry.get(name)


def list_extensions() -> Dict[str, AttestationExtension]:
    """
    Get all registered extensions.
    
    Returns:
        Dictionary mapping extension name to extension instance
    """
    return _registry.copy()


__all__ = [
    "AttestationExtension",
    "discover_extensions",
    "get_extension",
    "list_extensions",
]
