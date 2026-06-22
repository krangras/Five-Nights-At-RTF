"""Laptop power-state timing and phase mapping.

The model stores the state/timer, the presenter changes the state, and the view
only asks this module which visual phase should be drawn.
"""

from __future__ import annotations

LAPTOP_BOOT_TICKS = 180
LAPTOP_SHUTDOWN_TICKS = 150
PROGRESS_MIN = 0.0
PROGRESS_MAX = 1.0
BOOT_WAKE_END = 0.18
BOOT_POST_END = 0.62
BOOT_POST_DURATION = BOOT_POST_END - BOOT_WAKE_END
BOOT_LOADING_DURATION = PROGRESS_MAX - BOOT_POST_END
SHUTDOWN_MESSAGE_END = 0.48
SHUTDOWN_FADE_DURATION = PROGRESS_MAX - SHUTDOWN_MESSAGE_END
PHASE_BOOT_WAKE = "boot_wake"
PHASE_BOOT_POST = "boot_post"
PHASE_BOOT_LOADING = "boot_loading"
PHASE_SHUTDOWN_MESSAGE = "shutdown_msg"
PHASE_SHUTDOWN_FADE = "shutdown_fade"
PHASE_OFF_IDLE = "off_idle"
STATE_BOOTING = "BOOTING"
STATE_SHUTTING_DOWN = "SHUTTING_DOWN"


def get_laptop_power_sequence(power_state: str, power_timer: int) -> tuple[str, float]:
    if power_state == STATE_BOOTING:
        progress = max(PROGRESS_MIN, min(PROGRESS_MAX, PROGRESS_MAX - power_timer / LAPTOP_BOOT_TICKS))
        if progress < BOOT_WAKE_END:
            return PHASE_BOOT_WAKE, progress / BOOT_WAKE_END
        if progress < BOOT_POST_END:
            return PHASE_BOOT_POST, (progress - BOOT_WAKE_END) / BOOT_POST_DURATION
        return PHASE_BOOT_LOADING, (progress - BOOT_POST_END) / BOOT_LOADING_DURATION

    if power_state == STATE_SHUTTING_DOWN:
        progress = max(PROGRESS_MIN, min(PROGRESS_MAX, PROGRESS_MAX - power_timer / LAPTOP_SHUTDOWN_TICKS))
        if progress < SHUTDOWN_MESSAGE_END:
            return PHASE_SHUTDOWN_MESSAGE, progress / SHUTDOWN_MESSAGE_END
        return PHASE_SHUTDOWN_FADE, (progress - SHUTDOWN_MESSAGE_END) / SHUTDOWN_FADE_DURATION

    return PHASE_OFF_IDLE, PROGRESS_MIN
