"""Генерация vent_map.png — прозрачный оверлей с белыми контурами
комнат и синими duct-линиями с белой обводкой.

Запуск:  cd tools && python gen_vent_map.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageDraw
import numpy as np

CAMERA_MAP = os.path.join(os.path.dirname(__file__), "..", "assets", "cameras", "camera_map.png")
OUTPUT = os.path.join(os.path.dirname(__file__), "..", "assets", "cameras", "vent_map.png")

cam = Image.open(CAMERA_MAP).convert("RGBA")
W, H = cam.size
print(f"camera_map: {W}x{H}")

# ── 1. Извлечь белые контуры комнат из camera_map ───────────────────────
cam_arr = np.array(cam)
r, g, b, a = cam_arr[:, :, 0], cam_arr[:, :, 1], cam_arr[:, :, 2], cam_arr[:, :, 3]
brightness = 0.299 * r.astype(float) + 0.587 * g.astype(float) + 0.114 * b.astype(float)
is_outline = brightness > 140

out = np.zeros((H, W, 4), dtype=np.uint8)
out[is_outline] = [255, 255, 255, 255]

# ── 2. Duct-линии (по скриншоту reference, масштаб 1306x1204) ──────────
BLUE = (0, 90, 200, 255)
WHITE_BORD = (180, 190, 200, 200)
BORDER_W = 12
VENT_W = 6

# Пути duct-линий: периметр здания + коридоры
vent_paths = [
    # Верхний горизонт — полная ширина
    [(40, 40), (1266, 40)],
    # Левый вертикаль — от верха до среднего коридора
    [(40, 40), (40, 650)],
    # Левая горизонтальная ветка — короткая, вправо от левой стены
    [(40, 400), (140, 400)],
    # Центральный вертикальный стык — от верхней линии вниз
    [(760, 40), (760, 110)],
    # Правый верхний вертикаль — от верха вниз
    [(1266, 40), (1266, 290)],
    # Правое горизонтальное соединение
    [(950, 290), (1266, 290)],
    # Правый средний вертикаль — вниз к среднему коридору
    [(950, 290), (950, 650)],
    # Средний горизонтальный коридор — от левого к правому
    [(40, 650), (950, 650)],
    # Правый нижний вертикаль — от среднего к нижнему
    [(950, 650), (950, 1060)],
    # Нижний горизонтальный коридор — от правого влево
    [(40, 1060), (950, 1060)],
]

# ── 3. Рисуем ────────────────────────────────────────────────────────────
img = Image.fromarray(out, "RGBA")
d = ImageDraw.Draw(img)

# Белая обводка (шире), потом синяя поверх (уже)
for path in vent_paths:
    d.line(path, fill=WHITE_BORD, width=BORDER_W)
for path in vent_paths:
    d.line(path, fill=BLUE, width=VENT_W)

img.save(OUTPUT)
print(f"vent_map.png {W}x{H} saved")
