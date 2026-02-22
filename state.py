"""
Application state — configuration constants, FingerSmoother, and HandState.
"""
import math
from collections import deque

# ==============================
# Carousel layout
# ==============================
CARD_COUNT = 7
CARD_WIDTH = 280
CARD_HEIGHT = 280
CARD_SPACING = 50
ROW_BASE_SPACING = CARD_HEIGHT + 80

CATEGORIES = [
    ["Mail", "Music", "Browser", "Messages", "Calendar", "Maps", "Camera"],
    ["Photos", "Notes", "Reminders", "Clock", "Weather", "Stocks", "Sand"],
    ["YouTube", "Netflix", "Twitch", "Spotify", "Podcasts", "Books", "Games"],
]
NUM_CATEGORIES = len(CATEGORIES)

APP_COLORS = {
    "Mail": (74, 144, 226),   "Music": (252, 61, 86),    "Safari": (35, 142, 250),
    "Messages": (76, 217, 100), "Calendar": (252, 61, 57), "Maps": (89, 199, 249),
    "Camera": (138, 138, 142), "Photos": (252, 203, 47),  "Notes": (255, 214, 10),
    "Reminders": (255, 69, 58), "Clock": (30, 30, 30),    "Weather": (99, 204, 250),
    "Stocks": (30, 30, 30),    "Sand": (252, 61, 86),     "YouTube": (255, 0, 0),
    "Netflix": (229, 9, 20),   "Twitch": (145, 70, 255),  "Spotify": (30, 215, 96),
    "Podcasts": (146, 72, 223), "Books": (255, 124, 45),  "Games": (255, 45, 85),
    "Browser": (35, 142, 250), "Sand": (255, 200, 100),
}

WINDOW_WIDTH = 1600
WINDOW_HEIGHT = 900


# ==============================
# Finger smoother
# ==============================
class FingerSmoother:
    """One-pole exponential smoothing — simple, no jitter."""
    def __init__(self, alpha=0.08):
        self._a = alpha  # lower = heavier smoothing
        self._tx = None
        self._ty = None
        self._ix = None
        self._iy = None

    def update(self, thumb_pos, index_pos):
        a = self._a
        if self._tx is None:
            self._tx, self._ty = thumb_pos
            self._ix, self._iy = index_pos
        else:
            self._tx += a * (thumb_pos[0] - self._tx)
            self._ty += a * (thumb_pos[1] - self._ty)
            self._ix += a * (index_pos[0] - self._ix)
            self._iy += a * (index_pos[1] - self._iy)
        return (self._tx, self._ty), (self._ix, self._iy)

    def reset(self):
        self._tx = None
        self._ty = None
        self._ix = None
        self._iy = None


class PinchSmoother:
    """Smooths pinch coordinates for scroll/interaction."""
    def __init__(self, alpha=0.12):
        self._a = alpha
        self._x = None
        self._y = None

    def update(self, x, y):
        if self._x is None:
            self._x, self._y = x, y
        else:
            self._x += self._a * (x - self._x)
            self._y += self._a * (y - self._y)
        return self._x, self._y

    def reset(self):
        self._x = None
        self._y = None


class PinchSmoother:
    """Smooths pinch coordinates for scroll/interaction."""
    def __init__(self, alpha=0.12):
        self._a = alpha
        self._x = None
        self._y = None

    def update(self, x, y):
        if self._x is None:
            self._x, self._y = x, y
        else:
            self._x += self._a * (x - self._x)
            self._y += self._a * (y - self._y)
        return self._x, self._y

    def reset(self):
        self._x = None
        self._y = None


# ==============================
# Hand state
# ==============================
class HandState:
    def __init__(self):
        # scroll offsets
        self.card_offset = 0.0
        self.category_offset = 0.0
        self.smooth_card_offset = 0.0
        self.smooth_category_offset = 0.0
        self.scroll_smoothing = 0.18        # smooth fluid catch-up
        self.scroll_gain = 4.0              # balanced sensitivity

        # pinch state
        self.is_pinching = False
        self.last_pinch_x = None
        self.last_pinch_y = None
        self.pinch_start_pos = None
        self.movement_threshold = 40        # dead zone before scroll starts
        self.pinch_threshold = 0.04
        self.pinch_prev = False
        self.last_pinch_time = 0
        self.double_pinch_window = 0.4
        self.pinch_hold_start = 0
        self.scroll_unlocked = False
        self.pinch_hold_delay = 0.20

        # selection
        self.selected_card = None
        self.selected_category = None
        self.zoom_progress = 0.0
        self.zoom_target = 0.0
        self.finger_smoother = FingerSmoother()
        self.pinch_smoother = PinchSmoother()
        self.pinch_smoother = PinchSmoother()

        # zoom wheel
        self.wheel_active = False
        self.wheel_angle = math.pi
        self.last_finger_angle = None
        self.wheel_center_x = 0
        self.wheel_center_y = 0
        self.wheel_radius = 110
        self.gui_scale = 1.00
        self.gui_scale_min = 0.60
        self.gui_scale_max = 1.80
        self.gui_scale_sensitivity = 0.55

        # misc
        self.current_fps = 0.0

    def reset_pinch(self):
        self.pinch_smoother.reset()
        self.is_pinching = False
        self.last_pinch_x = None
        self.last_pinch_y = None
        self.pinch_start_pos = None
        self.scroll_unlocked = False