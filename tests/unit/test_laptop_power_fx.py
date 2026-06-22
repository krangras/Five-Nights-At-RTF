import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fnar.services.laptop_power import get_laptop_power_sequence


def test_boot_sequence_advances_through_all_visual_phases():
    assert get_laptop_power_sequence("BOOTING", 180)[0] == "boot_wake"
    assert get_laptop_power_sequence("BOOTING", 130)[0] == "boot_post"
    assert get_laptop_power_sequence("BOOTING", 40)[0] == "boot_loading"


def test_shutdown_sequence_advances_to_fade_out():
    assert get_laptop_power_sequence("SHUTTING_DOWN", 150)[0] == "shutdown_msg"
    assert get_laptop_power_sequence("SHUTTING_DOWN", 60)[0] == "shutdown_fade"


def test_off_state_stays_idle():
    phase, progress = get_laptop_power_sequence("OFF", 0)
    assert phase == "off_idle"
    assert progress == 0.0
