"""Analyze vent_map.png to find exact center coordinates of each blue duct line.

Strategy: The duct lines are thin (12px border + 6px blue = 18px total).
Room fills are wide areas. We detect duct lines by finding NARROW clusters
of colored pixels in each scan line, excluding known room fill colors.

We also look at ALL non-background pixels (alpha>0, not pure white/black)
and use the known vent_path coordinates from gen_vent_map.py to search
in precise regions.

Usage: python tools/find_duct_centers.py
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from PIL import Image

IMG = os.path.join(os.path.dirname(__file__), "..", "assets", "cameras", "vent_map.png")

img = Image.open(IMG).convert("RGBA")
arr = np.array(img)
W, H = img.size
print(f"Image: {W}x{H}")

r, g, b, a = arr[:,:,0].astype(int), arr[:,:,1].astype(int), arr[:,:,2].astype(int), arr[:,:,3].astype(int)

# --- Comprehensive color sampling along ALL expected duct lines ---
VENT_LINES = {
    "TOP_HORIZONTAL":    {"axis": "h", "y_nom": 40,   "x_range": (40, 1266)},
    "LEFT_VERTICAL":     {"axis": "v", "x_nom": 40,   "y_range": (40, 650)},
    "LEFT_BRANCH":       {"axis": "h", "y_nom": 400,  "x_range": (40, 140)},
    "CENTER_VERT_STUB":  {"axis": "v", "x_nom": 760,  "y_range": (40, 110)},
    "RIGHT_TOP_VERT":    {"axis": "v", "x_nom": 1266, "y_range": (40, 290)},
    "RIGHT_HORIZONTAL":  {"axis": "h", "y_nom": 290,  "x_range": (950, 1266)},
    "RIGHT_MID_VERT":    {"axis": "v", "x_nom": 950,  "y_range": (290, 650)},
    "MIDDLE_HORIZONTAL": {"axis": "h", "y_nom": 650,  "x_range": (40, 950)},
    "RIGHT_BOT_VERT":    {"axis": "v", "x_nom": 950,  "y_range": (650, 1060)},
    "BOT_HORIZONTAL":    {"axis": "h", "y_nom": 1060, "x_range": (40, 950)},
}

# For each line, scan a ±30px band and find the row/col with the most
# non-background pixels that are part of a NARROW cluster
print("\n" + "="*70)
print("DETAILED SCAN: Finding narrow duct line clusters")
print("="*70)

results = {}

for name, info in VENT_LINES.items():
    if info["axis"] == "h":
        y_nom = info["y_nom"]
        x0, x1 = info["x_range"]
        band = 30
        y_lo = max(0, y_nom - band)
        y_hi = min(H, y_nom + band)

        # For each row, find non-white colored pixels in x range
        # and check if they form a narrow cluster
        best_score = 0
        best_y = y_nom
        best_info = None

        for y in range(y_lo, y_hi):
            # Get all non-transparent, non-pure-white pixels in range
            row_r = r[y, x0:x1+1]
            row_g = g[y, x0:x1+1]
            row_b = b[y, x0:x1+1]
            row_a = a[y, x0:x1+1]

            # Colored = alpha>0, not pure white (255,255,255), not pure black (0,0,0)
            is_colored = (
                (row_a > 0) &
                ~((row_r > 250) & (row_g > 250) & (row_b > 250)) &
                ~((row_r < 5) & (row_g < 5) & (row_b < 5))
            )

            colored_xs = np.where(is_colored)[0]
            if len(colored_xs) < 3:
                continue

            # Find clusters (contiguous groups)
            gaps = np.diff(colored_xs)
            splits = np.where(gaps > 3)[0]  # cluster gap > 3px

            clusters = []
            start = 0
            for s in splits:
                cluster = colored_xs[start:s+1]
                clusters.append((cluster[0] + x0, cluster[-1] + x0, len(cluster)))
                start = s + 1
            cluster = colored_xs[start:]
            clusters.append((cluster[0] + x0, cluster[-1] + x0, len(cluster)))

            # Score: prefer narrow clusters (duct line ~18px) over wide ones (room fill)
            for c_x0, c_x1, c_len in clusters:
                width = c_x1 - c_x0 + 1
                if width < 25:  # Narrow = likely duct line
                    score = c_len * 10  # Bonus for narrow cluster
                elif width < 50:
                    score = c_len * 3
                else:
                    score = c_len  # Wide = room fill, no bonus

                if score > best_score:
                    best_score = score
                    best_y = y
                    best_info = (c_x0, c_x1, width, c_len)

        if best_info:
            cx0, cx1, w, cnt = best_info
            center_x = (cx0 + cx1) // 2
            results[name] = {"center": best_y, "range": (cx0, cx1), "axis": "h"}
            print(f"  {name:20s}  Y={best_y:4d}  X=[{cx0}..{cx1}] w={w:2d}  (nominal Y={y_nom})")
        else:
            # Fallback: just count colored pixels per row
            row_counts = []
            for y in range(y_lo, y_hi):
                row_r = r[y, x0:x1+1]
                row_g = g[y, x0:x1+1]
                row_b = b[y, x0:x1+1]
                row_a = a[y, x0:x1+1]
                is_colored = (row_a > 0) & ~((row_r > 250) & (row_g > 250) & (row_b > 250)) & ~((row_r < 5) & (row_g < 5) & (row_b < 5))
                row_counts.append((int(is_colored.sum()), y))
            row_counts.sort(reverse=True)
            best_y = row_counts[0][1]
            results[name] = {"center": best_y, "range": (x0, x1), "axis": "h"}
            print(f"  {name:20s}  Y={best_y:4d}  (fallback) (nominal Y={y_nom})")

    else:  # vertical
        x_nom = info["x_nom"]
        y0, y1 = info["y_range"]
        band = 30
        x_lo = max(0, x_nom - band)
        x_hi = min(W, x_nom + band)

        best_score = 0
        best_x = x_nom
        best_info = None

        for x in range(x_lo, x_hi):
            col_r = r[y0:y1+1, x]
            col_g = g[y0:y1+1, x]
            col_b = b[y0:y1+1, x]
            col_a = a[y0:y1+1, x]

            is_colored = (
                (col_a > 0) &
                ~((col_r > 250) & (col_g > 250) & (col_b > 250)) &
                ~((col_r < 5) & (col_g < 5) & (col_b < 5))
            )

            colored_ys = np.where(is_colored)[0]
            if len(colored_ys) < 3:
                continue

            gaps = np.diff(colored_ys)
            splits = np.where(gaps > 3)[0]

            clusters = []
            start = 0
            for s in splits:
                cluster = colored_ys[start:s+1]
                clusters.append((cluster[0] + y0, cluster[-1] + y0, len(cluster)))
                start = s + 1
            cluster = colored_ys[start:]
            clusters.append((cluster[0] + y0, cluster[-1] + y0, len(cluster)))

            for c_y0, c_y1, c_len in clusters:
                height = c_y1 - c_y0 + 1
                if height < 25:
                    score = c_len * 10
                elif height < 50:
                    score = c_len * 3
                else:
                    score = c_len

                if score > best_score:
                    best_score = score
                    best_x = x
                    best_info = (c_y0, c_y1, height, c_len)

        if best_info:
            cy0, cy1, h, cnt = best_info
            center_y = (cy0 + cy1) // 2
            results[name] = {"center": best_x, "range": (cy0, cy1), "axis": "v"}
            print(f"  {name:20s}  X={best_x:4d}  Y=[{cy0}..{cy1}] h={h:2d}  (nominal X={x_nom})")
        else:
            col_counts = []
            for x in range(x_lo, x_hi):
                col_r = r[y0:y1+1, x]
                col_g = g[y0:y1+1, x]
                col_b = b[y0:y1+1, x]
                col_a = a[y0:y1+1, x]
                is_colored = (col_a > 0) & ~((col_r > 250) & (col_g > 250) & (col_b > 250)) & ~((col_r < 5) & (col_g < 5) & (col_b < 5))
                col_counts.append((int(is_colored.sum()), x))
            col_counts.sort(reverse=True)
            best_x = col_counts[0][1]
            results[name] = {"center": best_x, "range": (y0, y1), "axis": "v"}
            print(f"  {name:20s}  X={best_x:4d}  (fallback) (nominal X={x_nom})")

print("\n" + "="*70)
print("RESULTS:")
print("="*70)
for name, r_info in results.items():
    if r_info["axis"] == "h":
        print(f"  {name:20s}  Y = {r_info['center']:4d}  (X: {r_info['range'][0]}..{r_info['range'][1]})")
    else:
        print(f"  {name:20s}  X = {r_info['center']:4d}  (Y: {r_info['range'][0]}..{r_info['range'][1]})")

print("\n" + "="*70)
print("COPY-PASTE:")
print("="*70)
for name, r_info in results.items():
    if r_info["axis"] == "h":
        print(f"{name}_Y = {r_info['center']}")
    else:
        print(f"{name}_X = {r_info['center']}")
