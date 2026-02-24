"""
theme_chrome — shared sci-fi / ice chrome drawing helpers for app windows.
Every window can call these to get the futuristic frame, header bar, buttons,
scanline overlay etc. so the look is consistent.
"""
import math, time as _time, pygame

# ── import current-theme query from renderer ───────────────────────
from renderer import is_dark_theme, is_ice_theme

# ── palettes ───────────────────────────────────────────────────────
_SCIFI = {
    "bright":  (0, 255, 220),
    "mid":     (0, 180, 160),
    "dim":     (0, 100, 90),
    "dark":    (0, 50, 45),
    "panel":   (8, 18, 22),
    "header":  (10, 24, 28),
    "stripe":  (14, 28, 36),
    "btn_bg":  (12, 32, 38),
    "btn_bdr": (0, 200, 180),
    "text_hi": (0, 255, 220),
    "text_md": (0, 180, 160),
    "text_lo": (0, 100, 90),
    "glow":    (0, 255, 220),
    "sep":     (0, 60, 50),
    "sel_bg":  (0, 50, 45, 120),
    "scrollbg":(0, 40, 35),
    "scrollfg":(0, 180, 160),
    "folder":  (0, 255, 220),
    "file":    (0, 180, 160),
    "danger":  (255, 60, 80),
    "danger_d":(180, 40, 50),
}
_ICE = {
    "bright":  (100, 180, 255),
    "mid":     (70, 130, 210),
    "dim":     (40, 80, 150),
    "dark":    (20, 40, 80),
    "panel":   (8, 14, 24),
    "header":  (10, 18, 32),
    "stripe":  (14, 22, 40),
    "btn_bg":  (12, 22, 42),
    "btn_bdr": (70, 140, 230),
    "text_hi": (100, 180, 255),
    "text_md": (70, 140, 220),
    "text_lo": (40, 80, 150),
    "glow":    (100, 180, 255),
    "sep":     (30, 50, 90),
    "sel_bg":  (30, 50, 100, 120),
    "scrollbg":(15, 25, 50),
    "scrollfg":(70, 140, 230),
    "folder":  (100, 200, 255),
    "file":    (70, 150, 220),
    "danger":  (255, 80, 100),
    "danger_d":(180, 50, 60),
}

# Font cache
_fc: dict[int, pygame.font.Font] = {}
def _f(sz):
    sz = max(10, sz)
    if sz not in _fc:
        _fc[sz] = pygame.font.Font(None, sz)
    return _fc[sz]


def pal():
    """Return the active sci-fi/ice palette dict, or None if classic."""
    if is_ice_theme():
        return _ICE
    if is_dark_theme():
        return _SCIFI
    return None


def _corner_cut(s):
    """Corner cut size scaled by gui_scale."""
    return max(8, int(20 * s))


# ── angular polygon for a rect with two cut corners ───────────────
def _frame_pts(r, cut):
    """Return polygon points for a rect with top-right and bottom-left corners cut."""
    return [
        (r.x, r.y),                             # top-left  (sharp)
        (r.right - cut, r.y),                    # → top-right before cut
        (r.right, r.y + cut),                    # → top-right after cut
        (r.right, r.bottom),                     # bottom-right (sharp)
        (r.x + cut, r.bottom),                   # → bottom-left before cut
        (r.x, r.bottom - cut),                   # → bottom-left after cut
    ]


# ── scanline overlay (very faint CRT lines) ───────────────────────
_scanline_cache: dict[tuple, pygame.Surface] = {}

def _scanlines(w, h, spacing=3, alpha=18):
    key = (w, h, spacing, alpha)
    if key not in _scanline_cache:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(0, h, spacing):
            pygame.draw.line(s, (0, 0, 0, alpha), (0, y), (w, y))
        _scanline_cache[key] = s
        # keep cache bounded
        if len(_scanline_cache) > 20:
            oldest = next(iter(_scanline_cache))
            del _scanline_cache[oldest]
    return _scanline_cache[key]


# ===================================================================
#  HIGH-LEVEL CHROME DRAWING
# ===================================================================

def draw_window_frame(surface, win, s, p):
    """Fill the angular window background + border + scanlines.
    `p` is the palette dict, `s` is gui_scale."""
    cut = _corner_cut(s)
    pts = _frame_pts(win, cut)

    # Panel fill
    pygame.draw.polygon(surface, p["panel"], pts)

    # Faint grid dots
    gx_step = max(12, int(24 * s))
    for gx in range(win.x + gx_step, win.right, gx_step):
        for gy in range(win.y + gx_step, win.bottom, gx_step):
            surface.set_at((gx, gy), (*p["dim"][:3], 30) if len(p["dim"]) == 3 else p["dim"])

    # Scanlines
    surface.blit(_scanlines(win.width, win.height), win.topleft)

    # Border
    bw = max(2, int(3 * s))
    pygame.draw.polygon(surface, p["bright"], pts, bw)

    # Corner tick marks (top-left, bottom-right)
    tk = max(6, int(16 * s))
    tw = max(1, int(2 * s))
    pygame.draw.line(surface, p["bright"], (win.x, win.y), (win.x + tk, win.y), tw)
    pygame.draw.line(surface, p["bright"], (win.x, win.y), (win.x, win.y + tk), tw)
    pygame.draw.line(surface, p["bright"], (win.right, win.bottom),
                     (win.right - tk, win.bottom), tw)
    pygame.draw.line(surface, p["bright"], (win.right, win.bottom),
                     (win.right, win.bottom - tk), tw)

    # Diagonal accent stripes in top-right cut
    for i in range(1, 5):
        off = int(cut * i / 5)
        sx1 = win.right - cut + off
        sy1 = win.y
        sx2 = win.right
        sy2 = win.y + off
        pygame.draw.line(surface, (*p["dim"][:3], 50) if isinstance(p["dim"], tuple) and len(p["dim"]) == 3 else p["dim"],
                         (sx1, sy1), (sx2, sy2), 1)


def draw_header(surface, win, header_h, title_text, s, p):
    """Draw the angular header bar with title and accent line."""
    cut = _corner_cut(s)
    hdr_pts = [
        (win.x, win.y),
        (win.right - cut, win.y),
        (win.right, win.y + cut),
        (win.right, win.y + header_h),
        (win.x, win.y + header_h),
    ]
    pygame.draw.polygon(surface, p["header"], hdr_pts)

    # Accent line under header
    lw = max(1, int(2 * s))
    pygame.draw.line(surface, p["bright"], (win.x, win.y + header_h),
                     (win.right, win.y + header_h), lw)

    # Small animated pulse dot in header
    t = _time.time()
    pulse = int(80 + 80 * math.sin(t * 3))
    dot_x = win.x + int(12 * s)
    dot_y = win.y + int(14 * s)
    pygame.draw.circle(surface, (*p["bright"][:3],), (dot_x, dot_y), max(3, int(4 * s)))
    # Outer ring
    pygame.draw.circle(surface, (*p["mid"][:3],), (dot_x, dot_y), max(5, int(7 * s)), 1)

    # Title text
    title = _f(int(32 * s)).render(title_text, True, p["text_hi"])
    surface.blit(title, (win.x + int(26 * s), win.y + int(8 * s)))


def draw_angular_button(surface, rect, label, s, p, enabled=True, danger=False):
    """Draw a small angular button. Returns the rect for hit-testing."""
    cut = max(4, int(8 * s))
    pts = [
        (rect.x, rect.y),
        (rect.right - cut, rect.y),
        (rect.right, rect.y + cut),
        (rect.right, rect.bottom),
        (rect.x + cut, rect.bottom),
        (rect.x, rect.bottom - cut),
    ]
    if danger:
        bg = p["danger_d"] if enabled else (40, 20, 25)
        bdr = p["danger"] if enabled else (80, 40, 50)
        txt_c = (255, 200, 200) if enabled else (80, 50, 50)
    else:
        bg = p["btn_bg"] if enabled else (20, 20, 30)
        bdr = p["btn_bdr"] if enabled else p["dim"]
        txt_c = p["text_hi"] if enabled else p["text_lo"]
    pygame.draw.polygon(surface, bg, pts)
    bw = max(1, int(2 * s))
    pygame.draw.polygon(surface, bdr, pts, bw)
    lbl = _f(int(20 * s)).render(label, True, txt_c)
    surface.blit(lbl, lbl.get_rect(center=rect.center))
    return rect


def draw_path_bar(surface, path_text, rect, s, p):
    """Draw a dark path/breadcrumb bar with angular ends."""
    cut = max(3, int(6 * s))
    pts = [
        (rect.x, rect.y),
        (rect.right - cut, rect.y),
        (rect.right, rect.y + cut),
        (rect.right, rect.bottom),
        (rect.x + cut, rect.bottom),
        (rect.x, rect.bottom - cut),
    ]
    pygame.draw.polygon(surface, (4, 10, 14), pts)
    bw = max(1, int(1 * s))
    pygame.draw.polygon(surface, p["dim"], pts, bw)
    font = _f(int(18 * s))
    max_w = rect.width - int(16 * s)
    while font.size(path_text)[0] > max_w and len(path_text) > 20:
        path_text = "..." + path_text[4:]
    img = font.render(path_text, True, p["text_lo"])
    surface.blit(img, (rect.x + int(8 * s), rect.centery - img.get_height() // 2))


def draw_separator(surface, x1, x2, y, p):
    """Thin horizontal separator line."""
    pygame.draw.line(surface, p["sep"], (x1, y), (x2, y), 1)


def draw_scrollbar(surface, rect_track, thumb_frac, thumb_pos_frac, s, p):
    """Draw a sci-fi scrollbar. rect_track = full track rect."""
    cut = max(2, int(3 * s))
    pygame.draw.rect(surface, p["scrollbg"], rect_track, border_radius=cut)
    th = max(int(16 * s), int(rect_track.height * thumb_frac))
    ty = rect_track.y + int((rect_track.height - th) * thumb_pos_frac)
    thumb_r = pygame.Rect(rect_track.x, ty, rect_track.width, th)
    pygame.draw.rect(surface, p["scrollfg"], thumb_r, border_radius=cut)


def draw_footer_text(surface, text, win, s, p):
    """Dim text near the bottom of the window."""
    img = _f(int(16 * s)).render(text, True, p["text_lo"])
    surface.blit(img, (win.x + int(16 * s), win.bottom - int(22 * s)))
