"""
Renderer — all Pygame drawing: app icons, card rows, zoom wheel, hand HUD, status bar.
"""

import math
import pygame

from state import APP_COLORS, CATEGORIES, CARD_COUNT


# ==============================
# Font cache
# ==============================
_font_cache: dict[int, pygame.font.Font] = {}


def get_font(size: int) -> pygame.font.Font:
    if size not in _font_cache:
        _font_cache[size] = pygame.font.Font(None, size)
    return _font_cache[size]


# Pre-rendered text surface cache: (text, size, color) -> Surface
_text_cache: dict[tuple, pygame.Surface] = {}


def _render_text(text: str, size: int, color: tuple) -> pygame.Surface:
    key = (text, size, color)
    if key not in _text_cache:
        _text_cache[key] = get_font(size).render(text, True, color)
    return _text_cache[key]


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


# ==============================
# App icon
# ==============================
# Pre-computed brightened app colors
_app_color_cache: dict[str, tuple] = {}

# Card surface cache: (app_name, w, h, is_selected) -> Surface
# Rendered at exact target size for crisp text — no scaling artifacts.
_card_surface_cache: dict[tuple, pygame.Surface] = {}
_CARD_CACHE_MAX = 60


def _get_card_surface(app_name, w, h, gui_scale, is_selected):
    """Render a card at the exact requested size (crisp text, no scaling)."""
    key = (app_name, w, h, is_selected)
    if key in _card_surface_cache:
        return _card_surface_cache[key]

    # Evict oldest entries if cache is full
    if len(_card_surface_cache) >= _CARD_CACHE_MAX:
        for old_key in list(_card_surface_cache.keys())[:20]:
            del _card_surface_cache[old_key]

    br = max(12, int(50 * gui_scale))
    pad = int(6 * gui_scale) + max(2, int(8 * gui_scale)) if is_selected else 0
    sw, sh = w + pad * 2, h + pad * 2

    surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
    cx, cy = sw // 2, sh // 2

    if app_name not in _app_color_cache:
        base_color = APP_COLORS.get(app_name, (100, 100, 100))
        _app_color_cache[app_name] = tuple(min(255, int(base_color[i] * 1.2)) for i in range(3))
    color = _app_color_cache[app_name]

    card_rect = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
    pygame.draw.rect(surf, color, card_rect, border_radius=br)

    if is_selected:
        sel = pygame.Rect(card_rect.x - int(6 * gui_scale), card_rect.y - int(6 * gui_scale),
                          card_rect.width + int(12 * gui_scale), card_rect.height + int(12 * gui_scale))
        pygame.draw.rect(surf, (255, 255, 255), sel,
                         width=max(2, int(8 * gui_scale)), border_radius=br)

    icon_size = max(24, int(120 * gui_scale))
    icon_img = _render_text(app_name[0], icon_size, (255, 255, 255))
    surf.blit(icon_img, icon_img.get_rect(center=(cx, cy - int(20 * gui_scale))))

    text_size = max(12, int(36 * gui_scale))
    text_img = _render_text(app_name, text_size, (255, 255, 255))
    surf.blit(text_img, text_img.get_rect(center=(cx, cy + int(60 * gui_scale))))

    _card_surface_cache[key] = surf
    return surf


def draw_app_icon(surface, app_name, x, y, base_w, base_h,
                  is_selected=False, zoom_scale=1.0, gui_scale=1.0):
    w = int(base_w * gui_scale)
    h = int(base_h * gui_scale)
    if is_selected:
        w = int(w * zoom_scale)
        h = int(h * zoom_scale)

    card_surf = _get_card_surface(app_name, w, h, gui_scale, is_selected)
    cw, ch = card_surf.get_size()
    surface.blit(card_surf, (x - cw // 2, y - ch // 2))

    rect = pygame.Rect(x - w // 2, y - h // 2, w, h)
    return rect


# ==============================
# Card row
# ==============================
def draw_cards(surface, center_x, center_y, card_offset, category_idx,
               selected_card, selected_category, zoom_progress,
               window_width, gui_scale, base_w, base_h, base_spacing):
    names = CATEGORIES[category_idx]
    rects = []
    stride = int(base_w * gui_scale) + int(base_spacing * gui_scale)
    first = max(0, int((-card_offset - window_width // 2) / stride) - 1)
    last = min(CARD_COUNT, int((-card_offset + window_width // 2) / stride) + 2)
    for i in range(first, last):
        x, y = round(center_x + i * stride + card_offset), round(center_y)
        if not (selected_card == i and selected_category == category_idx):
            rects.append((draw_app_icon(surface, names[i], x, y, base_w, base_h,
                                        False, 1.0, gui_scale), i, category_idx))
    for i in range(first, last):
        x, y = round(center_x + i * stride + card_offset), round(center_y)
        if selected_card == i and selected_category == category_idx:
            rects.append((draw_app_icon(surface, names[i], x, y, base_w, base_h,
                                        True, 1.0 + zoom_progress * 0.3, gui_scale), i, category_idx))
    return rects


# ==============================
# Zoom wheel overlay
# ==============================


def draw_wheel(surface, state, window_width, window_height):
    if not state.wheel_active:
        return
    s = state.gui_scale
    cx, cy = state.wheel_center_x, state.wheel_center_y
    r = int(state.wheel_radius * s)
    white = (255, 255, 255)
    # Simple wheel — two circles + pointer + label (no glow, no arc segments)
    pygame.draw.circle(surface, white, (cx, cy), r, max(1, int(4 * s)))
    pygame.draw.circle(surface, white, (cx, cy), r - int(20 * s), max(1, int(2 * s)))
    pl = r - int(30 * s)
    px = cx + int(pl * math.cos(state.wheel_angle))
    py = cy + int(pl * math.sin(state.wheel_angle))
    pygame.draw.line(surface, white, (cx, cy), (px, py), max(1, int(3 * s)))
    pygame.draw.circle(surface, white, (px, py), max(2, int(6 * s)))
    pygame.draw.circle(surface, white, (cx, cy), max(2, int(8 * s)))
    t = _render_text(f"GUI {state.gui_scale:.1f}x", max(18, int(40 * s)), white)
    tr = t.get_rect(center=(cx, cy + r + int(44 * s)))
    bg = pygame.Rect(tr.x - int(10 * s), tr.y - int(5 * s),
                     tr.width + int(20 * s), tr.height + int(10 * s))
    pygame.draw.rect(surface, (20, 20, 20), bg)
    pygame.draw.rect(surface, white, bg, max(1, int(2 * s)))
    surface.blit(t, tr)


# ==============================
# Skeleton thumbnail
# ==============================

# MediaPipe hand bone connections
_HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),        # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),        # index
    (0, 9), (9, 10), (10, 11), (11, 12),   # middle
    (0, 13), (13, 14), (14, 15), (15, 16), # ring
    (0, 17), (17, 18), (18, 19), (19, 20), # pinky
    (5, 9), (9, 13), (13, 17),             # palm knuckle bar
]

# Finger tip landmark indices, used to colour fingertips differently
_FINGERTIPS = {4, 8, 12, 16, 20}

_THUMB_COLOR  = (255, 180,  60)   # orange
_FINGER_COLOR = ( 80, 200, 255)   # cyan
_PALM_COLOR   = (160, 160, 200)   # muted purple-grey
_TIP_COLOR    = (255, 255, 100)   # bright yellow dots


def draw_skeleton_thumbnail(surface, landmarks, x=None, y=None,
                             w=220, h=165, window_width=1600, window_height=900,
                             margin=10):
    """
    Draw a skeleton-only hand thumbnail in the upper-right corner (or at x,y).

    landmarks — list of 21 _Landmark objects from HandTracker.latest(), or None.
    No camera image is drawn — just a black panel with coloured bones.
    """
    if x is None:
        x = window_width - w - margin
    if y is None:
        y = margin

    panel = pygame.Rect(x, y, w, h)

    # Semi-transparent background
    bg = pygame.Surface((w, h), pygame.SRCALPHA)
    bg.fill((10, 10, 18, 210))
    surface.blit(bg, (x, y))

    # Border
    pygame.draw.rect(surface, (70, 70, 100), panel, width=2, border_radius=8)

    # Label
    lbl = get_font(18).render("hand cam", True, (80, 80, 110))
    surface.blit(lbl, (x + 6, y + 4))

    if landmarks is None:
        msg = get_font(18).render("no hand", True, (70, 70, 90))
        surface.blit(msg, msg.get_rect(center=(x + w // 2, y + h // 2)))
        return

    # Map normalised landmark coords into the thumbnail rect.
    # Landmarks are already in [0..1] range (mirrored by OpenCV flip).
    pad = 18  # pixels of breathing room inside the panel

    def lm_xy(lm):
        px = x + pad + lm.x * (w - pad * 2)
        py = y + pad + lm.y * (h - pad * 2)
        return int(px), int(py)

    # Draw bones
    for a, b in _HAND_CONNECTIONS:
        pa, pb = lm_xy(landmarks[a]), lm_xy(landmarks[b])
        # Palm bar and thumb get a different tint
        if a in (5, 9, 13) and b in (9, 13, 17):
            color = _PALM_COLOR
        elif a <= 4 or b <= 4:
            color = _THUMB_COLOR
        else:
            color = _FINGER_COLOR
        pygame.draw.line(surface, color, pa, pb, 2)

    # Draw joint dots
    for i, lm in enumerate(landmarks):
        px, py = lm_xy(lm)
        if i in _FINGERTIPS:
            pygame.draw.circle(surface, _TIP_COLOR, (px, py), 4)
        elif i == 0:
            pygame.draw.circle(surface, _PALM_COLOR, (px, py), 4)
        else:
            pygame.draw.circle(surface, _FINGER_COLOR, (px, py), 2)
# ==============================
# Camera thumbnail (privacy — skeleton only, no video feed)
# ==============================
import cv2

_CAM_THUMB_W = 200
_CAM_THUMB_H = 150
_CAM_THUMB_MARGIN = 12


_cam_thumb_surf = None   # cached surface for camera thumbnail


def draw_camera_thumbnail(surface, frame, window_width, landmarks=None):
    """Privacy mode: black panel with white wireframe skeleton, no camera feed."""
    global _cam_thumb_surf
    x = window_width - _CAM_THUMB_W - _CAM_THUMB_MARGIN
    y = _CAM_THUMB_MARGIN

    if _cam_thumb_surf is None:
        _cam_thumb_surf = pygame.Surface((_CAM_THUMB_W, _CAM_THUMB_H))
    thumb_surface = _cam_thumb_surf
    thumb_surface.fill((10, 10, 18))

    if landmarks:
        for a, b in _HAND_CONNECTIONS:
            ax = int(landmarks[a].x * _CAM_THUMB_W)
            ay = int(landmarks[a].y * _CAM_THUMB_H)
            bx = int(landmarks[b].x * _CAM_THUMB_W)
            by = int(landmarks[b].y * _CAM_THUMB_H)
            if a in (5, 9, 13) and b in (9, 13, 17):
                color = _PALM_COLOR
            elif a <= 4 or b <= 4:
                color = _THUMB_COLOR
            else:
                color = _FINGER_COLOR
            pygame.draw.line(thumb_surface, color, (ax, ay), (bx, by), 2)
        for i, lm in enumerate(landmarks):
            px = int(lm.x * _CAM_THUMB_W)
            py = int(lm.y * _CAM_THUMB_H)
            if i in _FINGERTIPS:
                pygame.draw.circle(thumb_surface, _TIP_COLOR, (px, py), 4)
            elif i == 0:
                pygame.draw.circle(thumb_surface, _PALM_COLOR, (px, py), 4)
            else:
                pygame.draw.circle(thumb_surface, _FINGER_COLOR, (px, py), 2)
    else:
        msg = _render_text("no hand", 18, (70, 70, 90))
        thumb_surface.blit(msg, msg.get_rect(center=(_CAM_THUMB_W // 2, _CAM_THUMB_H // 2)))

    border = pygame.Rect(x - 2, y - 2, _CAM_THUMB_W + 4, _CAM_THUMB_H + 4)
    pygame.draw.rect(surface, (70, 70, 100), border, 2, border_radius=4)
    surface.blit(thumb_surface, (x, y))
