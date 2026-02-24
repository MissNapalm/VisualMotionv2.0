"""
System Monitor – live process list, CPU / memory gauges, animated graphs,
network throughput, disk usage, uptime.  All data is real (via psutil-free
stdlib calls on macOS).

Themed with theme_chrome angular HUD styling.
"""
import math
import os
import platform
import subprocess
import time

import pygame
import theme_chrome as tc

# ── Colours ─────────────────────────────────────────────────────────
_BG       = (14, 14, 24)
_PANEL    = (22, 22, 38)
_WHITE    = (255, 255, 255)
_GRAY     = (140, 140, 160)
_DIM      = (80, 80, 100)
_GREEN    = (0, 230, 120)
_YELLOW   = (255, 220, 60)
_RED      = (255, 60, 60)
_CYAN     = (0, 220, 220)
_ORANGE   = (255, 140, 40)
_PURPLE   = (180, 100, 255)
_BLUE     = (60, 140, 255)

# ── Font cache ──────────────────────────────────────────────────────
_fc: dict[int, pygame.font.Font] = {}


def _f(sz: int) -> pygame.font.Font:
    sz = max(10, sz)
    if sz not in _fc:
        _fc[sz] = pygame.font.Font(None, sz)
    return _fc[sz]


# ── Data helpers (macOS, no psutil needed) ──────────────────────────
def _cpu_percent() -> float:
    """Return overall CPU usage 0-100 (fast, cached subprocess)."""
    try:
        out = subprocess.check_output(
            ["top", "-l", "1", "-n", "0", "-s", "0"],
            stderr=subprocess.DEVNULL, timeout=3
        ).decode()
        for line in out.splitlines():
            if "CPU usage" in line:
                # "CPU usage: 12.5% user, 8.2% sys, 79.2% idle"
                parts = line.split(",")
                for p in parts:
                    if "idle" in p:
                        idle = float(p.strip().split("%")[0].split()[-1])
                        return round(100.0 - idle, 1)
        return 0.0
    except Exception:
        return 0.0


def _mem_info() -> tuple[float, float, float]:
    """Return (used_GB, total_GB, percent)."""
    try:
        import ctypes, ctypes.util
        libc = ctypes.CDLL(ctypes.util.find_library("c"))
        # sysctl hw.memsize
        out = subprocess.check_output(
            ["sysctl", "-n", "hw.memsize"],
            stderr=subprocess.DEVNULL, timeout=2,
        ).decode().strip()
        total_bytes = int(out)
        total_gb = total_bytes / (1024 ** 3)
        # vm_stat for pages free / active / inactive / speculative / wired
        vm = subprocess.check_output(
            ["vm_stat"], stderr=subprocess.DEVNULL, timeout=2
        ).decode()
        page_size = 16384  # Apple Silicon default
        for line in vm.splitlines():
            if "page size of" in line:
                page_size = int(line.split()[-2])
                break
        pages_free = 0
        pages_inactive = 0
        for line in vm.splitlines():
            if "Pages free" in line:
                pages_free = int(line.split()[-1].rstrip("."))
            elif "Pages inactive" in line:
                pages_inactive = int(line.split()[-1].rstrip("."))
        free_bytes = (pages_free + pages_inactive) * page_size
        used_gb = (total_bytes - free_bytes) / (1024 ** 3)
        pct = (used_gb / total_gb) * 100.0 if total_gb > 0 else 0.0
        return round(used_gb, 1), round(total_gb, 1), round(pct, 1)
    except Exception:
        return 0.0, 0.0, 0.0


def _disk_info() -> tuple[float, float, float]:
    """Return (used_GB, total_GB, percent) for /."""
    try:
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free
        total_gb = total / (1024 ** 3)
        used_gb = used / (1024 ** 3)
        pct = (used_gb / total_gb) * 100.0 if total_gb > 0 else 0.0
        return round(used_gb, 1), round(total_gb, 1), round(pct, 1)
    except Exception:
        return 0.0, 0.0, 0.0


def _net_bytes() -> tuple[int, int]:
    """Return (bytes_in, bytes_out) since boot via netstat."""
    try:
        out = subprocess.check_output(
            ["netstat", "-ib"], stderr=subprocess.DEVNULL, timeout=2
        ).decode()
        total_in, total_out = 0, 0
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 10 and parts[0].startswith("en"):
                try:
                    total_in += int(parts[6])
                    total_out += int(parts[9])
                except (ValueError, IndexError):
                    pass
        return total_in, total_out
    except Exception:
        return 0, 0


def _uptime_str() -> str:
    try:
        out = subprocess.check_output(
            ["sysctl", "-n", "kern.boottime"],
            stderr=subprocess.DEVNULL, timeout=2,
        ).decode()
        # { sec = 1708796432, usec = ... }
        sec = int(out.split("sec =")[1].split(",")[0].strip())
        elapsed = int(time.time()) - sec
        days = elapsed // 86400
        hrs = (elapsed % 86400) // 3600
        mins = (elapsed % 3600) // 60
        if days > 0:
            return f"{days}d {hrs}h {mins}m"
        return f"{hrs}h {mins}m"
    except Exception:
        return "???"


def _top_processes(n: int = 12) -> list[dict]:
    """Return top N processes by CPU, with pid/name/cpu/mem."""
    try:
        out = subprocess.check_output(
            ["ps", "-Ao", "pid,pcpu,pmem,comm", "-r"],
            stderr=subprocess.DEVNULL, timeout=3,
        ).decode()
        procs = []
        for line in out.splitlines()[1:]:
            parts = line.split(None, 3)
            if len(parts) < 4:
                continue
            try:
                pid = int(parts[0])
                cpu = float(parts[1])
                mem = float(parts[2])
                name = os.path.basename(parts[3])
                procs.append({"pid": pid, "name": name, "cpu": cpu, "mem": mem})
            except (ValueError, IndexError):
                pass
        return procs[:n]
    except Exception:
        return []


def _process_count() -> int:
    try:
        out = subprocess.check_output(
            ["ps", "-A"], stderr=subprocess.DEVNULL, timeout=2
        ).decode()
        return max(0, len(out.strip().splitlines()) - 1)
    except Exception:
        return 0


# ── Monitor Window ──────────────────────────────────────────────────
class MonitorWindow:
    """Full-screen system monitor panel."""

    def __init__(self, ww: int, wh: int):
        self._ww = ww
        self._wh = wh
        self.visible = False
        self._quit_btn_rect: pygame.Rect | None = None

        # Data refresh state
        self._last_refresh = 0.0
        self._refresh_interval = 2.0  # seconds between data refreshes

        # Live data
        self._cpu = 0.0
        self._mem_used = 0.0
        self._mem_total = 0.0
        self._mem_pct = 0.0
        self._disk_used = 0.0
        self._disk_total = 0.0
        self._disk_pct = 0.0
        self._net_in = 0
        self._net_out = 0
        self._net_in_prev = 0
        self._net_out_prev = 0
        self._net_in_rate = 0.0   # bytes/s
        self._net_out_rate = 0.0
        self._uptime = "???"
        self._processes: list[dict] = []
        self._proc_count = 0
        self._hostname = platform.node() or "localhost"
        self._os_version = platform.platform(terse=True)

        # History for animated graphs (ring buffers)
        self._hist_len = 80
        self._cpu_hist: list[float] = [0.0] * self._hist_len
        self._mem_hist: list[float] = [0.0] * self._hist_len
        self._net_in_hist: list[float] = [0.0] * self._hist_len
        self._net_out_hist: list[float] = [0.0] * self._hist_len
        self._hist_idx = 0

        # Scroll for process list
        self._scroll_offset = 0
        self._drag_last_y: float | None = None

    # ── open / close ────────────────────────────────────────────────
    def open(self):
        self.visible = True
        self._last_refresh = 0.0   # force immediate refresh
        self._scroll_offset = 0

    def close(self):
        self.visible = False

    # ── data refresh ────────────────────────────────────────────────
    def _refresh(self):
        now = time.time()
        if now - self._last_refresh < self._refresh_interval:
            return
        self._last_refresh = now

        self._cpu = _cpu_percent()
        self._mem_used, self._mem_total, self._mem_pct = _mem_info()
        self._disk_used, self._disk_total, self._disk_pct = _disk_info()
        self._uptime = _uptime_str()
        self._processes = _top_processes(14)
        self._proc_count = _process_count()

        # Network rate
        nin, nout = _net_bytes()
        if self._net_in_prev > 0:
            dt = max(self._refresh_interval, 0.1)
            self._net_in_rate = max(0, (nin - self._net_in_prev)) / dt
            self._net_out_rate = max(0, (nout - self._net_out_prev)) / dt
        self._net_in_prev, self._net_out_prev = nin, nout

        # Push to history
        idx = self._hist_idx % self._hist_len
        self._cpu_hist[idx] = self._cpu
        self._mem_hist[idx] = self._mem_pct
        self._net_in_hist[idx] = self._net_in_rate
        self._net_out_hist[idx] = self._net_out_rate
        self._hist_idx += 1

    # ── rect ────────────────────────────────────────────────────────
    def _rect(self, s: float) -> pygame.Rect:
        margin = int(20 * s)
        return pygame.Rect(margin, margin, self._ww - margin * 2, self._wh - margin * 2)

    # ── input ───────────────────────────────────────────────────────
    def handle_tap(self, px: float, py: float, gui_scale: float = 1.0):
        if not self.visible:
            return
        if self._quit_btn_rect and self._quit_btn_rect.collidepoint(int(px), int(py)):
            self.close()

    def handle_scroll(self, dy: int):
        if not self.visible:
            return
        self._scroll_offset += dy * 25
        self._scroll_offset = max(0, self._scroll_offset)

    def handle_pinch_drag(self, px: float, py: float, gui_scale: float = 1.0):
        if not self.visible:
            return
        if self._drag_last_y is None:
            self._drag_last_y = py
            return
        dy = self._drag_last_y - py
        self._scroll_offset += dy
        self._scroll_offset = max(0, self._scroll_offset)
        self._drag_last_y = py

    def handle_pinch_drag_end(self):
        self._drag_last_y = None

    # ── drawing ─────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface, gui_scale: float = 1.0):
        if not self.visible:
            return
        self._refresh()

        s = gui_scale
        p = tc.pal()
        win = self._rect(s)
        now = time.time()

        # Background + frame
        surface.fill(_BG, win)
        tc.draw_window_frame(surface, win, s, p)

        # Header
        header_h = int(50 * s)
        tc.draw_header(surface, win, header_h, "SYSTEM MONITOR", s, p)

        # Footer with quit button
        footer_h = int(60 * s)
        footer_y = win.bottom - footer_h
        btn_w, btn_h = int(100 * s), int(38 * s)
        quit_rect = pygame.Rect(
            win.right - btn_w - int(18 * s),
            footer_y + (footer_h - btn_h) // 2,
            btn_w, btn_h
        )
        self._quit_btn_rect = quit_rect
        tc.draw_angular_button(surface, quit_rect, "QUIT", s, p, danger=True)

        # Footer info
        info_txt = f"HOST: {self._hostname}  |  UP: {self._uptime}  |  PROCS: {self._proc_count}"
        ft = _f(int(16 * s)).render(info_txt, True, _GRAY)
        surface.blit(ft, (win.x + int(14 * s), footer_y + (footer_h - ft.get_height()) // 2))

        # Content area
        body_top = win.y + header_h + int(8 * s)
        body_bottom = footer_y - int(4 * s)
        body_h = body_bottom - body_top

        # Layout: left column (gauges + graphs) | right column (process list)
        col_gap = int(16 * s)
        left_w = int(win.width * 0.48)
        right_w = win.width - left_w - col_gap - int(24 * s)
        left_x = win.x + int(12 * s)
        right_x = left_x + left_w + col_gap

        # ── LEFT COLUMN ────────────────────────────────────────────
        cy = body_top + int(8 * s)

        # CPU gauge
        cy = self._draw_gauge(surface, left_x, cy, left_w, s, p, now,
                              "CPU", self._cpu, _GREEN, _YELLOW, _RED)
        cy += int(6 * s)

        # Memory gauge
        mem_label = f"MEM  {self._mem_used:.1f} / {self._mem_total:.1f} GB"
        cy = self._draw_gauge(surface, left_x, cy, left_w, s, p, now,
                              mem_label, self._mem_pct, _CYAN, _YELLOW, _RED)
        cy += int(6 * s)

        # Disk gauge
        disk_label = f"DISK  {self._disk_used:.0f} / {self._disk_total:.0f} GB"
        cy = self._draw_gauge(surface, left_x, cy, left_w, s, p, now,
                              disk_label, self._disk_pct, _BLUE, _ORANGE, _RED)
        cy += int(12 * s)

        # Network readout
        cy = self._draw_net_readout(surface, left_x, cy, left_w, s, p)
        cy += int(12 * s)

        # CPU history graph
        graph_h = int(90 * s)
        remaining = body_bottom - cy - int(8 * s)
        if remaining > graph_h * 2 + int(30 * s):
            cy = self._draw_graph(surface, left_x, cy, left_w, graph_h, s, p, now,
                                  "CPU HISTORY", self._cpu_hist, _GREEN, 100.0)
            cy += int(10 * s)
            # Net graph
            max_net = max(max(self._net_in_hist), max(self._net_out_hist), 1024)
            cy = self._draw_dual_graph(surface, left_x, cy, left_w, graph_h, s, p, now,
                                       "NETWORK", self._net_in_hist, self._net_out_hist,
                                       _CYAN, _ORANGE, max_net)
        elif remaining > graph_h + int(10 * s):
            cy = self._draw_graph(surface, left_x, cy, left_w, graph_h, s, p, now,
                                  "CPU HISTORY", self._cpu_hist, _GREEN, 100.0)

        # ── RIGHT COLUMN ── process list ────────────────────────────
        self._draw_process_list(surface, right_x, body_top + int(8 * s),
                                right_w, body_h - int(16 * s), s, p, now)

    # ── gauge bar ───────────────────────────────────────────────────
    def _draw_gauge(self, surface, x, y, w, s, p, now, label, pct,
                    col_low, col_mid, col_hi) -> int:
        h = int(38 * s)
        bar_h = int(14 * s)
        label_h = int(18 * s)

        # Choose colour
        if pct > 85:
            col = col_hi
        elif pct > 60:
            col = col_mid
        else:
            col = col_low

        # Label
        accent = p["bright"] if p else col
        ft = _f(int(16 * s)).render(f"{label}  {pct:.1f}%", True, accent)
        surface.blit(ft, (x, y))

        # Bar background
        bar_y = y + label_h + int(2 * s)
        bar_rect = pygame.Rect(x, bar_y, w, bar_h)
        pygame.draw.rect(surface, _PANEL, bar_rect, border_radius=int(3 * s))
        pygame.draw.rect(surface, _DIM, bar_rect, 1, border_radius=int(3 * s))

        # Filled portion with animated pulse glow
        fill_w = int(w * min(pct, 100.0) / 100.0)
        if fill_w > 0:
            fill_rect = pygame.Rect(x, bar_y, fill_w, bar_h)
            pygame.draw.rect(surface, col, fill_rect, border_radius=int(3 * s))
            # Pulsing shine
            pulse = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(now * 3 + pct * 0.1))
            shine_col = tuple(min(255, int(c + 60 * pulse)) for c in col)
            shine_rect = pygame.Rect(x, bar_y, fill_w, bar_h // 2)
            sh_surf = pygame.Surface((shine_rect.w, shine_rect.h), pygame.SRCALPHA)
            sh_surf.fill((*shine_col, int(45 * pulse)))
            surface.blit(sh_surf, shine_rect.topleft)

            # Animated moving highlight stripe
            stripe_x = x + int((now * 80 * s) % max(1, fill_w))
            stripe_w = int(18 * s)
            sr = pygame.Rect(stripe_x, bar_y + 1, stripe_w, bar_h - 2)
            sr = sr.clip(fill_rect)
            if sr.width > 0:
                ss = pygame.Surface((sr.w, sr.h), pygame.SRCALPHA)
                ss.fill((*_WHITE, 30))
                surface.blit(ss, sr.topleft)

        return y + h

    # ── network readout ─────────────────────────────────────────────
    def _draw_net_readout(self, surface, x, y, w, s, p) -> int:
        accent = p["bright"] if p else _CYAN
        # Format rates
        def fmt(bps):
            if bps > 1_000_000:
                return f"{bps / 1_000_000:.1f} MB/s"
            elif bps > 1_000:
                return f"{bps / 1_000:.0f} KB/s"
            return f"{bps:.0f} B/s"

        h = int(38 * s)
        lbl = _f(int(16 * s)).render("NETWORK", True, accent)
        surface.blit(lbl, (x, y))

        in_txt = _f(int(15 * s)).render(f"IN  {fmt(self._net_in_rate)}", True, _CYAN)
        out_txt = _f(int(15 * s)).render(f"OUT {fmt(self._net_out_rate)}", True, _ORANGE)
        surface.blit(in_txt, (x + int(4 * s), y + int(18 * s)))
        surface.blit(out_txt, (x + w // 2, y + int(18 * s)))
        return y + h

    # ── animated line graph ─────────────────────────────────────────
    def _draw_graph(self, surface, x, y, w, h, s, p, now,
                    label, history, color, max_val) -> int:
        accent = p["bright"] if p else color
        panel = pygame.Rect(x, y, w, h + int(20 * s))
        pygame.draw.rect(surface, _PANEL, panel, border_radius=int(4 * s))
        pygame.draw.rect(surface, _DIM, panel, 1, border_radius=int(4 * s))

        # Label
        ft = _f(int(14 * s)).render(label, True, accent)
        surface.blit(ft, (x + int(6 * s), y + int(3 * s)))

        # Graph area
        gx = x + int(4 * s)
        gy = y + int(18 * s)
        gw = w - int(8 * s)
        gh = h - int(4 * s)

        # Grid lines
        for i in range(1, 4):
            ly = gy + int(gh * i / 4)
            pygame.draw.line(surface, (*_DIM[:3],), (gx, ly), (gx + gw, ly), 1)

        # Build points from ring buffer
        n = len(history)
        idx = self._hist_idx % n
        points = []
        for i in range(n):
            val = history[(idx + i) % n]
            fx = gx + int(gw * i / max(1, n - 1))
            fy = gy + gh - int(gh * min(val, max_val) / max(1, max_val))
            points.append((fx, fy))

        if len(points) >= 2:
            # Filled area under curve
            fill_pts = list(points) + [(points[-1][0], gy + gh), (points[0][0], gy + gh)]
            fill_surf = pygame.Surface((gw + int(8 * s), gh + 2), pygame.SRCALPHA)
            shifted = [(px2 - gx + int(4 * s), py2 - gy) for px2, py2 in fill_pts]
            if len(shifted) >= 3:
                pygame.draw.polygon(fill_surf, (*color, 35), shifted)
                surface.blit(fill_surf, (gx - int(4 * s), gy))

            # Line
            pygame.draw.lines(surface, color, False, points, max(1, int(2 * s)))

            # Animated dot on latest point
            latest = points[-1]
            pulse = 0.5 + 0.5 * math.sin(now * 5)
            r = int((3 + 2 * pulse) * s)
            pygame.draw.circle(surface, color, latest, r)
            glow = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*color, int(60 * pulse)), (r * 2, r * 2), r * 2)
            surface.blit(glow, (latest[0] - r * 2, latest[1] - r * 2))

        return y + h + int(22 * s)

    # ── dual graph (net in/out) ─────────────────────────────────────
    def _draw_dual_graph(self, surface, x, y, w, h, s, p, now,
                         label, hist_a, hist_b, col_a, col_b, max_val) -> int:
        accent = p["bright"] if p else col_a
        panel = pygame.Rect(x, y, w, h + int(20 * s))
        pygame.draw.rect(surface, _PANEL, panel, border_radius=int(4 * s))
        pygame.draw.rect(surface, _DIM, panel, 1, border_radius=int(4 * s))

        ft = _f(int(14 * s)).render(label, True, accent)
        surface.blit(ft, (x + int(6 * s), y + int(3 * s)))

        # Legend
        leg_y = y + int(3 * s)
        leg_in = _f(int(12 * s)).render("IN", True, col_a)
        leg_out = _f(int(12 * s)).render("OUT", True, col_b)
        surface.blit(leg_in, (x + w - int(60 * s), leg_y))
        surface.blit(leg_out, (x + w - int(30 * s), leg_y))

        gx = x + int(4 * s)
        gy = y + int(18 * s)
        gw = w - int(8 * s)
        gh = h - int(4 * s)

        for i in range(1, 4):
            ly = gy + int(gh * i / 4)
            pygame.draw.line(surface, _DIM, (gx, ly), (gx + gw, ly), 1)

        n = len(hist_a)
        idx = self._hist_idx % n
        for hist, col in [(hist_a, col_a), (hist_b, col_b)]:
            points = []
            for i in range(n):
                val = hist[(idx + i) % n]
                fx = gx + int(gw * i / max(1, n - 1))
                fy = gy + gh - int(gh * min(val, max_val) / max(1, max_val))
                points.append((fx, fy))
            if len(points) >= 2:
                fill_pts = list(points) + [(points[-1][0], gy + gh), (points[0][0], gy + gh)]
                fill_surf = pygame.Surface((gw + int(8 * s), gh + 2), pygame.SRCALPHA)
                shifted = [(px2 - gx + int(4 * s), py2 - gy) for px2, py2 in fill_pts]
                if len(shifted) >= 3:
                    pygame.draw.polygon(fill_surf, (*col, 25), shifted)
                    surface.blit(fill_surf, (gx - int(4 * s), gy))
                pygame.draw.lines(surface, col, False, points, max(1, int(2 * s)))
                # Dot
                pulse = 0.5 + 0.5 * math.sin(now * 5)
                r = int((3 + 2 * pulse) * s)
                pygame.draw.circle(surface, col, points[-1], r)

        return y + h + int(22 * s)

    # ── process list ────────────────────────────────────────────────
    def _draw_process_list(self, surface, x, y, w, total_h, s, p, now):
        accent = p["bright"] if p else _GREEN
        border_col = p["btn_bdr"] if p else _DIM

        # Panel background
        panel = pygame.Rect(x, y, w, total_h)
        pygame.draw.rect(surface, _PANEL, panel, border_radius=int(4 * s))
        pygame.draw.rect(surface, border_col, panel, 1, border_radius=int(4 * s))

        # Header row
        hdr_h = int(28 * s)
        hdr_rect = pygame.Rect(x, y, w, hdr_h)
        hdr_surf = pygame.Surface((w, hdr_h), pygame.SRCALPHA)
        hdr_surf.fill((*accent, 20))
        surface.blit(hdr_surf, (x, y))

        row_font_sz = int(14 * s)
        hdr_font = _f(int(15 * s))

        # Columns: PID  NAME  CPU%  MEM%
        cols = [
            ("PID", int(50 * s)),
            ("PROCESS", int(w - 200 * s)),
            ("CPU%", int(60 * s)),
            ("MEM%", int(60 * s)),
        ]
        cx = x + int(8 * s)
        for col_name, col_w in cols:
            ht = hdr_font.render(col_name, True, accent)
            surface.blit(ht, (cx, y + (hdr_h - ht.get_height()) // 2))
            cx += col_w

        tc.draw_separator(surface, x + int(4 * s), x + w - int(4 * s), y + hdr_h, p)

        # Process rows (clipped)
        list_y = y + hdr_h + int(4 * s)
        list_h = total_h - hdr_h - int(8 * s)
        row_h = int(24 * s)
        clip = pygame.Rect(x, list_y, w, list_h)
        old_clip = surface.get_clip()
        surface.set_clip(clip)

        for i, proc in enumerate(self._processes):
            ry = list_y + i * row_h - self._scroll_offset
            if ry + row_h < list_y or ry > list_y + list_h:
                continue

            # Alternating row tint
            if i % 2 == 0:
                row_bg = pygame.Surface((w - int(8 * s), row_h), pygame.SRCALPHA)
                row_bg.fill((255, 255, 255, 8))
                surface.blit(row_bg, (x + int(4 * s), ry))

            # Animated CPU activity bar behind process name
            cpu_frac = min(proc["cpu"] / 100.0, 1.0)
            if cpu_frac > 0.01:
                bar_col = _GREEN if proc["cpu"] < 30 else (_YELLOW if proc["cpu"] < 70 else _RED)
                # Sweep animation
                sweep_w = int((w - int(16 * s)) * cpu_frac)
                sweep_phase = (now * 0.6 + i * 0.3) % 1.0
                bar_alpha = int(20 + 15 * math.sin(sweep_phase * math.pi * 2))
                bar_surf = pygame.Surface((sweep_w, row_h), pygame.SRCALPHA)
                bar_surf.fill((*bar_col, bar_alpha))
                surface.blit(bar_surf, (x + int(8 * s), ry))

            rf = _f(row_font_sz)
            cx = x + int(8 * s)

            # PID
            pid_txt = rf.render(str(proc["pid"]), True, _GRAY)
            surface.blit(pid_txt, (cx, ry + (row_h - pid_txt.get_height()) // 2))
            cx += int(50 * s)

            # Name (truncate)
            max_name_w = int(w - 200 * s)
            name = proc["name"]
            name_txt = rf.render(name, True, _WHITE)
            if name_txt.get_width() > max_name_w:
                while len(name) > 4 and rf.size(name + "..")[0] > max_name_w:
                    name = name[:-1]
                name_txt = rf.render(name + "..", True, _WHITE)
            surface.blit(name_txt, (cx, ry + (row_h - name_txt.get_height()) // 2))
            cx += max_name_w

            # CPU%
            cpu_col = _GREEN if proc["cpu"] < 30 else (_YELLOW if proc["cpu"] < 70 else _RED)
            cpu_txt = rf.render(f"{proc['cpu']:.1f}", True, cpu_col)
            surface.blit(cpu_txt, (cx, ry + (row_h - cpu_txt.get_height()) // 2))
            cx += int(60 * s)

            # MEM%
            mem_col = _CYAN if proc["mem"] < 10 else (_YELLOW if proc["mem"] < 30 else _RED)
            mem_txt = rf.render(f"{proc['mem']:.1f}", True, mem_col)
            surface.blit(mem_txt, (cx, ry + (row_h - mem_txt.get_height()) // 2))

        surface.set_clip(old_clip)

        # Scrollbar if needed
        max_scroll = max(0, len(self._processes) * row_h - list_h)
        if max_scroll > 0:
            self._scroll_offset = min(self._scroll_offset, max_scroll)
            thumb_frac = list_h / (len(self._processes) * row_h)
            thumb_pos = self._scroll_offset / max_scroll if max_scroll else 0
            sb_rect = pygame.Rect(x + w - int(8 * s), list_y, int(5 * s), list_h)
            tc.draw_scrollbar(surface, sb_rect, thumb_frac, thumb_pos, s, p)

        # Spinning activity indicator (animated ring)
        ring_cx = x + w - int(20 * s)
        ring_cy = y + hdr_h // 2
        ring_r = int(7 * s)
        ang = now * 4.0
        for j in range(8):
            a = ang + j * (math.pi / 4)
            alpha = int(60 + 195 * ((7 - j) / 7))
            dx2 = int(ring_r * math.cos(a))
            dy2 = int(ring_r * math.sin(a))
            dot_col = (*accent[:3], alpha) if len(accent) >= 3 else (*_GREEN, alpha)
            dot_surf = pygame.Surface((int(4 * s), int(4 * s)), pygame.SRCALPHA)
            pygame.draw.circle(dot_surf, dot_col,
                               (int(2 * s), int(2 * s)), int(2 * s))
            surface.blit(dot_surf, (ring_cx + dx2 - int(2 * s),
                                     ring_cy + dy2 - int(2 * s)))
