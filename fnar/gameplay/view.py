"""Gameplay view facade assembled from focused rendering components."""

from .camera_renderer import CameraRendererMixin
from .laptop_projection import LaptopProjectionMixin
from .laptop_renderer import LaptopRendererMixin
from .office_renderer import OfficeRendererMixin
from .ui_hitboxes import UiHitboxesMixin
from .view_assets import ViewAssetsMixin


class GameView(
    ViewAssetsMixin,
    LaptopProjectionMixin,
    UiHitboxesMixin,
    LaptopRendererMixin,
    CameraRendererMixin,
    OfficeRendererMixin,
):
    """Render gameplay while delegating each visual subsystem to one component."""
