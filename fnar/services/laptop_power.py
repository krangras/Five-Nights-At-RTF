"""Laptop power-state timing and phase mapping.

The model stores the state/timer, the presenter changes the state, and the view
only asks this module which visual phase should be drawn.
"""

from __future__ import annotations

LAPTOP_BOOT_TICKS = 180
LAPTOP_SHUTDOWN_TICKS = 150


def get_laptop_power_sequence(power_state: str, power_timer: int) -> tuple[str, float]:
    if power_state == "BOOTING":
        progress = max(0.0, min(1.0, 1.0 - power_timer / LAPTOP_BOOT_TICKS))
        if progress < 0.18:
            return "boot_wake", progress / 0.18
        if progress < 0.62:
            return "boot_post", (progress - 0.18) / 0.44
        return "boot_loading", (progress - 0.62) / 0.38

    if power_state == "SHUTTING_DOWN":
        progress = max(0.0, min(1.0, 1.0 - power_timer / LAPTOP_SHUTDOWN_TICKS))
        if progress < 0.48:
            return "shutdown_msg", progress / 0.48
        return "shutdown_fade", (progress - 0.48) / 0.52

    return "off_idle", 0.0
