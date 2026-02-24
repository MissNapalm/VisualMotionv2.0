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
# Theme toggle  (classic / scifi / ice)
# ==============================
_THEME_CLASSIC = 0
_THEME_SCIFI   = 1
_THEME_ICE     = 2
_THEME_COUNT   = 3
_theme_id = _THEME_SCIFI       # default = sci-fi dark

def toggle_theme():
    """Cycle to the next theme. Clears card cache."""
    global _theme_id
    _theme_id = (_theme_id + 1) % _THEME_COUNT
    _card_surface_cache.clear()

def is_dark_theme():
    return _theme_id != _THEME_CLASSIC

def is_ice_theme():
    return _theme_id == _THEME_ICE

def get_bg_color():
    """Background fill color for the current theme."""
    if _theme_id == _THEME_CLASSIC:
        return (20, 20, 30)
    return (0, 0, 0)   # both sci-fi and ice use black


# ==============================
# Theme toggle button (top-left)
# ==============================
_THEME_BTN_W = 90
_THEME_BTN_H = 30
_THEME_BTN_X = 10
_THEME_BTN_Y = 10

def draw_theme_button(surface):
    """Draw the theme toggle button and return its rect for hit-testing."""
    r = pygame.Rect(_THEME_BTN_X, _THEME_BTN_Y, _THEME_BTN_W, _THEME_BTN_H)
    # Label shows the NEXT theme name
    next_id = (_theme_id + 1) % _THEME_COUNT
    _THEME_NAMES = {_THEME_CLASSIC: "CLASSIC", _THEME_SCIFI: "SCI-FI", _THEME_ICE: "ICE"}
    next_name = _THEME_NAMES[next_id]

    if _theme_id == _THEME_SCIFI:
        # Sci-fi angular button (turquoise)
        cut = 8
        pts = [(r.x, r.y), (r.right - cut, r.y), (r.right, r.y + cut),
               (r.right, r.bottom), (r.x + cut, r.bottom), (r.x, r.bottom - cut)]
        pygame.draw.polygon(surface, (8, 18, 22), pts)
        pygame.draw.polygon(surface, (0, 255, 220), pts, 2)
        lbl = _render_text(next_name, 20, (0, 255, 220))
    elif _theme_id == _THEME_ICE:
        # Ice angular button (light blue)
        cut = 8
        pts = [(r.x, r.y), (r.right - cut, r.y), (r.right, r.y + cut),
               (r.right, r.bottom), (r.x + cut, r.bottom), (r.x, r.bottom - cut)]
        pygame.draw.polygon(surface, (8, 14, 24), pts)
        pygame.draw.polygon(surface, (100, 180, 255), pts, 2)
        lbl = _render_text(next_name, 20, (100, 180, 255))
    else:
        # Classic rounded button
        pygame.draw.rect(surface, (40, 40, 50), r, border_radius=6)
        pygame.draw.rect(surface, (200, 200, 200), r, width=2, border_radius=6)
        lbl = _render_text(next_name, 20, (200, 200, 200))
    surface.blit(lbl, lbl.get_rect(center=r.center))
    return r

def theme_button_hit(px, py):
    """Check if a point hits the theme button."""
    r = pygame.Rect(_THEME_BTN_X, _THEME_BTN_Y, _THEME_BTN_W, _THEME_BTN_H)
    return r.collidepoint(px, py)


# ==============================
# Animated double-helix "graph" (bottom-left, ice theme only)
# ==============================
import time as _time

_HELIX_W = 220         # panel width
_HELIX_H = 140         # panel height
_HELIX_MARGIN = 14     # distance from screen edges
_HELIX_PERIOD = 4.0    # full rotation period in seconds
_HELIX_POINTS = 80     # sample points per strand
_helix_t0 = _time.time()

def draw_helix_graph(surface, win_w, win_h):
    """Draw an animated double-helix 'graph' panel in the bottom-left corner.
    Only meant to be called when the ice theme is active."""
    now = _time.time()
    phase = ((now - _helix_t0) / _HELIX_PERIOD) * math.pi * 2  # continuous rotation

    px = _HELIX_MARGIN
    py = win_h - _HELIX_H - _HELIX_MARGIN

    # Semi-transparent dark panel
    panel = pygame.Surface((_HELIX_W, _HELIX_H), pygame.SRCALPHA)
    panel.fill((6, 12, 22, 200))
    surface.blit(panel, (px, py))

    # Angular border (same style as ice cards)
    cut = 10
    bpts = [
        (px, py), (px + _HELIX_W - cut, py), (px + _HELIX_W, py + cut),
        (px + _HELIX_W, py + _HELIX_H),
        (px + cut, py + _HELIX_H), (px, py + _HELIX_H - cut),
    ]
    pygame.draw.polygon(surface, _ICE_DIM, bpts, 2)

    # Corner ticks
    tk = 8
    pygame.draw.line(surface, _ICE_BRIGHT, (px, py), (px + tk, py), 1)
    pygame.draw.line(surface, _ICE_BRIGHT, (px, py), (px, py + tk), 1)
    pygame.draw.line(surface, _ICE_BRIGHT, (px + _HELIX_W, py + _HELIX_H),
                     (px + _HELIX_W - tk, py + _HELIX_H), 1)
    pygame.draw.line(surface, _ICE_BRIGHT, (px + _HELIX_W, py + _HELIX_H),
                     (px + _HELIX_W, py + _HELIX_H - tk), 1)

    # Label
    lbl = _render_text("HELIX ANALYSIS", 16, _ICE_DIM)
    surface.blit(lbl, (px + 8, py + 4))

    # Horizontal grid lines (faint)
    grid_color = (*_ICE_DARK[:3], 60)
    inner_top = py + 22
    inner_bot = py + _HELIX_H - 8
    inner_left = px + 8
    inner_right = px + _HELIX_W - 8
    for i in range(5):
        gy = inner_top + i * (inner_bot - inner_top) // 4
        pygame.draw.line(surface, grid_color, (inner_left, gy), (inner_right, gy), 1)

    # Draw the two helix strands
    mid_y = (inner_top + inner_bot) / 2
    amp = (inner_bot - inner_top) * 0.38   # amplitude
    strand_w = inner_right - inner_left

    pts_a = []
    pts_b = []
    for i in range(_HELIX_POINTS):
        t = i / (_HELIX_POINTS - 1)
        x = inner_left + t * strand_w
        angle = t * math.pi * 4 + phase          # 2 full twists across panel
        ya = mid_y + math.sin(angle) * amp
        yb = mid_y + math.sin(angle + math.pi) * amp   # 180° offset = other strand
        pts_a.append((int(x), int(ya)))
        pts_b.append((int(x), int(yb)))

    # Draw cross-rungs between strands (every ~10 points) — behind strands
    for i in range(0, _HELIX_POINTS, 8):
        # Only draw rung when strands are roughly level (z-crossing = visual overlap)
        t = i / (_HELIX_POINTS - 1)
        angle = t * math.pi * 4 + phase
        depth_a = math.cos(angle)
        # Draw rung with alpha based on depth
        alpha = int(40 + 40 * abs(depth_a))
        rung_color = (_ICE_DIM[0], _ICE_DIM[1], _ICE_DIM[2], alpha)
        rung_surf = pygame.Surface((abs(pts_a[i][0] - pts_b[i][0]) + 2,
                                    abs(pts_a[i][1] - pts_b[i][1]) + 2), pygame.SRCALPHA)
        x1, y1 = pts_a[i]
        x2, y2 = pts_b[i]
        pygame.draw.line(surface, rung_color, (x1, y1), (x2, y2), 1)

    # Determine which strand is "in front" at each segment to create 3D effect
    # Draw back strand first, then front strand
    for i in range(_HELIX_POINTS):
        t = i / (_HELIX_POINTS - 1)
        angle = t * math.pi * 4 + phase
        depth_a = math.cos(angle)      # positive = strand A in front
        if i > 0:
            # Strand A brightness based on depth
            a_bright = 0.5 + 0.5 * max(0, depth_a)
            b_bright = 0.5 + 0.5 * max(0, -depth_a)
            col_a = (int(_ICE_BRIGHT[0] * a_bright),
                     int(_ICE_BRIGHT[1] * a_bright),
                     int(_ICE_BRIGHT[2] * a_bright))
            col_b = (int(_ICE_MID[0] * b_bright),
                     int(_ICE_MID[1] * b_bright),
                     int(min(255, _ICE_MID[2] * b_bright * 1.2)))
            # Draw back strand segment first
            if depth_a > 0:
                pygame.draw.line(surface, col_b, pts_b[i - 1], pts_b[i], 2)
                pygame.draw.line(surface, col_a, pts_a[i - 1], pts_a[i], 2)
            else:
                pygame.draw.line(surface, col_a, pts_a[i - 1], pts_a[i], 2)
                pygame.draw.line(surface, col_b, pts_b[i - 1], pts_b[i], 2)

    # Small "data" dots at some peaks
    for i in range(0, _HELIX_POINTS, 12):
        pygame.draw.circle(surface, _ICE_BRIGHT, pts_a[i], 3)
        pygame.draw.circle(surface, _ICE_MID, pts_b[i], 2)


# ==============================
# App icon
# ==============================
# Pre-computed brightened app colors
_app_color_cache: dict[str, tuple] = {}

# Card surface cache: (app_name, w, h, is_selected) -> Surface
# Rendered at exact target size for crisp text — no scaling artifacts.
_card_surface_cache: dict[tuple, pygame.Surface] = {}
# ── Sci-fi turquoise palette ──
_CYAN_BRIGHT  = (0, 255, 220)
_CYAN_MID     = (0, 180, 160)
_CYAN_DIM     = (0, 100, 90)
_CYAN_DARK    = (0, 50, 45)
_PANEL_BG     = (8, 18, 22)        # near-black panel body
_PANEL_BG_SEL = (12, 28, 32)       # slightly lighter when selected
_BAR_HEIGHT_FRAC = 0.14            # title-bar height as fraction of card height

# ── Ice (light-blue) palette ──
_ICE_BRIGHT   = (100, 180, 255)
_ICE_MID      = (70,  130, 210)
_ICE_DIM      = (40,  80, 150)
_ICE_DARK     = (20,  40,  80)
_ICE_PANEL_BG     = (8, 14, 24)
_ICE_PANEL_BG_SEL = (12, 22, 36)

_CARD_CACHE_MAX = 60


def _get_card_classic(app_name, w, h, gui_scale, is_selected):
    """Render a classic colorful rounded card."""
    pad = int(6 * gui_scale) + max(2, int(8 * gui_scale)) if is_selected else 0
    sw, sh = w + pad * 2, h + pad * 2
    surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
    cx, cy = sw // 2, sh // 2
    br = max(12, int(50 * gui_scale))

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

    return surf


def _get_card_scifi(app_name, w, h, gui_scale, is_selected):
    """Render a futuristic angular sci-fi window tile with HUD details."""
    import time as _t
    pad = int(8 * gui_scale) if is_selected else 0
    sw, sh = w + pad * 2, h + pad * 2
    surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
    cx, cy = sw // 2, sh // 2

    # Card body rect
    rx, ry, rw, rh = cx - w // 2, cy - h // 2, w, h
    bar_h = max(8, int(rh * _BAR_HEIGHT_FRAC))
    corner_cut = max(6, int(18 * gui_scale))

    # ── Panel body (angular polygon — top-right and bottom-left corners cut) ──
    body_color = _PANEL_BG_SEL if is_selected else _PANEL_BG
    body_pts = [
        (rx, ry),
        (rx + rw - corner_cut, ry),
        (rx + rw, ry + corner_cut),
        (rx + rw, ry + rh),
        (rx + corner_cut, ry + rh),
        (rx, ry + rh - corner_cut),
    ]
    pygame.draw.polygon(surf, body_color, body_pts)

    # ── Scanline overlay (faint horizontal lines across body) ──
    scan_surf = pygame.Surface((rw, rh), pygame.SRCALPHA)
    scan_gap = max(3, int(4 * gui_scale))
    for sy in range(0, rh, scan_gap):
        pygame.draw.line(scan_surf, (0, 255, 220, 8), (0, sy), (rw, sy), 1)
    surf.blit(scan_surf, (rx, ry))

    # ── Grid dot pattern (subtle circuit-board feel) ──
    dot_gap = max(10, int(16 * gui_scale))
    dot_r = max(1, int(1 * gui_scale))
    dot_c = (*_CYAN_DIM[:3], 35)
    for gx in range(rx + dot_gap, rx + rw - dot_gap // 2, dot_gap):
        for gy in range(ry + bar_h + dot_gap, ry + rh - dot_gap // 2, dot_gap):
            pygame.draw.circle(surf, dot_c, (gx, gy), dot_r)

    # ── Title bar (angular, matches top shape) ──
    bar_color = _CYAN_DIM if not is_selected else _CYAN_MID
    bar_pts = [
        (rx, ry),
        (rx + rw - corner_cut, ry),
        (rx + rw, ry + corner_cut),
        (rx + rw, ry + bar_h),
        (rx, ry + bar_h),
    ]
    pygame.draw.polygon(surf, bar_color, bar_pts)

    # ── Thin accent line under the bar ──
    accent = _CYAN_BRIGHT if is_selected else _CYAN_MID
    lw = max(1, int(2 * gui_scale))
    pygame.draw.line(surf, accent, (rx, ry + bar_h), (rx + rw, ry + bar_h), lw)

    # ── Pulsing status dot in title bar ──
    pulse = (math.sin(_t.time() * 4) + 1) * 0.5  # 0..1
    dot_x = rx + rw - int(12 * gui_scale)
    dot_y = ry + bar_h // 2
    dot_sz = max(2, int(4 * gui_scale))
    dot_col = (int(0 + 255 * pulse), int(200 + 55 * pulse), int(180 + 40 * pulse))
    pygame.draw.circle(surf, dot_col, (dot_x, dot_y), dot_sz)

    # ── Border outline (angular, same shape as body) ──
    border_color = _CYAN_BRIGHT if is_selected else _CYAN_DIM
    border_w = max(2, int(3 * gui_scale)) if is_selected else max(1, int(2 * gui_scale))
    pygame.draw.polygon(surf, border_color, body_pts, border_w)

    # ── Decorative corner tick marks (all 4 sharp corners) ──
    tick = max(4, int(12 * gui_scale))
    tick_w = max(1, int(2 * gui_scale))
    pygame.draw.line(surf, _CYAN_BRIGHT, (rx, ry), (rx + tick, ry), tick_w)
    pygame.draw.line(surf, _CYAN_BRIGHT, (rx, ry), (rx, ry + tick), tick_w)
    pygame.draw.line(surf, _CYAN_BRIGHT, (rx + rw, ry + rh), (rx + rw - tick, ry + rh), tick_w)
    pygame.draw.line(surf, _CYAN_BRIGHT, (rx + rw, ry + rh), (rx + rw, ry + rh - tick), tick_w)
    # Extra ticks on cut corners
    pygame.draw.line(surf, _CYAN_BRIGHT, (rx + rw - corner_cut, ry),
                     (rx + rw - corner_cut + tick // 2, ry), tick_w)
    pygame.draw.line(surf, _CYAN_BRIGHT, (rx + corner_cut, ry + rh),
                     (rx + corner_cut - tick // 2, ry + rh), tick_w)

    # ── Small diagonal accent stripes in top-right cut ──
    stripe_color = (*_CYAN_DIM[:3], 80)
    for i in range(1, 4):
        off = int(corner_cut * i / 4)
        sx1 = rx + rw - corner_cut + off
        sy1 = ry
        sx2 = rx + rw
        sy2 = ry + off
        pygame.draw.line(surf, stripe_color, (sx1, sy1), (sx2, sy2), 1)

    # ── Bottom-left cut hatch lines ──
    for i in range(1, 4):
        off = int(corner_cut * i / 4)
        pygame.draw.line(surf, stripe_color,
                         (rx, ry + rh - corner_cut + off),
                         (rx + off, ry + rh), 1)

    # ── App name in title bar ──
    bar_text_size = max(10, int(22 * gui_scale))
    bar_text = _render_text(app_name, bar_text_size, _CYAN_BRIGHT)
    surf.blit(bar_text, (rx + max(4, int(10 * gui_scale)),
                         ry + bar_h // 2 - bar_text.get_height() // 2))

    # ── Large icon letter centred in panel body ──
    icon_size = max(24, int(100 * gui_scale))
    icon_color = _CYAN_BRIGHT if is_selected else _CYAN_MID
    icon_img = _render_text(app_name[0], icon_size, icon_color)
    body_center_y = ry + bar_h + (rh - bar_h) // 2
    surf.blit(icon_img, icon_img.get_rect(center=(cx, body_center_y - int(14 * gui_scale))))

    # ── Sub-label below icon ──
    sub_size = max(10, int(28 * gui_scale))
    sub_img = _render_text(app_name, sub_size, _CYAN_DIM)
    surf.blit(sub_img, sub_img.get_rect(center=(cx, body_center_y + int(38 * gui_scale))))

    # ── HUD data readout line (bottom of card) ──
    data_size = max(8, int(14 * gui_scale))
    data_color = (*_CYAN_DIM[:3], 140)
    data_text = f"SYS.{app_name[:3].upper()}.OK"
    data_img = _render_text(data_text, data_size, data_color)
    surf.blit(data_img, (rx + int(6 * gui_scale), ry + rh - data_img.get_height() - int(6 * gui_scale)))

    # ── Thin horizontal bracket lines near bottom ──
    bkt_y = ry + rh - int(22 * gui_scale)
    bkt_c = (*_CYAN_DIM[:3], 60)
    bkt_w2 = rw // 3
    pygame.draw.line(surf, bkt_c, (rx + rw - bkt_w2 - int(4 * gui_scale), bkt_y),
                     (rx + rw - int(4 * gui_scale), bkt_y), 1)
    # Small vertical end-caps
    pygame.draw.line(surf, bkt_c, (rx + rw - int(4 * gui_scale), bkt_y),
                     (rx + rw - int(4 * gui_scale), bkt_y + int(4 * gui_scale)), 1)

    # ── Selection glow border (outer) ──
    if is_selected:
        glow_pts = [
            (rx - 3, ry - 3),
            (rx + rw - corner_cut + 1, ry - 3),
            (rx + rw + 3, ry + corner_cut - 1),
            (rx + rw + 3, ry + rh + 3),
            (rx + corner_cut - 1, ry + rh + 3),
            (rx - 3, ry + rh - corner_cut + 1),
        ]
        pygame.draw.polygon(surf, _CYAN_BRIGHT, glow_pts, max(2, int(4 * gui_scale)))

    return surf


def _get_card_ice(app_name, w, h, gui_scale, is_selected):
    """Render a futuristic angular card in the ice (light-blue) palette with HUD details."""
    import time as _t
    pad = int(8 * gui_scale) if is_selected else 0
    sw, sh = w + pad * 2, h + pad * 2
    surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
    cx, cy = sw // 2, sh // 2

    rx, ry, rw, rh = cx - w // 2, cy - h // 2, w, h
    bar_h = max(8, int(rh * _BAR_HEIGHT_FRAC))
    corner_cut = max(6, int(18 * gui_scale))

    # ── Panel body ──
    body_color = _ICE_PANEL_BG_SEL if is_selected else _ICE_PANEL_BG
    body_pts = [
        (rx, ry),
        (rx + rw - corner_cut, ry),
        (rx + rw, ry + corner_cut),
        (rx + rw, ry + rh),
        (rx + corner_cut, ry + rh),
        (rx, ry + rh - corner_cut),
    ]
    pygame.draw.polygon(surf, body_color, body_pts)

    # ── Scanline overlay ──
    scan_surf = pygame.Surface((rw, rh), pygame.SRCALPHA)
    scan_gap = max(3, int(4 * gui_scale))
    for sy in range(0, rh, scan_gap):
        pygame.draw.line(scan_surf, (100, 180, 255, 6), (0, sy), (rw, sy), 1)
    surf.blit(scan_surf, (rx, ry))

    # ── Grid dot pattern ──
    dot_gap = max(10, int(16 * gui_scale))
    dot_r = max(1, int(1 * gui_scale))
    dot_c = (*_ICE_DIM[:3], 30)
    for gx in range(rx + dot_gap, rx + rw - dot_gap // 2, dot_gap):
        for gy in range(ry + bar_h + dot_gap, ry + rh - dot_gap // 2, dot_gap):
            pygame.draw.circle(surf, dot_c, (gx, gy), dot_r)

    # ── Title bar ──
    bar_color = _ICE_DIM if not is_selected else _ICE_MID
    bar_pts = [
        (rx, ry),
        (rx + rw - corner_cut, ry),
        (rx + rw, ry + corner_cut),
        (rx + rw, ry + bar_h),
        (rx, ry + bar_h),
    ]
    pygame.draw.polygon(surf, bar_color, bar_pts)

    # ── Accent line under bar ──
    accent = _ICE_BRIGHT if is_selected else _ICE_MID
    lw = max(1, int(2 * gui_scale))
    pygame.draw.line(surf, accent, (rx, ry + bar_h), (rx + rw, ry + bar_h), lw)

    # ── Pulsing status dot in title bar ──
    pulse = (math.sin(_t.time() * 3.5 + 1.0) + 1) * 0.5
    dot_x = rx + rw - int(12 * gui_scale)
    dot_y = ry + bar_h // 2
    dot_sz = max(2, int(4 * gui_scale))
    dot_col = (int(80 + 20 * pulse), int(160 + 20 * pulse), int(220 + 35 * pulse))
    pygame.draw.circle(surf, dot_col, (dot_x, dot_y), dot_sz)

    # ── Border outline ──
    border_color = _ICE_BRIGHT if is_selected else _ICE_DIM
    border_w = max(2, int(3 * gui_scale)) if is_selected else max(1, int(2 * gui_scale))
    pygame.draw.polygon(surf, border_color, body_pts, border_w)

    # ── Corner tick marks (all 4 sharp + 2 cut corners) ──
    tick = max(4, int(12 * gui_scale))
    tick_w = max(1, int(2 * gui_scale))
    pygame.draw.line(surf, _ICE_BRIGHT, (rx, ry), (rx + tick, ry), tick_w)
    pygame.draw.line(surf, _ICE_BRIGHT, (rx, ry), (rx, ry + tick), tick_w)
    pygame.draw.line(surf, _ICE_BRIGHT, (rx + rw, ry + rh), (rx + rw - tick, ry + rh), tick_w)
    pygame.draw.line(surf, _ICE_BRIGHT, (rx + rw, ry + rh), (rx + rw, ry + rh - tick), tick_w)
    pygame.draw.line(surf, _ICE_BRIGHT, (rx + rw - corner_cut, ry),
                     (rx + rw - corner_cut + tick // 2, ry), tick_w)
    pygame.draw.line(surf, _ICE_BRIGHT, (rx + corner_cut, ry + rh),
                     (rx + corner_cut - tick // 2, ry + rh), tick_w)

    # ── Diagonal accent stripes in top-right cut ──
    stripe_color = (*_ICE_DIM[:3], 80)
    for i in range(1, 4):
        off = int(corner_cut * i / 4)
        sx1 = rx + rw - corner_cut + off
        sy1 = ry
        sx2 = rx + rw
        sy2 = ry + off
        pygame.draw.line(surf, stripe_color, (sx1, sy1), (sx2, sy2), 1)

    # ── Bottom-left cut hatch lines ──
    for i in range(1, 4):
        off = int(corner_cut * i / 4)
        pygame.draw.line(surf, stripe_color,
                         (rx, ry + rh - corner_cut + off),
                         (rx + off, ry + rh), 1)

    # ── App name in title bar ──
    bar_text_size = max(10, int(22 * gui_scale))
    bar_text = _render_text(app_name, bar_text_size, _ICE_BRIGHT)
    surf.blit(bar_text, (rx + max(4, int(10 * gui_scale)),
                         ry + bar_h // 2 - bar_text.get_height() // 2))

    # ── Large icon letter ──
    icon_size = max(24, int(100 * gui_scale))
    icon_color = _ICE_BRIGHT if is_selected else _ICE_MID
    icon_img = _render_text(app_name[0], icon_size, icon_color)
    body_center_y = ry + bar_h + (rh - bar_h) // 2
    surf.blit(icon_img, icon_img.get_rect(center=(cx, body_center_y - int(14 * gui_scale))))

    # ── Sub-label ──
    sub_size = max(10, int(28 * gui_scale))
    sub_img = _render_text(app_name, sub_size, _ICE_DIM)
    surf.blit(sub_img, sub_img.get_rect(center=(cx, body_center_y + int(38 * gui_scale))))

    # ── HUD data readout (bottom) ──
    data_size = max(8, int(14 * gui_scale))
    data_color = (*_ICE_DIM[:3], 140)
    data_text = f"MOD.{app_name[:3].upper()}.RDY"
    data_img = _render_text(data_text, data_size, data_color)
    surf.blit(data_img, (rx + int(6 * gui_scale), ry + rh - data_img.get_height() - int(6 * gui_scale)))

    # ── Thin horizontal bracket line near bottom ──
    bkt_y = ry + rh - int(22 * gui_scale)
    bkt_c = (*_ICE_DIM[:3], 60)
    bkt_w2 = rw // 3
    pygame.draw.line(surf, bkt_c, (rx + rw - bkt_w2 - int(4 * gui_scale), bkt_y),
                     (rx + rw - int(4 * gui_scale), bkt_y), 1)
    pygame.draw.line(surf, bkt_c, (rx + rw - int(4 * gui_scale), bkt_y),
                     (rx + rw - int(4 * gui_scale), bkt_y + int(4 * gui_scale)), 1)

    # ── Selection glow ──
    if is_selected:
        glow_pts = [
            (rx - 3, ry - 3),
            (rx + rw - corner_cut + 1, ry - 3),
            (rx + rw + 3, ry + corner_cut - 1),
            (rx + rw + 3, ry + rh + 3),
            (rx + corner_cut - 1, ry + rh + 3),
            (rx - 3, ry + rh - corner_cut + 1),
        ]
        pygame.draw.polygon(surf, _ICE_BRIGHT, glow_pts, max(2, int(4 * gui_scale)))

    return surf


def _get_card_surface(app_name, w, h, gui_scale, is_selected):
    """Dispatch to the active theme's card renderer, with caching."""
    import time as _t
    # For animated themes, bucket time to ~8 fps animation so cache still helps
    if _theme_id != _THEME_CLASSIC:
        time_bucket = int(_t.time() * 8)
    else:
        time_bucket = 0
    key = (app_name, w, h, is_selected, time_bucket)
    if key in _card_surface_cache:
        return _card_surface_cache[key]
    # Evict oldest entries if cache is full
    if len(_card_surface_cache) >= _CARD_CACHE_MAX:
        for old_key in list(_card_surface_cache.keys())[:30]:
            del _card_surface_cache[old_key]
    if _theme_id == _THEME_SCIFI:
        surf = _get_card_scifi(app_name, w, h, gui_scale, is_selected)
    elif _theme_id == _THEME_ICE:
        surf = _get_card_ice(app_name, w, h, gui_scale, is_selected)
    else:
        surf = _get_card_classic(app_name, w, h, gui_scale, is_selected)
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
    t = _render_text(f"GUI {state.gui_scale_target:.1f}x", max(18, int(40 * s)), white)
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
