"""
Network Discovery — scan local network for hosts, open ports, and services.
Uses ARP table, ping sweep, and optional nmap for deeper scans.
All scanning runs in background threads so the UI stays responsive.
Themed with theme_chrome for consistent sci-fi / ice look.
"""
import os
import re
import socket
import subprocess
import threading
import time

import pygame
import theme_chrome as tc

# ── Colours (fallback for classic theme) ────────────────────────────
_BG      = (14, 14, 24)
_WHITE   = (255, 255, 255)
_GRAY    = (140, 140, 160)
_DIM     = (80, 80, 100)
_GREEN   = (0, 230, 120)
_YELLOW  = (255, 220, 60)
_RED     = (255, 60, 60)
_CYAN    = (0, 220, 220)
_BLUE    = (60, 140, 255)
_ORANGE  = (255, 140, 40)
_PURPLE  = (180, 100, 255)
_TEAL    = (0, 180, 180)

# ── Font cache ──────────────────────────────────────────────────────
_fc: dict[int, pygame.font.Font] = {}


def _f(sz: int) -> pygame.font.Font:
    sz = max(10, sz)
    if sz not in _fc:
        _fc[sz] = pygame.font.SysFont("Menlo", sz)
    return _fc[sz]


# ── Shell helper ────────────────────────────────────────────────────
def _run(cmd, timeout=8):
    try:
        return subprocess.check_output(
            cmd, stderr=subprocess.DEVNULL, timeout=timeout
        ).decode(errors="replace").strip()
    except Exception:
        return ""


# ── Host data ───────────────────────────────────────────────────────
class _Host:
    """Represents a discovered network host."""
    __slots__ = ("ip", "mac", "hostname", "vendor", "ports", "status", "latency")

    def __init__(self, ip, mac="", hostname="", vendor=""):
        self.ip = ip
        self.mac = mac.upper()
        self.hostname = hostname
        self.vendor = vendor
        self.ports: list[tuple[int, str]] = []   # (port, service_name)
        self.status = "up"
        self.latency = ""   # e.g. "1.2ms"


# ── Scanner backend (background threads) ───────────────────────────
class _Scanner:
    """Network scanning engine — runs in background threads."""

    def __init__(self):
        self.hosts: list[_Host] = []
        self.gateway: str = ""
        self.local_ip: str = ""
        self.subnet: str = ""
        self.interface: str = ""
        self.ssid: str = ""
        self.scanning: bool = False
        self.scan_phase: str = "idle"     # "arp", "resolve", "portscan", "done"
        self.scan_progress: float = 0.0   # 0..1
        self.last_scan_time: float = 0.0
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._nmap_available = False

    def start_scan(self):
        if self.scanning:
            return
        self.scanning = True
        self.scan_phase = "init"
        self.scan_progress = 0.0
        self._thread = threading.Thread(target=self._scan_worker, daemon=True)
        self._thread.start()

    def _scan_worker(self):
        try:
            self._detect_network()
            self._check_nmap()
            self._arp_scan()
            self._resolve_hostnames()
            self._port_scan()
        except Exception as e:
            print(f"NetScan error: {e}")
        finally:
            self.scan_phase = "done"
            self.scan_progress = 1.0
            self.scanning = False
            self.last_scan_time = time.time()

    def _detect_network(self):
        self.scan_phase = "init"
        self.scan_progress = 0.05
        # Get default gateway and interface
        route = _run(["route", "-n", "get", "default"])
        for line in route.splitlines():
            line = line.strip()
            if line.startswith("gateway:"):
                self.gateway = line.split(":", 1)[1].strip()
            elif line.startswith("interface:"):
                self.interface = line.split(":", 1)[1].strip()
        # Get local IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            self.local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            self.local_ip = "unknown"
        # Derive subnet (assume /24)
        if self.local_ip and self.local_ip != "unknown":
            parts = self.local_ip.rsplit(".", 1)
            self.subnet = parts[0] + ".0/24" if len(parts) == 2 else ""
        # Get SSID
        ssid_out = _run([
            "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport",
            "-I"
        ])
        if not ssid_out:
            ssid_out = _run(["networksetup", "-getairportnetwork", self.interface or "en0"])
        for line in ssid_out.splitlines():
            line = line.strip()
            if "SSID:" in line or "Current Wi-Fi Network:" in line:
                self.ssid = line.split(":", 1)[1].strip()
                break

    def _check_nmap(self):
        out = _run(["which", "nmap"])
        self._nmap_available = bool(out)

    def _arp_scan(self):
        self.scan_phase = "arp"
        self.scan_progress = 0.15
        # First, ping sweep to populate ARP table (fast, 1-second timeout)
        if self.subnet:
            base = self.local_ip.rsplit(".", 1)[0]
            # Parallel pings using subprocess
            procs = []
            for i in range(1, 255):
                ip = f"{base}.{i}"
                try:
                    p = subprocess.Popen(
                        ["ping", "-c", "1", "-W", "200", ip],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    procs.append((ip, p))
                except Exception:
                    pass
                # Limit parallel pings
                if len(procs) >= 50:
                    for _ip, _p in procs:
                        _p.wait()
                    procs.clear()
                self.scan_progress = 0.15 + 0.35 * (i / 254)
            for _ip, _p in procs:
                try:
                    _p.wait(timeout=3)
                except Exception:
                    _p.kill()

        self.scan_progress = 0.50
        # Read ARP table
        arp_out = _run(["arp", "-a"])
        seen_ips = set()
        with self._lock:
            self.hosts.clear()
            for line in arp_out.splitlines():
                # Format: host (IP) at MAC on interface [ifscope ...]
                m = re.match(r"(\S+)\s+\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+(\S+)", line)
                if m:
                    hostname_raw = m.group(1)
                    ip = m.group(2)
                    mac = m.group(3)
                    if mac == "(incomplete)" or ip in seen_ips:
                        continue
                    seen_ips.add(ip)
                    h = _Host(ip, mac)
                    if hostname_raw != "?":
                        h.hostname = hostname_raw
                    # Basic vendor lookup from MAC OUI
                    h.vendor = _oui_lookup(mac)
                    # Tag gateway
                    if ip == self.gateway:
                        h.hostname = h.hostname or "Gateway/Router"
                    if ip == self.local_ip:
                        h.hostname = h.hostname or "This Machine"
                    self.hosts.append(h)

    def _resolve_hostnames(self):
        self.scan_phase = "resolve"
        self.scan_progress = 0.55
        with self._lock:
            for i, h in enumerate(self.hosts):
                if not h.hostname:
                    try:
                        name = socket.gethostbyaddr(h.ip)[0]
                        h.hostname = name
                    except Exception:
                        pass
                self.scan_progress = 0.55 + 0.15 * ((i + 1) / max(1, len(self.hosts)))

    def _port_scan(self):
        self.scan_phase = "portscan"
        self.scan_progress = 0.70
        common_ports = [22, 53, 80, 443, 445, 548, 631, 3389, 5000, 5900, 8080, 8443, 62078]
        port_names = {
            22: "SSH", 53: "DNS", 80: "HTTP", 443: "HTTPS", 445: "SMB",
            548: "AFP", 631: "IPP", 3389: "RDP", 5000: "UPnP", 5900: "VNC",
            8080: "HTTP-Alt", 8443: "HTTPS-Alt", 62078: "iPhone",
        }
        with self._lock:
            total = len(self.hosts) * len(common_ports)
            done = 0
            for h in self.hosts:
                for port in common_ports:
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.settimeout(0.3)
                        result = s.connect_ex((h.ip, port))
                        s.close()
                        if result == 0:
                            h.ports.append((port, port_names.get(port, str(port))))
                    except Exception:
                        pass
                    done += 1
                    self.scan_progress = 0.70 + 0.28 * (done / max(1, total))

    def get_hosts(self):
        with self._lock:
            return list(self.hosts)


# ── OUI vendor lookup (common prefixes) ────────────────────────────
_OUI_MAP = {
    "00:50:56": "VMware", "00:0C:29": "VMware", "00:1C:42": "Parallels",
    "08:00:27": "VirtualBox", "DC:A6:32": "Raspberry Pi", "B8:27:EB": "Raspberry Pi",
    "AA:BB:CC": "—",
    "3C:22:FB": "Apple", "A4:83:E7": "Apple", "F0:18:98": "Apple",
    "AC:DE:48": "Apple", "14:98:77": "Apple", "F8:FF:C2": "Apple",
    "78:7B:8A": "Apple", "88:66:A5": "Apple", "A8:5C:2C": "Apple",
    "40:B3:95": "Apple", "F4:5C:89": "Apple", "A0:78:17": "Apple",
    "BC:D0:74": "Apple", "20:78:F0": "Apple", "6C:94:66": "Apple",
    "C8:69:CD": "Apple", "84:FC:FE": "Apple", "28:CF:E9": "Apple",
    "18:65:90": "Apple", "70:56:81": "Apple", "D0:81:7A": "Apple",
    "50:ED:3C": "Apple", "64:70:33": "Apple", "00:1B:63": "Apple",
    "10:DD:B1": "Apple", "8C:85:90": "Apple", "AC:BC:32": "Apple",
    "34:36:3B": "Apple",
    "B0:BE:76": "Samsung", "8C:F5:A3": "Samsung", "AC:5F:3E": "Samsung",
    "D0:D2:B0": "Samsung",
    "E4:5F:01": "Raspberry Pi",
    "B4:2E:99": "Google", "A4:77:33": "Google", "F4:F5:D8": "Google",
    "54:60:09": "Google",
    "44:07:0B": "Google Nest", "F4:F5:E8": "Google Nest",
    "FC:EC:DA": "Ubiquiti", "24:A4:3C": "Ubiquiti", "78:8A:20": "Ubiquiti",
    "B4:FB:E4": "Ubiquiti",
    "00:1A:2B": "Cisco", "00:26:0B": "Cisco", "64:F6:9D": "Cisco",
    "A0:3D:6F": "Netgear", "20:4E:7F": "Netgear",
    "C0:25:E9": "TP-Link", "60:32:B1": "TP-Link",
    "D8:3A:DD": "Raspberry Pi",
    "30:FD:38": "Google",
}


def _oui_lookup(mac: str) -> str:
    if not mac or len(mac) < 8:
        return ""
    prefix = mac[:8].upper().replace("-", ":")
    return _OUI_MAP.get(prefix, "")


# ── NetScanWindow ──────────────────────────────────────────────────
class NetScanWindow:
    """Network discovery app with ARP scan, hostname resolution, and port scan."""

    def __init__(self, screen_w: int, screen_h: int):
        self.visible = False
        self._sw = screen_w
        self._sh = screen_h
        self._scanner = _Scanner()
        self._scroll_offset = 0
        self._selected_idx = -1
        self._quit_btn_rect: pygame.Rect | None = None
        self._scan_btn_rect: pygame.Rect | None = None
        self._host_rects: list[tuple[pygame.Rect, int]] = []
        self._drag_last_y: float | None = None
        # Detail expand — index of host whose ports are shown (-1 = none)
        self._detail_idx = -1

    def open(self):
        self.visible = True
        self._scroll_offset = 0
        self._selected_idx = -1
        self._detail_idx = -1
        # Auto-start scan on open
        self._scanner.start_scan()

    def close(self):
        self.visible = False

    def _rect(self, s: float) -> pygame.Rect:
        w = min(int(1200 * s), self._sw - 20)
        h = min(int(720 * s), self._sh - 20)
        return pygame.Rect((self._sw - w) // 2, (self._sh - h) // 2, w, h)

    def hit_test(self, px, py, gui_scale):
        return self._rect(gui_scale).collidepoint(int(px), int(py))

    def handle_tap(self, px: float, py: float, gui_scale: float = 1.0) -> bool:
        if not self.visible:
            return False
        ipx, ipy = int(px), int(py)

        if self._quit_btn_rect and self._quit_btn_rect.collidepoint(ipx, ipy):
            self.close()
            return True

        if self._scan_btn_rect and self._scan_btn_rect.collidepoint(ipx, ipy):
            if not self._scanner.scanning:
                self._scanner.start_scan()
            return True

        for rect, idx in self._host_rects:
            if rect.collidepoint(ipx, ipy):
                if self._detail_idx == idx:
                    self._detail_idx = -1  # collapse
                else:
                    self._detail_idx = idx  # expand
                self._selected_idx = idx
                return True

        return False

    def handle_scroll(self, delta: int):
        self._scroll_offset += delta * 30
        self._scroll_offset = max(0, self._scroll_offset)

    def handle_pinch_drag(self, px, py, gui_scale=1.0):
        if self._drag_last_y is None:
            self._drag_last_y = py
            return
        dy = self._drag_last_y - py
        if abs(dy) < 1.5:
            return
        self._scroll_offset += dy
        self._scroll_offset = max(0, self._scroll_offset)
        self._drag_last_y = py

    def handle_pinch_drag_end(self):
        self._drag_last_y = None

    # ── draw ────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface, gui_scale: float = 1.0):
        if not self.visible:
            return
        s = gui_scale
        win = self._rect(s)
        p = tc.pal()

        # ── Background ──
        if p:
            tc.draw_window_frame(surface, win, s, p)
        else:
            bg = pygame.Surface((win.width, win.height), pygame.SRCALPHA)
            bg.fill(_BG)
            surface.blit(bg, win.topleft)
            pygame.draw.rect(surface, _DIM, win, width=2, border_radius=8)

        header_h = int(60 * s)
        footer_h = int(50 * s)

        # ── Header ──
        if p:
            tc.draw_header(surface, win, header_h, "NETWORK DISCOVERY", s, p)
        else:
            header_r = pygame.Rect(win.x, win.y, win.width, header_h)
            pygame.draw.rect(surface, (32, 32, 52), header_r)
            title = _f(int(28 * s)).render("Network Discovery", True, _WHITE)
            surface.blit(title, (win.x + int(20 * s), win.y + int(10 * s)))

        # ── Network info bar (below header) ──
        info_y = win.y + header_h + int(4 * s)
        info_col = p["text_lo"] if p else _DIM
        bright_col = p["bright"] if p else _WHITE
        mid_col = p["mid"] if p else _CYAN

        ip_str = f"IP: {self._scanner.local_ip}" if self._scanner.local_ip else "IP: detecting..."
        gw_str = f"GW: {self._scanner.gateway}" if self._scanner.gateway else ""
        ssid_str = f"SSID: {self._scanner.ssid}" if self._scanner.ssid else ""
        iface_str = f"IF: {self._scanner.interface}" if self._scanner.interface else ""

        info_parts = [s for s in [ip_str, gw_str, ssid_str, iface_str] if s]
        info_text = "  │  ".join(info_parts)
        info_img = _f(int(14 * s)).render(info_text, True, mid_col)
        surface.blit(info_img, (win.x + int(20 * s), info_y))

        # ── Scan status / progress ──
        status_y = info_y + int(20 * s)
        if self._scanner.scanning:
            phase = self._scanner.scan_phase.upper()
            pct = int(self._scanner.scan_progress * 100)
            status_text = f"SCANNING — {phase} ({pct}%)"
            status_col = _YELLOW if not p else p.get("mid", _YELLOW)
            # Progress bar
            bar_x = win.x + int(20 * s)
            bar_w = win.width - int(40 * s)
            bar_h = max(3, int(4 * s))
            bar_y = status_y + int(18 * s)
            pygame.draw.rect(surface, (*_DIM, 60) if not p else (*p["dim"], 60),
                             (bar_x, bar_y, bar_w, bar_h), border_radius=2)
            fill_w = int(bar_w * self._scanner.scan_progress)
            if fill_w > 0:
                bar_fill_col = _CYAN if not p else p["bright"]
                pygame.draw.rect(surface, bar_fill_col,
                                 (bar_x, bar_y, fill_w, bar_h), border_radius=2)
        else:
            hosts = self._scanner.get_hosts()
            n = len(hosts)
            if self._scanner.last_scan_time > 0:
                ago = time.time() - self._scanner.last_scan_time
                if ago < 60:
                    time_str = f"{int(ago)}s ago"
                else:
                    time_str = f"{int(ago / 60)}m ago"
                status_text = f"{n} HOSTS FOUND — scanned {time_str}"
            else:
                status_text = "READY — tap SCAN to discover network"
            status_col = _GREEN if n > 0 else info_col
        status_img = _f(int(13 * s)).render(status_text, True, status_col)
        surface.blit(status_img, (win.x + int(20 * s), status_y))

        # ── Host list body ──
        body_top = win.y + header_h + int(50 * s)
        body_h = win.height - header_h - footer_h - int(50 * s)

        clip_rect = pygame.Rect(win.x, body_top, win.width, body_h)
        old_clip = surface.get_clip()
        surface.set_clip(clip_rect)

        self._host_rects.clear()
        hosts = self._scanner.get_hosts()

        if not hosts and not self._scanner.scanning:
            empty_col = p["text_lo"] if p else _DIM
            msg = _f(int(20 * s)).render("No hosts discovered yet", True, empty_col)
            surface.blit(msg, msg.get_rect(center=(win.centerx, body_top + body_h // 2)))
        else:
            row_h = int(44 * s)
            detail_extra_h = int(28 * s)
            y = body_top - self._scroll_offset

            for i, h in enumerate(hosts):
                # Calculate row height (taller if detail is expanded)
                n_ports = len(h.ports)
                this_h = row_h
                if i == self._detail_idx and n_ports > 0:
                    this_h += detail_extra_h * min(n_ports, 6) + int(8 * s)

                if y + this_h < body_top:
                    y += this_h
                    continue
                if y > body_top + body_h:
                    break

                row_rect = pygame.Rect(win.x + int(10 * s), y, win.width - int(20 * s), this_h)
                self._host_rects.append((row_rect, i))

                # Alternating stripe
                if i % 2 == 0:
                    stripe_col = p["stripe"] if p else (18, 18, 30)
                    stripe_surf = pygame.Surface((row_rect.width, row_h), pygame.SRCALPHA)
                    stripe_surf.fill((*stripe_col, 40) if len(stripe_col) == 3 else stripe_col)
                    surface.blit(stripe_surf, row_rect.topleft)

                # Selected highlight
                if i == self._selected_idx:
                    sel_col = p["sel_bg"] if p else (40, 60, 100, 100)
                    sel_s = pygame.Surface((row_rect.width, row_h), pygame.SRCALPHA)
                    sel_s.fill(sel_col if len(sel_col) == 4 else (*sel_col, 100))
                    surface.blit(sel_s, row_rect.topleft)

                # Status dot
                dot_x = win.x + int(24 * s)
                dot_y = y + row_h // 2
                dot_col = _GREEN if h.status == "up" else _RED
                pygame.draw.circle(surface, dot_col, (dot_x, dot_y), max(3, int(4 * s)))

                # IP address
                ip_font = _f(int(16 * s))
                ip_col = bright_col
                ip_img = ip_font.render(h.ip, True, ip_col)
                surface.blit(ip_img, (dot_x + int(16 * s), y + int(4 * s)))

                # Hostname
                host_x = dot_x + int(160 * s)
                hn = h.hostname or "—"
                if len(hn) > 28:
                    hn = hn[:26] + "…"
                hn_col = mid_col if h.hostname else info_col
                hn_img = _f(int(14 * s)).render(hn, True, hn_col)
                surface.blit(hn_img, (host_x, y + int(6 * s)))

                # MAC address
                mac_x = dot_x + int(160 * s)
                mac_col = info_col
                mac_img = _f(int(12 * s)).render(h.mac or "—", True, mac_col)
                surface.blit(mac_img, (mac_x, y + int(24 * s)))

                # Vendor
                vendor_x = dot_x + int(340 * s)
                if h.vendor:
                    v_img = _f(int(13 * s)).render(h.vendor, True, _ORANGE if not p else p.get("mid", _ORANGE))
                    surface.blit(v_img, (vendor_x, y + int(6 * s)))

                # Port count badge
                if h.ports:
                    port_badge = f"{len(h.ports)} port{'s' if len(h.ports) != 1 else ''}"
                    badge_col = _CYAN if not p else p["bright"]
                    badge_img = _f(int(12 * s)).render(port_badge, True, badge_col)
                    badge_x = win.x + win.width - int(30 * s) - badge_img.get_width()
                    surface.blit(badge_img, (badge_x, y + int(6 * s)))

                # Expand arrow
                arrow = "▾" if i == self._detail_idx else "▸"
                arrow_col = bright_col if h.ports else info_col
                arrow_img = _f(int(16 * s)).render(arrow, True, arrow_col)
                surface.blit(arrow_img, (win.x + win.width - int(20 * s), y + int(12 * s)))

                # ── Expanded port detail ──
                if i == self._detail_idx and n_ports > 0:
                    detail_y = y + row_h + int(4 * s)
                    for pi, (port, svc) in enumerate(h.ports[:6]):
                        px = dot_x + int(40 * s)
                        py = detail_y + pi * detail_extra_h
                        port_str = f":{port}"
                        svc_str = f"  {svc}"
                        port_img = _f(int(14 * s)).render(port_str, True, _CYAN if not p else p["bright"])
                        svc_img = _f(int(13 * s)).render(svc_str, True, info_col)
                        surface.blit(port_img, (px, py))
                        surface.blit(svc_img, (px + port_img.get_width(), py + int(1 * s)))
                    if n_ports > 6:
                        more = _f(int(12 * s)).render(f"  +{n_ports - 6} more…", True, info_col)
                        surface.blit(more, (dot_x + int(40 * s), detail_y + 6 * detail_extra_h))

                y += this_h

            # Clamp scroll
            total_h = y + self._scroll_offset - body_top
            max_scroll = max(0, total_h - body_h)
            self._scroll_offset = max(0, min(self._scroll_offset, max_scroll))

        surface.set_clip(old_clip)

        # ── Footer: buttons ──
        footer_y = win.y + win.height - footer_h
        if p:
            tc.draw_separator(surface, win.x + 10, footer_y, win.width - 20, s, p)

        btn_w = int(100 * s)
        btn_h = int(32 * s)
        btn_y = footer_y + (footer_h - btn_h) // 2

        # Scan button
        scan_label = "SCANNING…" if self._scanner.scanning else "SCAN"
        scan_x = win.x + int(20 * s)
        self._scan_btn_rect = pygame.Rect(scan_x, btn_y, btn_w, btn_h)
        if p:
            tc.draw_angular_button(surface, self._scan_btn_rect, scan_label, s, p,
                                   disabled=self._scanner.scanning)
        else:
            col = _DIM if self._scanner.scanning else _CYAN
            pygame.draw.rect(surface, col, self._scan_btn_rect, width=2, border_radius=6)
            lbl = _f(int(16 * s)).render(scan_label, True, col)
            surface.blit(lbl, lbl.get_rect(center=self._scan_btn_rect.center))

        # Host count
        n = len(self._scanner.get_hosts())
        count_img = _f(int(14 * s)).render(f"{n} hosts", True, info_col)
        surface.blit(count_img, (scan_x + btn_w + int(16 * s),
                                 btn_y + btn_h // 2 - count_img.get_height() // 2))

        # Quit button
        quit_x = win.x + win.width - btn_w - int(20 * s)
        self._quit_btn_rect = pygame.Rect(quit_x, btn_y, btn_w, btn_h)
        if p:
            tc.draw_angular_button(surface, self._quit_btn_rect, "CLOSE", s, p)
        else:
            pygame.draw.rect(surface, _RED, self._quit_btn_rect, width=2, border_radius=6)
            lbl = _f(int(16 * s)).render("CLOSE", True, _RED)
            surface.blit(lbl, lbl.get_rect(center=self._quit_btn_rect.center))
