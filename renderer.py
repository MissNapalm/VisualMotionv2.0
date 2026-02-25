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
# Subtle drifting stars (classic theme)
# ==============================
import random as _star_rand

_stars: list | None = None
_STAR_COUNT = 120


def _init_stars(w: int, h: int):
    """Create a field of tiny stars with random positions, brightness, and drift speed."""
    global _stars
    _stars = []
    for _ in range(_STAR_COUNT):
        _stars.append({
            "x": _star_rand.random() * w,
            "y": _star_rand.random() * h,
            "b": _star_rand.randint(25, 70),        # base brightness (very dim)
            "s": _star_rand.uniform(0.04, 0.25),     # drift speed px/frame
            "r": _star_rand.uniform(0.5, 1.5),       # radius
            "tw": _star_rand.uniform(0.002, 0.008),  # twinkle speed
            "tp": _star_rand.random() * 6.28,        # twinkle phase
        })

import time as _star_time

def draw_stars_bg(surface):
    """Draw very subtle drifting stars on the classic theme.
       Returns True if drawn, False otherwise."""
    if _theme_id != _THEME_CLASSIC:
        return False
    w, h = surface.get_size()
    if _stars is None:
        _init_stars(w, h)
    t = _star_time.time()
    for s in _stars:
        # Slow horizontal drift
        s["x"] -= s["s"]
        if s["x"] < -2:
            s["x"] = w + 2
            s["y"] = _star_rand.random() * h
        # Gentle twinkle
        import math as _m
        flicker = _m.sin(t * 60.0 * s["tw"] + s["tp"]) * 0.3 + 0.7
        bright = int(s["b"] * flicker)
        bright = max(10, min(bright, 80))
        c = (bright, bright, bright + 8)  # very slight blue tint
        r = s["r"]
        if r < 1.0:
            surface.set_at((int(s["x"]), int(s["y"])), c)
        else:
            pygame.draw.circle(surface, c, (int(s["x"]), int(s["y"])), int(r))
    return True


# ==============================
# Scrolling hex-code rain (sci-fi background)
# ==============================
_hex_columns: list | None = None
_HEX_COLS = 22          # number of columns across the screen
_HEX_ROWS = 50          # total rows per column (wraps around)
_hex_font_size = 13
_hex_seed_w = 0
_hex_seed_h = 0
_hex_strip_cache: dict[int, pygame.Surface] | None = None  # pre-rendered column strips

def _init_hex_columns(w, h):
    """Pre-generate column positions, speeds, and pre-render each column strip."""
    global _hex_columns, _hex_seed_w, _hex_seed_h, _hex_strip_cache
    _hex_seed_w, _hex_seed_h = w, h
    rng = _star_rand.Random(99)
    col_spacing = w // _HEX_COLS
    row_h = _hex_font_size + 4
    font = get_font(_hex_font_size)
    text_color = (35, 50, 70)  # _MR_FAINT equivalent (avoid forward-ref at import)

    _hex_columns = []
    _hex_strip_cache = {}
    for i in range(_HEX_COLS):
        x = int(col_spacing * (i + 0.5))
        speed = rng.uniform(6, 22)
        phase = rng.random() * 10000
        _hex_columns.append({"x": x, "speed": speed, "phase": phase})

        # Pre-render the entire column as one tall strip surface
        strip_h = _HEX_ROWS * row_h
        strip = pygame.Surface((50, strip_h), pygame.SRCALPHA)
        for j in range(_HEX_ROWS):
            hex_str = f"{rng.randint(0, 0xFFFF):04X}"
            img = font.render(hex_str, True, text_color)
            strip.blit(img, (0, j * row_h))
        strip.set_alpha(18)  # barely visible
        _hex_strip_cache[i] = strip

def draw_hex_rain(surface, win_w, win_h):
    """Draw barely-visible scrolling hex codes behind everything.
    Only active on sci-fi theme. Returns True if drawn."""
    if _theme_id != _THEME_SCIFI:
        return False
    if _hex_columns is None or _hex_seed_w != win_w or _hex_seed_h != win_h:
        _init_hex_columns(win_w, win_h)

    now = _star_time.time()
    row_h = _hex_font_size + 4

    for i, col in enumerate(_hex_columns):
        strip = _hex_strip_cache[i]
        strip_h = strip.get_height()
        # Scroll offset in pixels (wraps)
        offset = int((now * col["speed"] + col["phase"]) % strip_h)
        x = col["x"]
        # Blit the strip twice to create seamless wrap-around scroll
        surface.blit(strip, (x, -offset))
        surface.blit(strip, (x, -offset + strip_h))
    return True


# ==============================
# Ambient system-monitor background (sci-fi theme — behind cards)
# ==============================
# Rolling data buffers — fake but plausible system metrics
_SYSMON_HISTORY = 200          # samples per graph
_SYSMON_GRAPH_W = 340          # pixels wide
_SYSMON_GRAPH_H = 70           # pixels tall per graph
_SYSMON_GRAPHS = 3             # CPU, MEM, NET
_sysmon_data: list[list[float]] | None = None
_sysmon_t0 = 0.0
_sysmon_last_push = 0.0
_sysmon_rng = _star_rand.Random(777)


def _init_sysmon_data():
    global _sysmon_data, _sysmon_t0, _sysmon_last_push
    _sysmon_t0 = _time.time()
    _sysmon_last_push = _sysmon_t0
    _sysmon_data = []
    for g in range(_SYSMON_GRAPHS):
        # Pre-fill with smooth random data
        buf = []
        val = _sysmon_rng.uniform(0.2, 0.6)
        for _ in range(_SYSMON_HISTORY):
            val += _sysmon_rng.uniform(-0.04, 0.04)
            val = max(0.05, min(0.95, val))
            buf.append(val)
        _sysmon_data.append(buf)


def _push_sysmon_sample():
    """Add a new data point to each graph (called ~15 times/sec)."""
    global _sysmon_last_push
    now = _time.time()
    if now - _sysmon_last_push < 0.066:   # ~15 Hz update rate
        return
    _sysmon_last_push = now
    t = now - _sysmon_t0
    for g in range(_SYSMON_GRAPHS):
        prev = _sysmon_data[g][-1]
        # Each graph has a different "personality"
        if g == 0:   # CPU — bursty, medium frequency
            drift = math.sin(t * 0.7 + 1.0) * 0.03 + _sysmon_rng.uniform(-0.025, 0.025)
            # Occasional spikes
            if _sysmon_rng.random() < 0.03:
                drift += _sysmon_rng.uniform(0.1, 0.3)
        elif g == 1: # MEM — slow, gradual drift
            drift = math.sin(t * 0.2) * 0.008 + _sysmon_rng.uniform(-0.008, 0.008)
        else:        # NET — spiky, fast
            drift = _sysmon_rng.uniform(-0.06, 0.06)
            if _sysmon_rng.random() < 0.08:
                drift += _sysmon_rng.choice([-1, 1]) * _sysmon_rng.uniform(0.08, 0.25)
        val = max(0.03, min(0.97, prev + drift))
        _sysmon_data[g].append(val)
        if len(_sysmon_data[g]) > _SYSMON_HISTORY:
            _sysmon_data[g].pop(0)


def draw_sysmon_bg(surface, win_w, win_h):
    """Draw ambient animated system-monitor line graphs behind the cards.
    Three translucent graph panels arrayed across the background.
    Only active on sci-fi theme. Returns True if drawn."""
    if _theme_id != _THEME_SCIFI:
        return False
    if _sysmon_data is None:
        _init_sysmon_data()
    _push_sysmon_sample()

    now = _time.time()
    gw = _SYSMON_GRAPH_W
    gh = _SYSMON_GRAPH_H

    _GRAPH_LABELS = ["CPU LOAD", "MEMORY", "NETWORK I/O"]
    _GRAPH_COLORS = [
        (120, 180, 220),    # cool blue (CPU)
        (100, 210, 170),    # teal-green (MEM)
        (170, 140, 220),    # soft purple (NET)
    ]
    _GRAPH_FILL_ALPHA = [16, 14, 12]

    # Horizontal layout: distribute graphs along the bottom edge
    total_w = gw * _SYSMON_GRAPHS + 40 * (_SYSMON_GRAPHS - 1)
    start_x = (win_w - total_w) // 2
    base_y = win_h - gh - 160   # above the HUD telemetry panels at the very bottom

    for g in range(_SYSMON_GRAPHS):
        gx = start_x + g * (gw + 40)
        gy = base_y

        # ── Frosted glass panel ──
        panel = pygame.Surface((gw + 16, gh + 32), pygame.SRCALPHA)
        pygame.draw.rect(panel, (*_MR_GLASS, 40), (0, 0, gw + 16, gh + 32), border_radius=6)
        pygame.draw.rect(panel, (*_MR_DIM, 20), (0, 0, gw + 16, gh + 32), width=1, border_radius=6)
        surface.blit(panel, (gx - 8, gy - 22))

        # ── Label ──
        lbl_col = _GRAPH_COLORS[g]
        lbl = _render_text(_GRAPH_LABELS[g], 11, (*lbl_col[:3],))
        surface.blit(lbl, (gx, gy - 16))

        # ── Percentage readout (latest value) ──
        pct = _sysmon_data[g][-1] * 100
        pct_str = f"{pct:4.1f}%"
        pct_img = _render_text(pct_str, 11, (*lbl_col[:3],))
        surface.blit(pct_img, (gx + gw - pct_img.get_width(), gy - 16))

        # ── Horizontal grid lines (faint) ──
        for gi in range(5):
            grid_y = gy + int(gi * gh / 4)
            pygame.draw.line(surface, (*_MR_FAINT, 18),
                             (gx, grid_y), (gx + gw, grid_y), 1)

        # ── Build polyline from data ──
        data = _sysmon_data[g]
        visible = min(len(data), _SYSMON_HISTORY)
        step = gw / max(1, visible - 1)
        pts = []
        for i in range(visible):
            px = gx + int(i * step)
            py = gy + gh - int(data[len(data) - visible + i] * gh)
            pts.append((px, py))

        if len(pts) > 1:
            # ── Filled area under the curve (very faint) ──
            fill_pts = list(pts) + [(pts[-1][0], gy + gh), (pts[0][0], gy + gh)]
            fill_surf = pygame.Surface((gw + 2, gh + 2), pygame.SRCALPHA)
            # Shift points relative to fill_surf origin
            shifted = [(p[0] - gx, p[1] - gy) for p in fill_pts]
            try:
                pygame.draw.polygon(fill_surf, (*_GRAPH_COLORS[g], _GRAPH_FILL_ALPHA[g]),
                                    shifted)
                surface.blit(fill_surf, (gx, gy))
            except Exception:
                pass  # degenerate polygon edge case

            # ── Line graph ──
            line_alpha = 50
            line_surf = pygame.Surface((gw + 2, gh + 2), pygame.SRCALPHA)
            shifted_line = [(p[0] - gx, p[1] - gy) for p in pts]
            pygame.draw.lines(line_surf, (*_GRAPH_COLORS[g], line_alpha), False, shifted_line, 1)
            surface.blit(line_surf, (gx, gy))

            # ── Bright dot at the latest point (rightmost) ──
            latest = pts[-1]
            dot_pulse = int(60 + 30 * math.sin(now * 4.0 + g * 2.0))
            pygame.draw.circle(surface, (*_GRAPH_COLORS[g], dot_pulse),
                               latest, 3)

        # ── Bottom axis line ──
        pygame.draw.line(surface, (*_MR_DIM, 30),
                         (gx, gy + gh), (gx + gw, gy + gh), 1)


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
        # Minority-Report rounded button (cold blue-silver)
        br = 8
        pygame.draw.rect(surface, (14, 22, 32), r, border_radius=br)
        pygame.draw.rect(surface, (120, 160, 200), r, width=1, border_radius=br)
        lbl = _render_text(next_name, 20, (200, 215, 230))
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
# Cybernetic background grid
# ==============================
import time as _time
import random as _random

# Pre-generate the circuit layout once so it doesn't shift every frame.
# Each "trace" is a path of horizontal/vertical segments with occasional junctions.
_cyber_traces: list | None = None
_cyber_nodes: list | None = None
_cyber_seed_w = 0
_cyber_seed_h = 0
_cyber_pulse_t0 = 0.0


def _generate_cyber_layout(win_w, win_h):
    """Build a set of circuit-board-style traces and junction nodes."""
    global _cyber_traces, _cyber_nodes, _cyber_seed_w, _cyber_seed_h, _cyber_pulse_t0
    _cyber_seed_w = win_w
    _cyber_seed_h = win_h
    _cyber_pulse_t0 = _time.time()
    rng = _random.Random(42)  # deterministic so layout is stable

    traces = []
    nodes = []

    # Horizontal main bus lines
    for i in range(6):
        y = int(win_h * (0.08 + i * 0.16))
        x0 = rng.randint(20, win_w // 4)
        x1 = rng.randint(win_w * 3 // 4, win_w - 20)
        traces.append(("h", x0, y, x1, y, rng.uniform(0.3, 1.0)))

        # Branch stubs dropping down or up from the bus
        num_branches = rng.randint(2, 5)
        for _ in range(num_branches):
            bx = rng.randint(x0 + 30, x1 - 30)
            direction = rng.choice([-1, 1])
            blen = rng.randint(30, 120)
            by2 = y + direction * blen
            traces.append(("v", bx, y, bx, by2, rng.uniform(0.2, 0.8)))
            # Sometimes add a horizontal stub at the end of the branch
            if rng.random() < 0.5:
                stub_dir = rng.choice([-1, 1])
                stub_len = rng.randint(20, 80)
                sx2 = bx + stub_dir * stub_len
                traces.append(("h", bx, by2, sx2, by2, rng.uniform(0.15, 0.6)))
                # Junction dot at the corner
                nodes.append((bx, by2, rng.uniform(0.2, 0.7)))
            # Junction dot where branch meets bus
            nodes.append((bx, y, rng.uniform(0.3, 0.9)))

    # Vertical risers
    for i in range(4):
        x = int(win_w * (0.15 + i * 0.22))
        y0 = rng.randint(20, win_h // 3)
        y1 = rng.randint(win_h * 2 // 3, win_h - 20)
        traces.append(("v", x, y0, x, y1, rng.uniform(0.2, 0.7)))
        # Small horizontal ticks along the riser
        num_ticks = rng.randint(3, 7)
        for _ in range(num_ticks):
            ty = rng.randint(y0 + 10, y1 - 10)
            td = rng.choice([-1, 1])
            tl = rng.randint(8, 40)
            traces.append(("h", x, ty, x + td * tl, ty, rng.uniform(0.1, 0.4)))

    _cyber_traces = traces
    _cyber_nodes = nodes


def draw_cyber_grid(surface, win_w, win_h):
    """Draw subtle animated cybernetic circuit lines behind everything."""
    global _cyber_traces, _cyber_nodes

    # Regenerate layout if screen size changed or first call
    if _cyber_traces is None or _cyber_seed_w != win_w or _cyber_seed_h != win_h:
        _generate_cyber_layout(win_w, win_h)

    now = _time.time()
    elapsed = now - _cyber_pulse_t0

    # Theme-aware colors
    if _theme_id == _THEME_SCIFI:
        base_color = (60, 85, 115)     # cool blue-gray (MR palette)
        node_color = (120, 160, 200)
        pulse_color = (140, 180, 220)
        base_alpha = 14
        node_alpha = 22
    elif _theme_id == _THEME_ICE:
        base_color = (100, 160, 220)   # pale blue
        node_color = (130, 190, 255)
        pulse_color = (180, 220, 255)
        base_alpha = 14
        node_alpha = 24
    else:
        base_color = (40, 50, 70)      # dim blue-gray for classic
        node_color = (60, 70, 90)
        pulse_color = (80, 100, 130)
        base_alpha = 12
        node_alpha = 18

    # Draw traces
    for trace in _cyber_traces:
        _kind, x1, y1, x2, y2, phase_offset = trace
        # Subtle pulse: brightness oscillates slowly
        pulse = 0.6 + 0.4 * math.sin(elapsed * 0.8 + phase_offset * math.pi * 6)
        a = int(base_alpha * pulse)
        color = (*base_color, max(4, a))
        pygame.draw.line(surface, color, (x1, y1), (x2, y2), 1)

    # Draw junction nodes (small dots)
    for node in _cyber_nodes:
        nx, ny, phase_offset = node
        pulse = 0.5 + 0.5 * math.sin(elapsed * 1.2 + phase_offset * math.pi * 8)
        a = int(node_alpha * pulse)
        color = (*node_color, max(4, a))
        pygame.draw.circle(surface, color, (int(nx), int(ny)), 2)

    # Travelling pulse dots along a few traces (data packets)
    num_pulses = 8
    for i in range(num_pulses):
        # Each pulse travels along a different trace
        trace_idx = (i * 7) % len(_cyber_traces)
        trace = _cyber_traces[trace_idx]
        _kind, x1, y1, x2, y2, phase_offset = trace
        # Position along the trace oscillates over time
        speed = 0.3 + phase_offset * 0.4
        t = ((elapsed * speed + phase_offset * 5.0) % 2.0)
        if t > 1.0:
            t = 2.0 - t  # bounce back
        px = x1 + (x2 - x1) * t
        py = y1 + (y2 - y1) * t
        # Bright dot
        pa = int(35 + 25 * math.sin(elapsed * 2.0 + i))
        pygame.draw.circle(surface, (*pulse_color, max(8, pa)), (int(px), int(py)), 2)


# ==============================
# Animated double-helix "graph" (bottom-left, ice theme only)
# ==============================

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
# ── Sci-fi turquoise palette (legacy, kept for ice fallback) ──
_CYAN_BRIGHT  = (0, 255, 220)
_CYAN_MID     = (0, 180, 160)
_CYAN_DIM     = (0, 100, 90)
_CYAN_DARK    = (0, 50, 45)
_PANEL_BG     = (8, 18, 22)        # near-black panel body
_PANEL_BG_SEL = (12, 28, 32)       # slightly lighter when selected
_BAR_HEIGHT_FRAC = 0.14            # title-bar height as fraction of card height

# ── Minority-Report-inspired palette (desaturated cold blue-silver) ──
_MR_WHITE     = (200, 215, 230)    # cold white text / bright accents
_MR_BLUE      = (120, 160, 200)    # mid-tone cool blue
_MR_DIM       = (60,  85, 115)     # dim structural lines
_MR_FAINT     = (35,  50,  70)     # very faint accents
_MR_GLASS     = (15,  22,  32)     # frosted-glass body tint
_MR_GLOW      = (140, 180, 220)    # selection glow

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
    card_alpha_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    card_alpha = 210 if is_selected else 195
    pygame.draw.rect(card_alpha_surf, (*color, card_alpha), (0, 0, w, h), border_radius=br)
    surf.blit(card_alpha_surf, (card_rect.x, card_rect.y))

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
    """Render a Minority-Report-inspired translucent glass panel tile."""
    pad = int(10 * gui_scale) if is_selected else 0
    sw, sh = w + pad * 2, h + pad * 2
    surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
    cx, cy = sw // 2, sh // 2

    # Card body rect
    rx, ry, rw, rh = cx - w // 2, cy - h // 2, w, h
    br = max(8, int(14 * gui_scale))  # rounded corners — curves, not angular cuts
    line_inset = max(8, int(16 * gui_scale))

    # ── 1. Frosted-glass panel body (semi-transparent) ──
    glass_alpha = 190 if is_selected else 165
    glass_surf = pygame.Surface((rw, rh), pygame.SRCALPHA)
    pygame.draw.rect(glass_surf, (*_MR_GLASS, glass_alpha), (0, 0, rw, rh), border_radius=br)
    surf.blit(glass_surf, (rx, ry))

    # ── 2. Subtle inner edge highlight (frosted glass rim) ──
    rim_alpha = 25 if is_selected else 15
    rim_surf = pygame.Surface((rw, rh), pygame.SRCALPHA)
    pygame.draw.rect(rim_surf, (*_MR_DIM, rim_alpha), (0, 0, rw, rh), border_radius=br)
    inner_margin = max(3, int(6 * gui_scale))
    inner_rect = (inner_margin, inner_margin, rw - inner_margin * 2, rh - inner_margin * 2)
    inner_br = max(5, br - inner_margin)
    pygame.draw.rect(rim_surf, (0, 0, 0, rim_alpha), inner_rect, border_radius=inner_br)
    surf.blit(rim_surf, (rx, ry))

    # ── 3. Thin horizontal divider line (top quarter — separates title zone) ──
    div_y = ry + int(rh * 0.26)
    line_color = _MR_DIM if not is_selected else _MR_BLUE
    lw = max(1, int(1 * gui_scale))
    pygame.draw.line(surf, (*line_color, 100),
                     (rx + line_inset, div_y), (rx + rw - line_inset, div_y), lw)

    # ── 4. Small arc accent (circular motif — Minority Report curve) ──
    arc_r = max(10, int(28 * gui_scale))
    arc_cx = rx + rw - int(24 * gui_scale)
    arc_cy = ry + int(20 * gui_scale)
    arc_color = _MR_BLUE if is_selected else _MR_DIM
    arc_rect = pygame.Rect(arc_cx - arc_r, arc_cy - arc_r, arc_r * 2, arc_r * 2)
    pygame.draw.arc(surf, (*arc_color, 90), arc_rect,
                    math.radians(200), math.radians(340),
                    max(1, int(2 * gui_scale)))

    # ── 4b. Concentric inner arc (double-ring motif) ──
    arc_r2 = max(6, int(18 * gui_scale))
    arc_rect2 = pygame.Rect(arc_cx - arc_r2, arc_cy - arc_r2, arc_r2 * 2, arc_r2 * 2)
    pygame.draw.arc(surf, (*arc_color, 55), arc_rect2,
                    math.radians(220), math.radians(320),
                    max(1, int(1 * gui_scale)))

    # ── 5. Second arc (bottom-left, mirror) ──
    arc2_r = max(8, int(20 * gui_scale))
    arc2_cx = rx + int(22 * gui_scale)
    arc2_cy = ry + rh - int(18 * gui_scale)
    arc2_rect = pygame.Rect(arc2_cx - arc2_r, arc2_cy - arc2_r, arc2_r * 2, arc2_r * 2)
    pygame.draw.arc(surf, (*_MR_FAINT, 70), arc2_rect,
                    math.radians(20), math.radians(160),
                    max(1, int(1 * gui_scale)))

    # ── 6. Thin vertical accent line (left side, inset) ──
    vert_x = rx + int(6 * gui_scale)
    vert_y1 = div_y + int(10 * gui_scale)
    vert_y2 = ry + rh - int(28 * gui_scale)
    pygame.draw.line(surf, (*_MR_FAINT, 50),
                     (vert_x, vert_y1), (vert_x, vert_y2), 1)

    # ── 7. Short horizontal tick marks off the vertical accent ──
    tick_len = max(3, int(8 * gui_scale))
    num_ticks = 4
    if vert_y2 > vert_y1 + 20:
        tick_spacing = (vert_y2 - vert_y1) // max(1, num_ticks + 1)
        for i in range(1, num_ticks + 1):
            ty = vert_y1 + i * tick_spacing
            pygame.draw.line(surf, (*_MR_FAINT, 40),
                             (vert_x, ty), (vert_x + tick_len, ty), 1)

    # ── 8. Right-side thin bracket line (futuristic readout feel) ──
    bkt_x = rx + rw - int(8 * gui_scale)
    bkt_y1 = div_y + int(20 * gui_scale)
    bkt_y2 = ry + rh - int(40 * gui_scale)
    bkt_len = max(3, int(6 * gui_scale))
    pygame.draw.line(surf, (*_MR_FAINT, 40),
                     (bkt_x, bkt_y1), (bkt_x, bkt_y2), 1)
    # Top and bottom end-caps (horizontal)
    pygame.draw.line(surf, (*_MR_FAINT, 40),
                     (bkt_x - bkt_len, bkt_y1), (bkt_x, bkt_y1), 1)
    pygame.draw.line(surf, (*_MR_FAINT, 40),
                     (bkt_x - bkt_len, bkt_y2), (bkt_x, bkt_y2), 1)

    # ── 8b. Mini bar-graph readout (right bracket interior) ──
    bar_count = 5
    bar_max_w = max(6, int(14 * gui_scale))
    bar_h_each = max(2, int(3 * gui_scale))
    bar_gap = max(2, int(4 * gui_scale))
    bar_block_h = bar_count * (bar_h_each + bar_gap)
    bar_start_y = (bkt_y1 + bkt_y2) // 2 - bar_block_h // 2
    bar_x = bkt_x - bkt_len - bar_max_w - int(2 * gui_scale)
    # Deterministic "data" widths based on app name
    rng_seed = sum(ord(c) for c in app_name)
    for bi in range(bar_count):
        frac = ((rng_seed * (bi + 3) * 7 + 13) % 100) / 100.0
        bw = max(2, int(bar_max_w * (0.25 + 0.75 * frac)))
        by = bar_start_y + bi * (bar_h_each + bar_gap)
        bar_col = (*_MR_BLUE, 55) if is_selected else (*_MR_DIM, 40)
        pygame.draw.rect(surf, bar_col, (bar_x + bar_max_w - bw, by, bw, bar_h_each))

    # ── 9. Bottom divider line (thinner, separates status area) ──
    bot_div_y = ry + rh - int(24 * gui_scale)
    pygame.draw.line(surf, (*_MR_FAINT, 60),
                     (rx + line_inset, bot_div_y), (rx + rw - line_inset, bot_div_y), 1)

    # ── 10. Tiny corner dots (glass panel mounting points) ──
    dot_r = max(1, int(2 * gui_scale))
    dot_inset = max(6, int(10 * gui_scale))
    dot_col = (*_MR_DIM, 60)
    for dx, dy in [(rx + dot_inset, ry + dot_inset),
                   (rx + rw - dot_inset, ry + dot_inset),
                   (rx + dot_inset, ry + rh - dot_inset),
                   (rx + rw - dot_inset, ry + rh - dot_inset)]:
        pygame.draw.circle(surf, dot_col, (dx, dy), dot_r)

    # ── 10b. Corner bracket motifs (L-shaped accents at each corner) ──
    cb_len = max(6, int(14 * gui_scale))
    cb_inset = max(4, int(7 * gui_scale))
    cb_col = _MR_BLUE if is_selected else (*_MR_DIM, 80)
    # top-left
    pygame.draw.line(surf, cb_col, (rx + cb_inset, ry + cb_inset),
                     (rx + cb_inset + cb_len, ry + cb_inset), 1)
    pygame.draw.line(surf, cb_col, (rx + cb_inset, ry + cb_inset),
                     (rx + cb_inset, ry + cb_inset + cb_len), 1)
    # top-right
    pygame.draw.line(surf, cb_col, (rx + rw - cb_inset, ry + cb_inset),
                     (rx + rw - cb_inset - cb_len, ry + cb_inset), 1)
    pygame.draw.line(surf, cb_col, (rx + rw - cb_inset, ry + cb_inset),
                     (rx + rw - cb_inset, ry + cb_inset + cb_len), 1)
    # bottom-left
    pygame.draw.line(surf, cb_col, (rx + cb_inset, ry + rh - cb_inset),
                     (rx + cb_inset + cb_len, ry + rh - cb_inset), 1)
    pygame.draw.line(surf, cb_col, (rx + cb_inset, ry + rh - cb_inset),
                     (rx + cb_inset, ry + rh - cb_inset - cb_len), 1)
    # bottom-right
    pygame.draw.line(surf, cb_col, (rx + rw - cb_inset, ry + rh - cb_inset),
                     (rx + rw - cb_inset - cb_len, ry + rh - cb_inset), 1)
    pygame.draw.line(surf, cb_col, (rx + rw - cb_inset, ry + rh - cb_inset),
                     (rx + rw - cb_inset, ry + rh - cb_inset - cb_len), 1)

    # ── 11. App name in title zone ──
    title_size = max(10, int(22 * gui_scale))
    title_color = _MR_WHITE if is_selected else _MR_BLUE
    title_img = _render_text(app_name, title_size, title_color)
    surf.blit(title_img, (rx + line_inset,
                          ry + int(rh * 0.13) - title_img.get_height() // 2))

    # ── 11b. Thin signal-strength dots after title ──
    sig_x = rx + line_inset + title_img.get_width() + int(8 * gui_scale)
    sig_y = ry + int(rh * 0.13)
    sig_dot_r = max(1, int(2 * gui_scale))
    sig_gap = max(3, int(5 * gui_scale))
    sig_count = 3
    sig_filled = ((rng_seed * 3 + 7) % sig_count) + 1  # 1..3 dots "filled"
    for si in range(sig_count):
        sc = (*_MR_BLUE, 110) if si < sig_filled else (*_MR_FAINT, 40)
        pygame.draw.circle(surf, sc, (sig_x + si * sig_gap, sig_y), sig_dot_r)

    # ── 12. Glow ring behind icon letter ──
    body_center_y = div_y + (ry + rh - div_y) // 2
    icon_center_y = body_center_y - int(12 * gui_scale)
    glow_ring_r = max(20, int(46 * gui_scale))
    glow_ring_col = (*_MR_BLUE, 28) if is_selected else (*_MR_DIM, 18)
    pygame.draw.circle(surf, glow_ring_col, (cx, icon_center_y), glow_ring_r, max(1, int(2 * gui_scale)))
    # Inner halo (softer, filled)
    halo_r = max(14, int(32 * gui_scale))
    halo_col = (*_MR_GLASS, 50) if is_selected else (*_MR_GLASS, 30)
    pygame.draw.circle(surf, halo_col, (cx, icon_center_y), halo_r)

    # Large icon letter centred in body
    icon_size = max(24, int(100 * gui_scale))
    icon_color = _MR_WHITE if is_selected else (*_MR_BLUE[:3],)
    icon_img = _render_text(app_name[0], icon_size, icon_color)
    surf.blit(icon_img, icon_img.get_rect(center=(cx, icon_center_y)))

    # ── 13. Sub-label below icon ──
    sub_size = max(10, int(24 * gui_scale))
    sub_img = _render_text(app_name, sub_size, _MR_DIM)
    surf.blit(sub_img, sub_img.get_rect(center=(cx, body_center_y + int(36 * gui_scale))))

    # ── 13b. Faint waveform line below sub-label (signal motif) ──
    wave_y = body_center_y + int(52 * gui_scale)
    wave_x0 = rx + line_inset + int(10 * gui_scale)
    wave_x1 = rx + rw - line_inset - int(10 * gui_scale)
    wave_pts = []
    wave_steps = max(10, (wave_x1 - wave_x0) // 3)
    for wi in range(wave_steps):
        t = wi / max(1, wave_steps - 1)
        wx = wave_x0 + int(t * (wave_x1 - wave_x0))
        # Deterministic waveform from app name hash
        phase = rng_seed * 0.7 + wi * 0.9
        amp = max(2, int(6 * gui_scale))
        wy = wave_y + int(math.sin(phase) * amp * (0.3 + 0.7 * math.sin(wi * 0.4 + rng_seed)))
        wave_pts.append((wx, wy))
    wave_col = (*_MR_DIM, 45) if not is_selected else (*_MR_BLUE, 60)
    if len(wave_pts) > 1:
        pygame.draw.lines(surf, wave_col, False, wave_pts, 1)

    # ── 14. Status readout text bottom-left ──
    stat_size = max(8, int(12 * gui_scale))
    stat_text = f"{app_name[:3].upper()} ACTIVE"
    stat_img = _render_text(stat_text, stat_size, (*_MR_FAINT[:3],))
    stat_x = rx + line_inset
    stat_y = ry + rh - stat_img.get_height() - int(6 * gui_scale)
    surf.blit(stat_img, (stat_x, stat_y))

    # ── 14b. Tiny blinking-style status dot next to status text ──
    status_dot_x = stat_x + stat_img.get_width() + int(5 * gui_scale)
    status_dot_y = stat_y + stat_img.get_height() // 2
    status_dot_col = (*_MR_BLUE, 110) if is_selected else (*_MR_DIM, 70)
    pygame.draw.circle(surf, status_dot_col, (status_dot_x, status_dot_y), max(1, int(2 * gui_scale)))

    # ── 15. Small "ID" tag bottom-right ──
    id_text = f"ID:{ord(app_name[0]):03X}"
    id_img = _render_text(id_text, stat_size, (*_MR_FAINT[:3],))
    surf.blit(id_img, (rx + rw - id_img.get_width() - line_inset, stat_y))

    # ── 15b. Hex data readout above ID (fake telemetry) ──
    hex_data = f"{(rng_seed * 2731 + 12345) & 0xFFFF:04X}.{(rng_seed * 997) & 0xFF:02X}"
    hex_img = _render_text(hex_data, max(8, int(11 * gui_scale)), (*_MR_FAINT[:3],))
    surf.blit(hex_img, (rx + rw - hex_img.get_width() - line_inset,
                        stat_y - hex_img.get_height() - int(2 * gui_scale)))

    # ── 16. Thin rounded border ──
    border_color = _MR_BLUE if is_selected else _MR_DIM
    border_w = max(2, int(3 * gui_scale)) if is_selected else max(1, int(1 * gui_scale))
    pygame.draw.rect(surf, border_color, (rx, ry, rw, rh),
                     width=border_w, border_radius=br)

    # ── 17. Selection outer glow ──
    if is_selected:
        glow_expand = max(3, int(5 * gui_scale))
        glow_rect = (rx - glow_expand, ry - glow_expand,
                     rw + glow_expand * 2, rh + glow_expand * 2)
        glow_br = br + glow_expand
        pygame.draw.rect(surf, (*_MR_GLOW, 90), glow_rect,
                         width=max(2, int(3 * gui_scale)), border_radius=glow_br)

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

    # ── Panel body (semi-transparent) ──
    body_color = _ICE_PANEL_BG_SEL if is_selected else _ICE_PANEL_BG
    body_pts = [
        (rx, ry),
        (rx + rw - corner_cut, ry),
        (rx + rw, ry + corner_cut),
        (rx + rw, ry + rh),
        (rx + corner_cut, ry + rh),
        (rx, ry + rh - corner_cut),
    ]
    body_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
    body_alpha = 210 if is_selected else 185
    pygame.draw.polygon(body_surf, (*body_color, body_alpha), body_pts)
    surf.blit(body_surf, (0, 0))

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
    # Ice theme has pulsing dot animation — bucket time to ~8 fps so cache helps.
    # Sci-fi (Minority Report) and classic are fully static — no time dependency.
    if _theme_id == _THEME_ICE:
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
# HUD overlay — system data readouts (sci-fi theme only)
# ==============================
import platform as _platform
import datetime as _datetime

_hud_frame_times: list = []  # rolling FPS buffer
_hud_sys_info: dict | None = None


def _get_sys_info():
    """Cache system info strings (expensive calls, only do once)."""
    global _hud_sys_info
    if _hud_sys_info is not None:
        return _hud_sys_info
    _hud_sys_info = {
        "os": _platform.system().upper(),
        "arch": _platform.machine().upper(),
        "node": _platform.node().upper()[:16],
        "py": _platform.python_version(),
    }
    return _hud_sys_info


def draw_hud_overlay(surface, win_w, win_h, hand_detected=False, fps_clock=None):
    """Draw Minority-Report-style system HUD data around the screen edges.
    Only active on sci-fi theme. Designed to frame the cards without overlapping."""
    if _theme_id != _THEME_SCIFI:
        return

    now = _time.time()

    # ── FPS calculation ──
    _hud_frame_times.append(now)
    # Keep last 60 timestamps
    while len(_hud_frame_times) > 60:
        _hud_frame_times.pop(0)
    if len(_hud_frame_times) > 2:
        elapsed = _hud_frame_times[-1] - _hud_frame_times[0]
        fps = (len(_hud_frame_times) - 1) / max(0.001, elapsed)
    else:
        fps = 60.0

    sys_info = _get_sys_info()

    # ── Bottom-left: System readout panel ──
    bl_x, bl_y = 12, win_h - 130
    # Semi-transparent backing
    bl_panel = pygame.Surface((210, 118), pygame.SRCALPHA)
    pygame.draw.rect(bl_panel, (*_MR_GLASS, 55), (0, 0, 210, 118), border_radius=6)
    pygame.draw.rect(bl_panel, (*_MR_DIM, 40), (0, 0, 210, 118), width=1, border_radius=6)
    surface.blit(bl_panel, (bl_x, bl_y))

    # Header
    hdr = _render_text("SYS TELEMETRY", max(10, 13), _MR_DIM)
    surface.blit(hdr, (bl_x + 8, bl_y + 4))
    pygame.draw.line(surface, (*_MR_DIM, 60), (bl_x + 8, bl_y + 20), (bl_x + 200, bl_y + 20), 1)

    # Data rows
    rows = [
        f"OS     {sys_info['os']} {sys_info['arch']}",
        f"NODE   {sys_info['node']}",
        f"PYRT   {sys_info['py']}",
        f"FPS    {fps:5.1f}",
        f"RENDER PYGAME/SDL2",
    ]
    for i, txt in enumerate(rows):
        y = bl_y + 26 + i * 16
        col = _MR_BLUE if i == 3 else (*_MR_FAINT[:3],)
        img = _render_text(txt, max(9, 12), col)
        surface.blit(img, (bl_x + 10, y))

    # Live status dot
    dot_pulse = int(80 + 40 * math.sin(now * 3.0))
    pygame.draw.circle(surface, (*_MR_BLUE[:3], dot_pulse), (bl_x + 198, bl_y + 12), 3)

    # ── Bottom-right: Gesture status panel ──
    br_w, br_h = 190, 80
    br_x = win_w - br_w - 12
    br_y = win_h - br_h - 12
    br_panel = pygame.Surface((br_w, br_h), pygame.SRCALPHA)
    pygame.draw.rect(br_panel, (*_MR_GLASS, 55), (0, 0, br_w, br_h), border_radius=6)
    pygame.draw.rect(br_panel, (*_MR_DIM, 40), (0, 0, br_w, br_h), width=1, border_radius=6)
    surface.blit(br_panel, (br_x, br_y))

    ghdr = _render_text("GESTURE ENGINE", max(10, 13), _MR_DIM)
    surface.blit(ghdr, (br_x + 8, br_y + 4))
    pygame.draw.line(surface, (*_MR_DIM, 60), (br_x + 8, br_y + 20), (br_x + br_w - 10, br_y + 20), 1)

    tracking_text = "TRACKING" if hand_detected else "STANDBY"
    tracking_col = (100, 220, 160) if hand_detected else _MR_FAINT
    t_img = _render_text(f"STATUS  {tracking_text}", max(9, 12), tracking_col)
    surface.blit(t_img, (br_x + 10, br_y + 28))

    mode_img = _render_text("MODE    CAROUSEL", max(9, 12), (*_MR_FAINT[:3],))
    surface.blit(mode_img, (br_x + 10, br_y + 44))

    latency_ms = 1000.0 / max(1, fps)
    lat_img = _render_text(f"LATENCY {latency_ms:5.1f}ms", max(9, 12), (*_MR_FAINT[:3],))
    surface.blit(lat_img, (br_x + 10, br_y + 60))

    # Status dot
    if hand_detected:
        pygame.draw.circle(surface, (100, 220, 160, 160), (br_x + br_w - 12, br_y + 12), 3)
    else:
        blink = 120 if int(now * 2) % 2 == 0 else 40
        pygame.draw.circle(surface, (*_MR_DIM[:3], blink), (br_x + br_w - 12, br_y + 12), 3)

    # ── Top-center: Clock + date readout ──
    dt_now = _datetime.datetime.now()
    time_str = dt_now.strftime("%H:%M:%S")
    date_str = dt_now.strftime("%Y.%m.%d")

    time_img = _render_text(time_str, max(14, 20), _MR_WHITE)
    date_img = _render_text(date_str, max(10, 14), _MR_DIM)
    total_w = time_img.get_width() + 12 + date_img.get_width()

    # Don't overlap the camera thumbnail (top-right) or theme button (top-left)
    tc_x = win_w // 2 - total_w // 2
    tc_y = 10
    # Small backing strip
    strip_w = total_w + 24
    strip_h = max(time_img.get_height(), date_img.get_height()) + 8
    strip_surf = pygame.Surface((strip_w, strip_h), pygame.SRCALPHA)
    pygame.draw.rect(strip_surf, (*_MR_GLASS, 40), (0, 0, strip_w, strip_h), border_radius=4)
    surface.blit(strip_surf, (tc_x - 12, tc_y - 4))

    surface.blit(time_img, (tc_x, tc_y))
    surface.blit(date_img, (tc_x + time_img.get_width() + 12,
                            tc_y + time_img.get_height() - date_img.get_height()))

    # Thin decorative lines flanking the clock
    flank_y = tc_y + strip_h // 2
    flank_len = 40
    pygame.draw.line(surface, (*_MR_DIM, 50),
                     (tc_x - 18, flank_y), (tc_x - 18 - flank_len, flank_y), 1)
    pygame.draw.line(surface, (*_MR_DIM, 50),
                     (tc_x + total_w + 6, flank_y),
                     (tc_x + total_w + 6 + flank_len, flank_y), 1)
    # Tiny end dots
    pygame.draw.circle(surface, (*_MR_DIM, 60), (tc_x - 18 - flank_len, flank_y), 2)
    pygame.draw.circle(surface, (*_MR_DIM, 60), (tc_x + total_w + 6 + flank_len, flank_y), 2)

    # ── Left edge: Vertical data stream (scrolling hex/binary snippets) ──
    stream_x = 14
    stream_y0 = 50
    stream_y1 = win_h - 150
    stream_count = 12
    stream_spacing = (stream_y1 - stream_y0) // max(1, stream_count)
    for si in range(stream_count):
        # Each line scrolls: offset by time so they change
        offset = int(now * 0.5 + si * 1.7) % 99999
        hex_val = f"{(offset * 48271 + si * 1013) & 0xFFFFFF:06X}"
        sy = stream_y0 + si * stream_spacing
        s_img = _render_text(hex_val, max(8, 10), (*_MR_FAINT[:3],))
        surface.blit(s_img, (stream_x, sy))

    # Thin vertical guide line next to the stream
    pygame.draw.line(surface, (*_MR_FAINT, 30),
                     (stream_x + 48, stream_y0 - 4),
                     (stream_x + 48, stream_y1 + 12), 1)

    # ── Right edge: Animated signal bars ──
    sig_x = win_w - 30
    sig_y0 = 180
    sig_bar_count = 16
    sig_bar_h = 2
    sig_bar_gap = 8
    sig_bar_max_w = 18
    for si in range(sig_bar_count):
        sy = sig_y0 + si * (sig_bar_h + sig_bar_gap)
        # Animated width based on time + position
        phase = now * 1.5 + si * 0.6
        frac = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(phase))
        bw = int(sig_bar_max_w * frac)
        bar_alpha = int(30 + 25 * frac)
        pygame.draw.rect(surface, (*_MR_DIM[:3], bar_alpha),
                         (sig_x - bw, sy, bw, sig_bar_h))

    # ── Bottom-center: Category indicator label ──
    cat_label = _render_text("▸ CAROUSEL INTERFACE ACTIVE", max(9, 12), (*_MR_DIM[:3],))
    cat_x = win_w // 2 - cat_label.get_width() // 2
    cat_y = win_h - 18
    surface.blit(cat_label, (cat_x, cat_y))


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
