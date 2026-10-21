"""
hypr-doctor: Static analysis linter, duplicate keybinding detector, and autostart auditor for Hyprland.
"""

__version__ = "0.1.0"

from .doctor import HyprDoctor, audit_config

__all__ = ["HyprDoctor", "audit_config", "__version__"]
