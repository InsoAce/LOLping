"""Pure geometry helpers. All rectangles use physical desktop coordinates."""
import math


def default_positions(slots):
    if slots <= 5:
        return [[0.17, 0.19 + i * 0.11] for i in range(slots)]
    columns = (slots + 9) // 10
    rows = min(slots, 10)
    gap = min(0.14, 0.70 / max(1, columns - 1))
    return [[0.17 + (i // rows) * gap, 0.14 + (i % rows) * 0.74 / max(1, rows-1)]
            for i in range(slots)]


def valid_positions(value, slots):
    return (isinstance(value, list) and len(value) == slots and
            all(isinstance(p, (list, tuple)) and len(p) == 2 and
                all(isinstance(v, (int, float)) and not isinstance(v, bool) and
                    math.isfinite(v) and 0 <= v <= 1 for v in p) for p in value))


def load_layouts(saved):
    if valid_positions(saved, 5):
        return {'5': saved}  # Migrate the original five-button calibration.
    layouts = {}
    if isinstance(saved, dict) and saved.get('version') == 2 and isinstance(saved.get('layouts'), dict):
        for key, positions in saved['layouts'].items():
            if str(key).isdigit() and int(key) >= 5 and valid_positions(positions, int(key)):
                layouts[str(int(key))] = positions
    return layouts


def button_size(width, height, slots):
    rows = min(slots, 10)
    bh = max(34, round(height * 0.042))
    if slots > 5:
        bh = min(bh, max(24, int(height * 0.74 / max(1, rows-1)) - 3))
    return max(122, round(width * 0.09)), bh


def intersection(a, b):
    rect = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    return rect if rect[2] > rect[0] and rect[3] > rect[1] else None


def place_button(client, position, size, monitors):
    """Hide offscreen slots; keep partially visible buttons inside one visible client area.

    A negative desktop coordinate is valid on a monitor left/above the primary.
    Monitor gaps must never be treated as visible desktop space.
    """
    x, y, width, height = client
    bw, bh = size
    px = max(x, min(x+width-bw, x+round(position[0]*width)))
    py = max(y, min(y+height-bh, y+round(position[1]*height)))
    desired = (px, py, px+bw, py+bh)
    candidates = []
    for monitor in monitors:
        visible = intersection((x, y, x+width, y+height), monitor)
        if not visible or visible[2]-visible[0] < bw or visible[3]-visible[1] < bh:
            continue
        overlap = intersection(desired, visible)
        if not overlap:
            continue
        area = (overlap[2]-overlap[0]) * (overlap[3]-overlap[1])
        candidates.append((area, visible))
    if not candidates:
        return None
    _, visible = max(candidates, key=lambda item: item[0])
    return (max(visible[0], min(visible[2]-bw, px)),
            max(visible[1], min(visible[3]-bh, py)), bw, bh)
