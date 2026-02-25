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
    "bright":  (200, 215, 230),
    "mid":     (120, 160, 200),
    "dim":     (60, 85, 115),
    "dark":    (35, 50, 70),
    "panel":   (10, 16, 24),
    "header":  (14, 22, 32),
    "stripe":  (18, 28, 40),
    "btn_bg":  (18, 28, 40),
    "btn_bdr": (120, 160, 200),
    "text_hi": (200, 215, 230),
    "text_md": (120, 160, 200),
    "text_lo": (60, 85, 115),
    "glow":    (140, 180, 220),
    "sep":     (40, 55, 75),
    "sel_bg":  (35, 55, 80, 120),
    "scrollbg":(20, 30, 45),
    "scrollfg":(120, 160, 200),
    "folder":  (200, 215, 230),
    "file":    (120, 160, 200),
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
    """Fill the window background + border + scanlines.
    Sci-fi uses rounded rects; ice uses angular cut-corners.
    `p` is the palette dict, `s` is gui_scale."""
    cut = _corner_cut(s)

    if not is_ice_theme():
        # ── Minority-Report style: rounded frosted-glass frame ──
        br = max(10, int(16 * s))

        # Translucent panel fill
        glass = pygame.Surface((win.width, win.height), pygame.SRCALPHA)
        pygame.draw.rect(glass, (*p["panel"], 220), (0, 0, win.width, win.height), border_radius=br)
        surface.blit(glass, win.topleft)

        # Inner edge highlight (frosted-glass rim)
        rim = pygame.Surface((win.width, win.height), pygame.SRCALPHA)
        pygame.draw.rect(rim, (*p["dim"][:3], 22), (0, 0, win.width, win.height), border_radius=br)
        m = max(3, int(5 * s))
        pygame.draw.rect(rim, (0, 0, 0, 22), (m, m, win.width - m*2, win.height - m*2),
                         border_radius=max(6, br - m))
        surface.blit(rim, win.topleft)

        # Scanlines (very faint)
        surface.blit(_scanlines(win.width, win.height, spacing=4, alpha=10), win.topleft)

        # Rounded border
        bw = max(1, int(2 * s))
        pygame.draw.rect(surface, p["mid"], win, width=bw, border_radius=br)
    else:
        # ── Ice style: angular cut-corners ──
        pts = _frame_pts(win, cut)
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
    """Draw the header bar with title and accent line.
    Sci-fi uses rounded top; ice uses angular."""
    cut = _corner_cut(s)

    if not is_ice_theme():
        # ── Minority-Report style: rounded header ──
        br = max(10, int(16 * s))
        hdr_rect = pygame.Rect(win.x, win.y, win.width, header_h)
        hdr_surf = pygame.Surface((win.width, header_h), pygame.SRCALPHA)
        pygame.draw.rect(hdr_surf, (*p["header"], 200), (0, 0, win.width, header_h),
                         border_top_left_radius=br, border_top_right_radius=br)
        surface.blit(hdr_surf, (win.x, win.y))

        # Thin divider line under header
        lw = max(1, int(1 * s))
        inset = max(8, int(16 * s))
        pygame.draw.line(surface, (*p["mid"][:3], 120),
                         (win.x + inset, win.y + header_h),
                         (win.right - inset, win.y + header_h), lw)

        # Small arc accent (Minority Report circular motif)
        arc_r = max(6, int(10 * s))
        arc_cx = win.x + int(14 * s)
        arc_cy = win.y + header_h // 2
        arc_rect = pygame.Rect(arc_cx - arc_r, arc_cy - arc_r, arc_r * 2, arc_r * 2)
        pygame.draw.arc(surface, p["mid"], arc_rect,
                        math.radians(30), math.radians(330), max(1, int(2 * s)))

        # Title text
        title = _f(int(32 * s)).render(title_text, True, p["text_hi"])
        surface.blit(title, (win.x + int(30 * s), win.y + int(8 * s)))
    else:
        # ── Ice style: angular header ──
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
    """Draw a small button. Rounded for sci-fi, angular for ice. Returns the rect."""
    if danger:
        bg = p["danger_d"] if enabled else (40, 20, 25)
        bdr = p["danger"] if enabled else (80, 40, 50)
        txt_c = (255, 200, 200) if enabled else (80, 50, 50)
    else:
        bg = p["btn_bg"] if enabled else (20, 20, 30)
        bdr = p["btn_bdr"] if enabled else p["dim"]
        txt_c = p["text_hi"] if enabled else p["text_lo"]

    if not is_ice_theme():
        # Rounded pill-style button (Minority Report)
        br = max(4, int(8 * s))
        pygame.draw.rect(surface, bg, rect, border_radius=br)
        bw = max(1, int(1 * s))
        pygame.draw.rect(surface, bdr, rect, width=bw, border_radius=br)
    else:
        # Angular cut-corner button (ice)
        cut = max(4, int(8 * s))
        pts = [
            (rect.x, rect.y),
            (rect.right - cut, rect.y),
            (rect.right, rect.y + cut),
            (rect.right, rect.bottom),
            (rect.x + cut, rect.bottom),
            (rect.x, rect.bottom - cut),
        ]
        pygame.draw.polygon(surface, bg, pts)
        bw = max(1, int(2 * s))
        pygame.draw.polygon(surface, bdr, pts, bw)

    lbl = _f(int(20 * s)).render(label, True, txt_c)
    surface.blit(lbl, lbl.get_rect(center=rect.center))
    return rect


def draw_path_bar(surface, path_text, rect, s, p):
    """Draw a dark path/breadcrumb bar."""
    if not is_ice_theme():
        # Rounded (Minority Report)
        br = max(3, int(6 * s))
        pygame.draw.rect(surface, (8, 14, 22), rect, border_radius=br)
        bw = max(1, int(1 * s))
        pygame.draw.rect(surface, p["dim"], rect, width=bw, border_radius=br)
    else:
        # Angular (ice)
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


# ───────────────────────────────────────────────────────────────────
#  Sub-panel (interior card / info box) — Minority-Report glass style
# ───────────────────────────────────────────────────────────────────

def draw_sub_panel(surface, rect, s, p, title=None, accent_col=None):
    """Draw an interior sub-panel with frosted-glass MR styling.

    * Sci-fi: translucent glass fill, inner rim highlight, thin border,
              corner-bracket motifs, optional title with arc accent.
    * Ice: angular cut-corner panel with grid dots.
    * Returns the content-area y (below title if present)."""
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    ac = accent_col or p["bright"]

    if not is_ice_theme():
        # ── Minority-Report rounded frosted sub-panel ──
        br = max(6, int(10 * s))

        # Glass fill (translucent)
        glass = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(glass, (*p["panel"], 180), (0, 0, w, h), border_radius=br)
        surface.blit(glass, (x, y))

        # Inner rim highlight
        rim = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(rim, (*p["dim"][:3], 18), (0, 0, w, h), border_radius=br)
        m = max(2, int(3 * s))
        pygame.draw.rect(rim, (0, 0, 0, 18), (m, m, w - m * 2, h - m * 2),
                         border_radius=max(3, br - m))
        surface.blit(rim, (x, y))

        # Border
        bw = max(1, int(1 * s))
        pygame.draw.rect(surface, p["dim"], rect, width=bw, border_radius=br)

        # Corner bracket motifs
        cb = max(4, int(8 * s))
        cb_col = (*p["dim"][:3], 80)
        # top-left
        pygame.draw.line(surface, cb_col, (x + 4, y + 4), (x + 4 + cb, y + 4), 1)
        pygame.draw.line(surface, cb_col, (x + 4, y + 4), (x + 4, y + 4 + cb), 1)
        # top-right
        pygame.draw.line(surface, cb_col, (x + w - 5, y + 4), (x + w - 5 - cb, y + 4), 1)
        pygame.draw.line(surface, cb_col, (x + w - 5, y + 4), (x + w - 5, y + 4 + cb), 1)
        # bottom-left
        pygame.draw.line(surface, cb_col, (x + 4, y + h - 5), (x + 4 + cb, y + h - 5), 1)
        pygame.draw.line(surface, cb_col, (x + 4, y + h - 5), (x + 4, y + h - 5 - cb), 1)
        # bottom-right
        pygame.draw.line(surface, cb_col, (x + w - 5, y + h - 5), (x + w - 5 - cb, y + h - 5), 1)
        pygame.draw.line(surface, cb_col, (x + w - 5, y + h - 5), (x + w - 5, y + h - 5 - cb), 1)

        content_y = y + int(4 * s)

        if title:
            title_h = int(22 * s)
            # Title bar fill (subtle glow)
            th_surf = pygame.Surface((w, title_h), pygame.SRCALPHA)
            pygame.draw.rect(th_surf, (*ac[:3], 16), (0, 0, w, title_h),
                             border_top_left_radius=br, border_top_right_radius=br)
            surface.blit(th_surf, (x, y))

            # Small arc accent (MR circular motif)
            arc_r = max(4, int(6 * s))
            arc_cx = x + int(10 * s)
            arc_cy = y + title_h // 2
            arc_rect = pygame.Rect(arc_cx - arc_r, arc_cy - arc_r, arc_r * 2, arc_r * 2)
            pygame.draw.arc(surface, (*ac[:3], 80), arc_rect,
                            math.radians(30), math.radians(330), max(1, int(1 * s)))

            # Title text
            t = _f(int(14 * s)).render(title, True, ac)
            surface.blit(t, (x + int(20 * s), y + (title_h - t.get_height()) // 2))

            # Divider below title
            inset = max(4, int(8 * s))
            pygame.draw.line(surface, (*p["dim"][:3], 60),
                             (x + inset, y + title_h), (x + w - inset, y + title_h), 1)
            content_y = y + title_h + int(2 * s)

        return content_y
    else:
        # ── Ice angular sub-panel ──
        cut = max(4, int(10 * s))
        pts = [
            (x, y), (x + w - cut, y), (x + w, y + cut),
            (x + w, y + h), (x + cut, y + h), (x, y + h - cut),
        ]
        pygame.draw.polygon(surface, p["panel"], pts)
        bw = max(1, int(2 * s))
        pygame.draw.polygon(surface, p["dim"], pts, bw)

        # Corner ticks
        tk = max(3, int(8 * s))
        pygame.draw.line(surface, p["bright"], (x, y), (x + tk, y), 1)
        pygame.draw.line(surface, p["bright"], (x, y), (x, y + tk), 1)
        pygame.draw.line(surface, p["bright"], (x + w, y + h), (x + w - tk, y + h), 1)
        pygame.draw.line(surface, p["bright"], (x + w, y + h), (x + w, y + h - tk), 1)

        content_y = y + int(4 * s)

        if title:
            title_h = int(22 * s)
            hdr_pts = [
                (x, y), (x + w - cut, y), (x + w, y + cut),
                (x + w, y + title_h), (x, y + title_h),
            ]
            pygame.draw.polygon(surface, p["header"], hdr_pts)
            pygame.draw.line(surface, p["bright"], (x, y + title_h),
                             (x + w, y + title_h), 1)
            t = _f(int(14 * s)).render(title, True, ac)
            surface.blit(t, (x + int(8 * s), y + (title_h - t.get_height()) // 2))
            content_y = y + title_h + int(2 * s)

        return content_y
