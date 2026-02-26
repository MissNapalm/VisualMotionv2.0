"""
Eye-Tracking Launcher — adaptive tile grid controlled by
gaze (mouse) and blink activation (Z key).

  Mouse position  →  gaze cursor
  Z key tap       →  select / activate tile
  Escape          →  quit (or close open app)

Zoom in  → tiles grow, grid shrinks from 9 → 6 → 3
Zoom out → tiles shrink, grid grows from 3 → 6 → 9
"Next" button at bottom pages through when there are more apps than fit.
"""

import math
import time

import pygame

from state import HandState, WINDOW_WIDTH, WINDOW_HEIGHT
from renderer import (
    clamp, draw_app_icon, draw_theme_button, theme_button_hit,
    toggle_theme, get_bg_color, draw_helix_graph, is_ice_theme,
    draw_stars_bg, draw_hex_rain, draw_hud_overlay, draw_sysmon_bg,
)
from weather_window import WeatherWindow
from todo_window import TodoWindow
from sand_window import SandWindow
from files_window import FilesWindow
from monitor_window import MonitorWindow
from netscan_window import NetScanWindow


# ── All apps ──────────────────────────────────────────────────────
ALL_APPS = [
    "Weather",  "Reminders", "Sand",
    "Files",    "Monitor",   "NetScan",
    "Mail",     "Music",     "Browser",
    "Messages", "Calendar",  "Camera",
    "Photos",   "Notes",     "YouTube",
    "Netflix",  "Twitch",    "Spotify",
    "Podcasts", "Books",     "Games",
]
# Tile sizing — computed at runtime in __init__ to fill the screen
TILE_SIZE  = 220   # default, overridden at init
TILE_GAP   = 26    # default, overridden at init
_MARGIN_Y  = 46    # vertical margin for zoom buttons + Next btn




# ── Gaze cursor colours ──────────────────────────────────────────
_CURSOR_IDLE   = (160, 190, 220, 180)
_CURSOR_ACTIVE = (220, 240, 255, 240)
_CURSOR_RING   = (90, 130, 170, 100)

# ── Zoom dwell-button styling ────────────────────────────────────
_ZB_SIZE     = 122
_ZB_MARGIN   = 18
_ZB_DWELL    = 0.4
_ZB_RATE     = 0.6
_ZB_BG       = (12, 18, 30)
_ZB_RIM_IDLE = (60, 85, 115)
_ZB_RIM_HOT  = (120, 160, 200)
_ZB_TEXT     = (200, 215, 230)
_ZB_FILL     = (120, 160, 200)

# ── "Next" button styling ────────────────────────────────────────
_NB_WIDTH    = 260
_NB_HEIGHT   = 54
_NB_MARGIN   = 28


# ── Adaptive grid helpers ────────────────────────────────────────
def _grid_layout(gui_scale, scr_w, scr_h):
    """Return (cols, rows, per_page) that fit on screen at current scale.

    Always uses 3 columns; rows shrink from 3 → 2 → 1 as tiles grow.
    """
    tw = int(TILE_SIZE * gui_scale)
    gap = int(TILE_GAP * gui_scale)
    usable_h = scr_h - _MARGIN_Y * 2
    # how many rows fit?
    if tw <= 0:
        rows = 3
    else:
        rows = max(1, (usable_h + gap) // (tw + gap))
    rows = min(rows, 3)         # cap at 3×3
    cols = 3
    return cols, rows, cols * rows


def _total_pages(per_page):
    return max(1, math.ceil(len(ALL_APPS) / max(1, per_page)))


class EyeTrackingApp:
    """Adaptive tile launcher with dwell zoom."""

    def __init__(self):
        pygame.init()

        # ── Fullscreen ──
        import state as _state_mod
        disp_info = pygame.display.Info()
        _state_mod.WINDOW_WIDTH = disp_info.current_w
        _state_mod.WINDOW_HEIGHT = disp_info.current_h
        global WINDOW_WIDTH, WINDOW_HEIGHT
        WINDOW_WIDTH = _state_mod.WINDOW_WIDTH
        WINDOW_HEIGHT = _state_mod.WINDOW_HEIGHT


        # ── Auto-size tiles to fill ~80% of screen at 1.0x zoom ──
        global TILE_SIZE, TILE_GAP
        usable_h = WINDOW_HEIGHT - _MARGIN_Y * 2
        # ts from height: 3*ts + 2*gap = usable_h, gap ~ ts*0.11
        # 3*ts + 2*(ts*0.11) = usable_h → ts*(3.22) = usable_h
        ts_h = usable_h / 3.22
        # ts from width: 3*ts + 2*(ts*0.11) = W*0.82
        ts_w = (WINDOW_WIDTH * 0.82) / 3.22
        TILE_SIZE = int(min(ts_w, ts_h))
        TILE_GAP  = max(8, int(TILE_SIZE * 0.11))
        try:
            self.screen = pygame.display.set_mode(
                (WINDOW_WIDTH, WINDOW_HEIGHT),
                pygame.FULLSCREEN | pygame.DOUBLEBUF | pygame.SCALED,
                vsync=1,
            )
        except Exception:
            self.screen = pygame.display.set_mode(
                (WINDOW_WIDTH, WINDOW_HEIGHT),
                pygame.FULLSCREEN | pygame.DOUBLEBUF,
            )
        pygame.display.set_caption("Eye Tracking Launcher")
        self.clock = pygame.time.Clock()
        self._last_frame_time = time.time()

        # ── Audio ──
        pygame.mixer.init()
        try:
            self._snd_select = pygame.mixer.Sound("select.mp3")
            self._snd_select.set_volume(0.5)
        except Exception:
            self._snd_select = None
        try:
            self._snd_open = pygame.mixer.Sound("doublepinch.mp3")
            self._snd_open.set_volume(0.5)
        except Exception:
            self._snd_open = None

        # ── State ──
        self.state = HandState()
        self._tap = None

        # ── App windows ──
        self._weather = WeatherWindow(WINDOW_WIDTH, WINDOW_HEIGHT)
        self._todo = TodoWindow(WINDOW_WIDTH, WINDOW_HEIGHT)
        self._sand = SandWindow(WINDOW_WIDTH, WINDOW_HEIGHT)
        self._files = FilesWindow(WINDOW_WIDTH, WINDOW_HEIGHT)
        self._monitor = MonitorWindow(WINDOW_WIDTH, WINDOW_HEIGHT)
        self._netscan = NetScanWindow(WINDOW_WIDTH, WINDOW_HEIGHT)

        # ── Gaze / input ──
        self._gaze_x = WINDOW_WIDTH // 2
        self._gaze_y = WINDOW_HEIGHT // 2
        self._pinch_active = False
        self._pinch_prev = False
        self._pinch_start_pos = None
        self._pinch_start_time = 0.0
        self._last_pinch_x = None
        self._last_pinch_y = None
        self._sand_btn_consumed = False

        # ── Page state ──
        self._current_page = 0

        # ── Zoom dwell buttons ──
        self._zoom_dwell_start = None
        self._zoom_dwell_which = None

    # ── helpers ────────────────────────────────────────────────────
    @property
    def _any_app_visible(self):
        return (self._weather.visible or self._todo.visible or
                self._sand.visible or self._files.visible or
                self._monitor.visible or self._netscan.visible)

    def _current_layout(self):
        """Return (cols, rows, per_page) for the current gui_scale."""
        return _grid_layout(self.state.gui_scale,
                            WINDOW_WIDTH, WINDOW_HEIGHT)

    def _page_apps(self):
        """Return the list of app names for the current page."""
        _, _, per_page = self._current_layout()
        # clamp page so it stays valid when per_page changes
        tp = _total_pages(per_page)
        if self._current_page >= tp:
            self._current_page = tp - 1
        start = self._current_page * per_page
        return ALL_APPS[start:start + per_page]

    def _tile_rects(self, gui_scale):
        """Return list of (center_x, center_y, w, h, page_idx)."""
        apps = self._page_apps()
        cols, rows, _ = self._current_layout()
        tw = int(TILE_SIZE * gui_scale)
        th = int(TILE_SIZE * gui_scale)
        gap = int(TILE_GAP * gui_scale)
        count = len(apps)
        actual_rows = math.ceil(count / cols) if cols else 1
        total_w = cols * tw + (cols - 1) * gap
        total_h = actual_rows * th + (actual_rows - 1) * gap
        ox = (WINDOW_WIDTH - total_w) // 2
        oy = (WINDOW_HEIGHT - total_h) // 2 - int(20 * gui_scale)
        rects = []
        for idx in range(count):
            col = idx % cols
            row = idx // cols
            x = ox + col * (tw + gap) + tw // 2
            y = oy + row * (th + gap) + th // 2
            rects.append((x, y, tw, th, idx))
        return rects

    def _next_button_rect(self, gui_scale):
        """Return the rect for the Next page button at the bottom."""
        tiles = self._tile_rects(gui_scale)
        if not tiles:
            bot_y = WINDOW_HEIGHT // 2
        else:
            bot_y = max(cy + th // 2 for (cx, cy, tw, th, _) in tiles)
        bw = int(_NB_WIDTH * gui_scale)
        bh = int(_NB_HEIGHT * gui_scale)
        bx = WINDOW_WIDTH // 2 - bw // 2
        by = bot_y + int(_NB_MARGIN * gui_scale)
        return pygame.Rect(bx, by, bw, bh)

    # ── Zoom button rects ─────────────────────────────────────────
    def _zoom_button_rects(self):
        s = _ZB_SIZE
        m = _ZB_MARGIN
        plus_rect  = pygame.Rect(m, m, s, s)
        minus_rect = pygame.Rect(WINDOW_WIDTH - m - s, m, s, s)
        return minus_rect, plus_rect

    # ── Zoom dwell logic ──────────────────────────────────────────
    def _update_zoom_dwell(self, dt):
        gx, gy = self._gaze_x, self._gaze_y
        minus_r, plus_r = self._zoom_button_rects()
        st = self.state

        on_plus  = plus_r.collidepoint(gx, gy)
        on_minus = minus_r.collidepoint(gx, gy)

        if on_plus:
            which = "plus"
        elif on_minus:
            which = "minus"
        else:
            which = None

        if which != self._zoom_dwell_which:
            self._zoom_dwell_which = which
            self._zoom_dwell_start = time.time() if which else None
            return

        if which is None:
            return

        elapsed = time.time() - self._zoom_dwell_start
        if elapsed >= _ZB_DWELL:
            delta = _ZB_RATE * dt
            if which == "plus":
                st.gui_scale_target = min(st.gui_scale_max,
                                          st.gui_scale_target + delta)
            else:
                st.gui_scale_target = max(st.gui_scale_min,
                                          st.gui_scale_target - delta)

    # ── Draw zoom buttons ─────────────────────────────────────────
    def _draw_zoom_buttons(self, screen):
        minus_r, plus_r = self._zoom_button_rects()
        gx, gy = self._gaze_x, self._gaze_y
        now = time.time()
        st = self.state

        for rect, label, is_plus in [(plus_r, "+", True), (minus_r, "−", False)]:
            hovered = rect.collidepoint(gx, gy)
            which = "plus" if is_plus else "minus"

            progress = 0.0
            if (hovered and self._zoom_dwell_which == which
                    and self._zoom_dwell_start is not None):
                progress = min(1.0, (now - self._zoom_dwell_start) / _ZB_DWELL)

            active = progress >= 1.0

            # Background
            btn = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            bg_alpha = 140 if hovered else 80
            pygame.draw.rect(btn, (*_ZB_BG, bg_alpha),
                             (0, 0, rect.w, rect.h), border_radius=8)

            # Rim
            rim_col = _ZB_RIM_HOT if hovered else _ZB_RIM_IDLE
            rim_alpha = 200 if active else (160 if hovered else 90)
            pygame.draw.rect(btn, (*rim_col, rim_alpha),
                             (0, 0, rect.w, rect.h), width=2, border_radius=8)

            # Dwell progress arc
            if 0 < progress < 1.0:
                arc_r = rect.w // 2 - 4
                acx, acy = rect.w // 2, rect.h // 2
                end_angle = -math.pi / 2 + progress * 2 * math.pi
                start_angle = -math.pi / 2
                steps = max(4, int(progress * 32))
                for i in range(steps):
                    a1 = start_angle + (end_angle - start_angle) * i / steps
                    a2 = start_angle + (end_angle - start_angle) * (i + 1) / steps
                    x1 = acx + int(arc_r * math.cos(a1))
                    y1 = acy + int(arc_r * math.sin(a1))
                    x2 = acx + int(arc_r * math.cos(a2))
                    y2 = acy + int(arc_r * math.sin(a2))
                    pygame.draw.line(btn, (*_ZB_FILL, 200), (x1, y1), (x2, y2), 2)

            # Active glow
            if active:
                pulse = 0.7 + 0.3 * math.sin(now * 6)
                glow_alpha = int(60 * pulse)
                pygame.draw.rect(btn, (*_ZB_RIM_HOT, glow_alpha),
                                 (0, 0, rect.w, rect.h), width=3, border_radius=8)

            screen.blit(btn, rect.topleft)

            # Label
            font_size = 56
            try:
                font = pygame.font.Font(None, font_size)
            except Exception:
                font = pygame.font.SysFont(None, font_size)
            text_col = _ZB_TEXT if hovered else _ZB_RIM_IDLE
            text_img = font.render(label, True, text_col)
            tx = rect.centerx - text_img.get_width() // 2
            ty = rect.centery - text_img.get_height() // 2
            screen.blit(text_img, (tx, ty))

            # Scale readout
            if active:
                scale_text = f"{st.gui_scale_target:.2f}x"
                small_font = pygame.font.Font(None, 26)
                scale_img = small_font.render(scale_text, True, _ZB_RIM_HOT)
                screen.blit(scale_img, (rect.centerx - scale_img.get_width() // 2,
                                        rect.bottom + 4))

    # ── Draw "Next" page button ───────────────────────────────────
    def _draw_next_button(self, screen, gui_scale):
        """Draw the Next page button at the bottom of the tile grid."""
        _, _, per_page = self._current_layout()
        tp = _total_pages(per_page)
        if tp <= 1:
            return  # everything fits on one page

        rect = self._next_button_rect(gui_scale)
        gx, gy = self._gaze_x, self._gaze_y
        hovered = rect.collidepoint(gx, gy)

        btn = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg_alpha = 140 if hovered else 70
        pygame.draw.rect(btn, (*_ZB_BG, bg_alpha),
                         (0, 0, rect.w, rect.h), border_radius=10)
        rim_col = _ZB_RIM_HOT if hovered else _ZB_RIM_IDLE
        rim_alpha = 180 if hovered else 70
        pygame.draw.rect(btn, (*rim_col, rim_alpha),
                         (0, 0, rect.w, rect.h), width=2, border_radius=10)
        screen.blit(btn, rect.topleft)

        # Label  —  show grid layout + page
        _, rows, _ = self._current_layout()
        page_num = self._current_page + 1
        grid_label = f"{3}x{rows}"
        label = f"NEXT  ›  {page_num}/{tp}  [{grid_label}]"
        font_size = max(18, int(24 * gui_scale))
        try:
            font = pygame.font.Font(None, font_size)
        except Exception:
            font = pygame.font.SysFont(None, font_size)
        text_col = _ZB_TEXT if hovered else _ZB_RIM_IDLE
        text_img = font.render(label, True, text_col)
        tx = rect.centerx - text_img.get_width() // 2
        ty = rect.centery - text_img.get_height() // 2
        screen.blit(text_img, (tx, ty))

    # ── Pinch (Z-key) processing ──────────────────────────────────
    def _process_pinch(self):
        st = self.state
        px, py = float(self._gaze_x), float(self._gaze_y)
        pinch_now = self._pinch_active

        if pinch_now and not self._pinch_prev:
            self._pinch_start_pos = (px, py)
            self._pinch_start_time = time.time()
            self._last_pinch_x, self._last_pinch_y = px, py
            st.is_pinching = True
            st.pinch_hold_start = time.time()
            if self._sand.visible and self._sand._in_ui_zone(px, py):
                self._sand.handle_tap(px, py)
                self._sand_btn_consumed = True
            else:
                self._sand_btn_consumed = False

        elif pinch_now and self._pinch_prev:
            if (self._any_app_visible and not self._sand.visible
                    and not self._files.visible and not self._monitor.visible
                    and not self._netscan.visible
                    and self._pinch_start_pos):
                if not (self._todo.visible and self._todo._keyboard_open):
                    total = math.hypot(px - self._pinch_start_pos[0],
                                       py - self._pinch_start_pos[1])
                    if total <= 80 and time.time() - self._pinch_start_time >= 1.0:
                        if self._weather.visible:
                            self._weather.close()
                        elif self._todo.visible:
                            self._todo.close()
                        self._pinch_prev = False
                        self._pinch_active = False
                        st.is_pinching = False
                        return

            if self._sand.visible and self._pinch_start_pos:
                total = math.hypot(px - self._pinch_start_pos[0],
                                   py - self._pinch_start_pos[1])
                if total > 8:
                    self._sand.handle_pinch(px, py)

            if self._files.visible and self._pinch_start_pos:
                total = math.hypot(px - self._pinch_start_pos[0],
                                   py - self._pinch_start_pos[1])
                if total > 8:
                    self._files.handle_pinch_drag(px, py, st.gui_scale)

            if self._monitor.visible and self._pinch_start_pos:
                total = math.hypot(px - self._pinch_start_pos[0],
                                   py - self._pinch_start_pos[1])
                if total > 8:
                    self._monitor.handle_pinch_drag(px, py, st.gui_scale)

            if self._netscan.visible and self._pinch_start_pos:
                total = math.hypot(px - self._pinch_start_pos[0],
                                   py - self._pinch_start_pos[1])
                if total > 8:
                    self._netscan.handle_pinch_drag(px, py, st.gui_scale)

            self._last_pinch_x, self._last_pinch_y = px, py

        elif not pinch_now and self._pinch_prev:
            if self._pinch_start_pos and self._last_pinch_x is not None:
                total = math.hypot(
                    self._last_pinch_x - self._pinch_start_pos[0],
                    self._last_pinch_y - self._pinch_start_pos[1],
                )
                if total <= st.movement_threshold:
                    if self._sand.visible and self._sand_btn_consumed:
                        pass
                    else:
                        self._tap = (self._last_pinch_x, self._last_pinch_y)
            st.is_pinching = False
            self._pinch_start_pos = None
            self._last_pinch_x = None
            self._last_pinch_y = None
            if self._sand.visible:
                self._sand.handle_pinch_end()
            if self._files.visible:
                self._files.handle_pinch_drag_end()
            if self._monitor.visible:
                self._monitor.handle_pinch_drag_end()
            if self._netscan.visible:
                self._netscan.handle_pinch_drag_end()

        self._pinch_prev = pinch_now

    # ── Tap resolution ────────────────────────────────────────────
    def _resolve_taps(self, tile_data):
        st = self.state
        if not self._tap:
            return
        tx, ty = self._tap
        self._tap = None

        if self._todo.visible:
            self._todo.handle_tap(tx, ty, st.gui_scale)
        elif self._weather.visible:
            if not self._weather.hit_test(tx, ty, st.gui_scale):
                self._weather.close()
        elif self._sand.visible:
            self._sand.handle_tap(tx, ty)
        elif self._files.visible:
            self._files.handle_tap(tx, ty, st.gui_scale)
        elif self._monitor.visible:
            self._monitor.handle_tap(tx, ty, st.gui_scale)
        elif self._netscan.visible:
            self._netscan.handle_tap(tx, ty, st.gui_scale)
        else:
            # Check "Next" button first
            _, _, per_page = self._current_layout()
            tp = _total_pages(per_page)
            next_r = self._next_button_rect(st.gui_scale)
            if tp > 1 and next_r.collidepoint(tx, ty):
                self._current_page = (self._current_page + 1) % tp
                if self._snd_select:
                    self._snd_select.play()
                return

            # Check grid tiles
            page_apps = self._page_apps()
            for cx, cy, tw, th, idx in tile_data:
                rect = pygame.Rect(cx - tw // 2, cy - th // 2, tw, th)
                if rect.collidepoint(tx, ty) and idx < len(page_apps):
                    name = page_apps[idx]
                    if self._snd_select:
                        self._snd_select.play()
                    self._open_app(name)
                    break

    def _open_app(self, name):
        snd = self._snd_open
        if name == "Weather":
            self._weather.open()
            if snd: snd.play()
        elif name == "Reminders":
            self._todo.open()
            if snd: snd.play()
        elif name == "Sand":
            self._sand.open()
            if snd: snd.play()
        elif name == "Files":
            self._files.open()
            if snd: snd.play()
        elif name == "Monitor":
            self._monitor.open()
            if snd: snd.play()
        elif name == "NetScan":
            self._netscan.open()
            if snd: snd.play()
        # Other apps are placeholders — no window yet

    # ── Gaze cursor ───────────────────────────────────────────────
    def _draw_gaze_cursor(self, screen):
        gx, gy = int(self._gaze_x), int(self._gaze_y)
        now = time.time()

        if self._pinch_active:
            ring_r = 16
            ring_surf = pygame.Surface((ring_r * 2 + 4, ring_r * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(ring_surf, _CURSOR_ACTIVE,
                               (ring_r + 2, ring_r + 2), ring_r, 2)
            screen.blit(ring_surf, (gx - ring_r - 2, gy - ring_r - 2))
            pygame.draw.circle(screen, (220, 240, 255), (gx, gy), 4)
            ch = 8
            pygame.draw.line(screen, (200, 220, 240),
                             (gx - ch, gy), (gx - 5, gy), 1)
            pygame.draw.line(screen, (200, 220, 240),
                             (gx + 5, gy), (gx + ch, gy), 1)
            pygame.draw.line(screen, (200, 220, 240),
                             (gx, gy - ch), (gx, gy - 5), 1)
            pygame.draw.line(screen, (200, 220, 240),
                             (gx, gy + 5), (gx, gy + ch), 1)
        else:
            pulse = 0.7 + 0.3 * math.sin(now * 2.5)
            ring_r = int(12 + 3 * pulse)
            ring_surf = pygame.Surface((ring_r * 2 + 4, ring_r * 2 + 4), pygame.SRCALPHA)
            alpha = int(80 * pulse)
            pygame.draw.circle(ring_surf, (*_CURSOR_RING[:3], alpha),
                               (ring_r + 2, ring_r + 2), ring_r, 2)
            screen.blit(ring_surf, (gx - ring_r - 2, gy - ring_r - 2))
            dot_surf = pygame.Surface((8, 8), pygame.SRCALPHA)
            pygame.draw.circle(dot_surf, (*_CURSOR_IDLE[:3], int(160 * pulse)), (4, 4), 3)
            screen.blit(dot_surf, (gx - 4, gy - 4))

    # ── Main draw ─────────────────────────────────────────────────
    def _draw(self, dt):
        st = self.state
        screen = self.screen
        screen.fill(get_bg_color())
        draw_stars_bg(screen)
        draw_hex_rain(screen, WINDOW_WIDTH, WINDOW_HEIGHT)
        draw_sysmon_bg(screen, WINDOW_WIDTH, WINDOW_HEIGHT)

        # Smooth zoom interpolation
        zoom_sm = 1.0 - (1.0 - 0.12) ** (dt * 60.0)
        st.gui_scale += (st.gui_scale_target - st.gui_scale) * zoom_sm

        tile_data = []

        if self._sand.visible:
            self._sand.draw(screen, st.gui_scale)
        elif self._todo.visible:
            self._todo.draw(screen, st.gui_scale)
        elif self._weather.visible:
            self._weather.draw(screen, st.gui_scale)
        elif self._files.visible:
            self._files.draw(screen, st.gui_scale)
        elif self._monitor.visible:
            self._monitor.draw(screen, st.gui_scale)
        elif self._netscan.visible:
            self._netscan.draw(screen, st.gui_scale)
        else:
            # ── Draw adaptive tile grid for current page ──
            tile_data = self._tile_rects(st.gui_scale)
            page_apps = self._page_apps()
            gx, gy = self._gaze_x, self._gaze_y
            for cx, cy, tw, th, idx in tile_data:
                if idx >= len(page_apps):
                    break
                name = page_apps[idx]
                rect = pygame.Rect(cx - tw // 2, cy - th // 2, tw, th)
                is_hovered = rect.collidepoint(gx, gy)
                draw_app_icon(screen, name, cx, cy,
                              TILE_SIZE, TILE_SIZE,
                              is_selected=is_hovered,
                              zoom_scale=1.0 + (0.08 if is_hovered else 0.0),
                              gui_scale=st.gui_scale)

            # ── Next button ──
            self._draw_next_button(screen, st.gui_scale)

        if not self._any_app_visible:
            if is_ice_theme():
                draw_helix_graph(screen, WINDOW_WIDTH, WINDOW_HEIGHT)
            draw_hud_overlay(screen, WINDOW_WIDTH, WINDOW_HEIGHT, hand_detected=True)
            draw_theme_button(screen)

        # ── Zoom dwell buttons (always visible) ──
        self._draw_zoom_buttons(screen)

        self._resolve_taps(tile_data)
        self._draw_gaze_cursor(screen)
        pygame.display.flip()

    # ── Main loop ─────────────────────────────────────────────────
    def run(self):
        print("=" * 50)
        print("EYE TRACKING LAUNCHER")
        print("Mouse = gaze | Z = select | Esc = quit/close")
        print("Zoom in: 9 → 6 → 3 tiles | Zoom out: 3 → 6 → 9")
        print("=" * 50)
        st = self.state

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return

                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if self._sand.visible:
                        self._sand.close()
                    elif self._weather.visible:
                        self._weather.close()
                    elif self._todo.visible:
                        self._todo.close()
                    elif self._files.visible:
                        self._files.close()
                    elif self._monitor.visible:
                        self._monitor.close()
                    elif self._netscan.visible:
                        self._netscan.close()
                    else:
                        pygame.quit()
                        return

                # Z key = pinch
                if event.type == pygame.KEYDOWN and event.key == pygame.K_z:
                    self._pinch_active = True
                if event.type == pygame.KEYUP and event.key == pygame.K_z:
                    self._pinch_active = False

                # Sand keyboard controls
                if self._sand.visible:
                    if event.type == pygame.KEYDOWN:
                        self._sand.handle_key(event.key, True)
                    elif event.type == pygame.KEYUP:
                        self._sand.handle_key(event.key, False)

                # Scroll wheel → pass to open app
                if event.type == pygame.MOUSEWHEEL:
                    if self._sand.visible:
                        self._sand.handle_scroll(-event.y)
                    elif self._files.visible:
                        self._files.handle_scroll(-event.y)
                    elif self._monitor.visible:
                        self._monitor.handle_scroll(-event.y)
                    elif self._netscan.visible:
                        self._netscan.handle_scroll(-event.y)

                # Mouse click fallback for theme button
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    if not self._any_app_visible and theme_button_hit(mx, my):
                        toggle_theme()

            # Mouse position = gaze
            self._gaze_x, self._gaze_y = pygame.mouse.get_pos()

            # Delta time
            now = time.time()
            dt = min(now - self._last_frame_time, 0.05)
            self._last_frame_time = now

            # Zoom dwell
            self._update_zoom_dwell(dt)

            # Process pinch state machine
            self._process_pinch()

            # Draw
            self._draw(dt)
            self.clock.tick(60)


if __name__ == "__main__":
    EyeTrackingApp().run()
