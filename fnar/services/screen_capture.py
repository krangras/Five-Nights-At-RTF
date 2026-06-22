"""Фоновый захват области экрана и проекция изображения на ноутбук в офисе."""

import threading
import time
import pygame
import numpy as np
import cv2
import mss


class ScreenCapture:
    """Фоновый захват экрана с перспективной трансформацией под экран ноутбука."""

    # 4 угла экрана ноутбука в оригинальном изображении офиса (1915x821)
    _LAPTOP_CORNERS_ORIG = np.float32([
        [423, 497],  # top-left
        [566, 477],  # top-right
        [589, 570],  # bottom-right
        [446, 599],  # bottom-left
    ])

    def __init__(self, scale: float):
        """scale — масштаб офисного изображения (screen_h / 821).

        Args:
            scale: Параметр типа ``float``, используемый методом ``__init__``.

        Returns:
            Результат выполнения метода; для процедурных методов — ``None``."""
        self.scale = scale
        self.surface: pygame.Surface | None = None
        self._lock = threading.Lock()
        self._running = True
        self._interval = 0.5  # секунды между захватами

        # dst-углы в масштабированных координатах
        dst = self._LAPTOP_CORNERS_ORIG * scale

        # Bounding box dst-углов — размер выходного изображения warpa
        x_min, y_min = dst.min(axis=0).astype(int)
        x_max, y_max = dst.max(axis=0).astype(int)
        self.out_w = int(x_max - x_min)
        self.out_h = int(y_max - y_min)
        self.blit_origin = (x_min, y_min)  # откуда начинать blit (в координатах изображения)

        # Src-углы для warpa (прямоугольник out_w x out_h)
        self._src_corners = np.float32([
            [0, 0],
            [self.out_w, 0],
            [self.out_w, self.out_h],
            [0, self.out_h],
        ])

        # Dst-углы сдвинуты так, что (x_min, y_min) -> (0, 0)
        self._dst_corners = (dst - np.array([x_min, y_min])).astype(np.float32)

        # Precompute perspective matrix (неизменная)
        self._M = cv2.getPerspectiveTransform(self._src_corners, self._dst_corners)

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def _capture_loop(self):
        """В фоне считывает экран и обновляет последний кадр для проекции ноутбука."""
        sct = mss.mss()
        monitor = sct.monitors[1]  # primary monitor
        while self._running:
            try:
                shot = sct.grab(monitor)
                frame = np.array(shot)[:, :, :3]  # BGRA -> BGR

                # Perspective warp
                warped = cv2.warpPerspective(frame, self._M, (self.out_w, self.out_h))

                # BGR -> RGB -> pygame Surface
                rgb = cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)
                surf = pygame.image.frombuffer(rgb.tobytes(), (self.out_w, self.out_h), "RGB")

                with self._lock:
                    self.surface = surf

            except Exception:
                pass

            time.sleep(self._interval)

    def stop(self):
        """Останавливает фоновый поток захвата экрана."""
        self._running = False
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
