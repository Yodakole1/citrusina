"""Where things are on the wheel. No Qt in here, so the geometry can be tested on its own.

Angles are degrees clockwise from 12 o'clock, the way the screen reads.
"""
import math

R_OUT = 160
R_IN = 66
R_HUB = 54
GAP = 6          # px between petals, the same at every radius so the gaps stay parallel
CORNER = 12
REACH = 36       # a little past the rim still counts, so a quick flick outward lands
MAX_PETALS = 10
HUB = "hub"


def step(n):
    return 360 / n


def span(i, n):
    """Start and end angle of petal i of n. Petal 0 sits on top and they run clockwise."""
    mid = i * step(n)
    return mid - step(n) / 2, mid + step(n) / 2


def half_gap(r, gap=GAP):
    """The angle a gap of `gap` px takes up on each side of a seam at radius r."""
    return math.degrees(math.asin(min(1.0, gap / 2 / r)))


def point(angle, r):
    """Offset from the center for an angle and radius, with y pointing down."""
    a = math.radians(angle)
    return r * math.sin(a), -r * math.cos(a)


def angle_of(dx, dy):
    return math.degrees(math.atan2(dx, -dy)) % 360


def hit(dx, dy, n):
    """The petal under an offset from the center, HUB, or None."""
    d = math.hypot(dx, dy)
    if d <= R_HUB + 4:
        return HUB
    if n == 0 or d > R_OUT + REACH:
        return None
    return int((angle_of(dx, dy) + step(n) / 2) // step(n)) % n


def place(x, y, left, top, width, height, margin=R_OUT + 20):
    """Move the center in from the screen edges so no petal is cut off."""
    def clamp(v, lo, size):
        if size < 2 * margin:
            return lo + size / 2
        return min(max(v, lo + margin), lo + size - margin)
    return clamp(x, left, width), clamp(y, top, height)


def label_size(text, n, base=14, smallest=10, char_width=0.72):
    """A font size that keeps a label inside its petal.

    Bold caps with letter spacing come out at about char_width of the font size per character.
    """
    room = 2 * math.pi * (R_IN + R_OUT) / 2 / max(n, 1) * 0.78 if n > 1 else R_OUT
    room = min(room, (R_OUT - R_IN) * 1.6)
    fit = room / max(len(text), 1) / char_width
    return max(smallest, min(base, int(fit)))
