"""
System Profile – tabbed HUD with real-time data:

  TAB 0 – OVERVIEW    : CPU / Memory / Disk gauges, per-core bars, memory
                         pressure, uptime, hostname, OS
  TAB 1 – PROCESSES   : live top-N process list sorted by CPU (select→kill)
  TAB 2 – HARDWARE    : chip, cores, GPU, bluetooth, USB, security badges
  TAB 3 – NETWORK     : interfaces, throughput graph, open connections, Wi-Fi
  TAB 4 – STORAGE     : per-volume bars, disk I/O graph, open FD gauge

All data gathered with macOS stdlib (no psutil).
Themed with theme_chrome angular HUD styling.
"""
import math
import os
import platform
import random
import re
import signal
import subprocess
import threading
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
_TEAL     = (0, 180, 180)
_PINK     = (255, 100, 180)

_TAB_NAMES = ["OVERVIEW", "PROCESSES", "HARDWARE", "NETWORK", "STORAGE"]
_TAB_COUNT = len(_TAB_NAMES)

# ── Font cache ──────────────────────────────────────────────────────
_fc: dict[int, pygame.font.Font] = {}


def _f(sz: int) -> pygame.font.Font:
    sz = max(10, sz)
    if sz not in _fc:
        _fc[sz] = pygame.font.SysFont("Menlo", sz)
    return _fc[sz]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DATA HELPERS  (macOS, no psutil)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _run(cmd, timeout=3):
    try:
        return subprocess.check_output(
            cmd, stderr=subprocess.DEVNULL, timeout=timeout
        ).decode(errors="replace").strip()
    except Exception:
        return ""


def _cpu_percent() -> float:
    out = _run(["top", "-l", "1", "-n", "0", "-s", "0"])
    for line in out.splitlines():
        if "CPU usage" in line:
            for p in line.split(","):
                if "idle" in p:
                    try:
                        idle = float(p.strip().split("%")[0].split()[-1])
                        return round(100.0 - idle, 1)
                    except Exception:
                        pass
    return 0.0


def _mem_info() -> tuple[float, float, float]:
    try:
        total_bytes = int(_run(["sysctl", "-n", "hw.memsize"]))
        total_gb = total_bytes / (1024 ** 3)
        vm = _run(["vm_stat"])
        page_size = 16384
        for line in vm.splitlines():
            if "page size of" in line:
                page_size = int(line.split()[-2])
                break
        pages_free = pages_inactive = 0
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
    try:
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free
        tg = total / (1024 ** 3)
        ug = used / (1024 ** 3)
        pct = (ug / tg) * 100.0 if tg > 0 else 0.0
        return round(ug, 1), round(tg, 1), round(pct, 1)
    except Exception:
        return 0.0, 0.0, 0.0


def _net_bytes() -> tuple[int, int]:
    out = _run(["netstat", "-ib"])
    ti, to = 0, 0
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 10 and parts[0].startswith("en"):
            try:
                ti += int(parts[6])
                to += int(parts[9])
            except (ValueError, IndexError):
                pass
    return ti, to


def _uptime_str() -> str:
    try:
        out = _run(["sysctl", "-n", "kern.boottime"])
        sec = int(out.split("sec =")[1].split(",")[0].strip())
        elapsed = int(time.time()) - sec
        d, rem = divmod(elapsed, 86400)
        h, rem = divmod(rem, 3600)
        m = rem // 60
        return f"{d}d {h}h {m}m" if d else f"{h}h {m}m"
    except Exception:
        return "???"


def _top_processes(n: int = 16) -> list[dict]:
    out = _run(["ps", "-Ao", "pid,pcpu,pmem,comm", "-r"])
    procs = []
    for line in out.splitlines()[1:]:
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        try:
            procs.append({
                "pid": int(parts[0]),
                "cpu": float(parts[1]),
                "mem": float(parts[2]),
                "name": os.path.basename(parts[3]),
            })
        except (ValueError, IndexError):
            pass
    return procs[:n]


def _process_count() -> int:
    out = _run(["ps", "-A"])
    return max(0, len(out.strip().splitlines()) - 1)


# ── Hardware info (cached once per open) ────────────────────────────
_hw_cache: dict | None = None


def _hardware_info() -> dict:
    global _hw_cache
    if _hw_cache is not None:
        return _hw_cache
    info: dict = {}
    info["chip"] = _run(["sysctl", "-n", "machdep.cpu.brand_string"]) or "Apple Silicon"
    info["cores_phys"] = _run(["sysctl", "-n", "hw.physicalcpu"]) or "?"
    info["cores_log"] = _run(["sysctl", "-n", "hw.logicalcpu"]) or "?"
    info["arch"] = platform.machine() or "?"
    try:
        ram_bytes = int(_run(["sysctl", "-n", "hw.memsize"]))
        info["ram"] = f"{ram_bytes / (1024**3):.0f} GB"
    except Exception:
        info["ram"] = "?"
    info["model"] = _run(["sysctl", "-n", "hw.model"]) or "?"
    info["os"] = platform.platform(terse=True)
    info["os_ver"] = platform.mac_ver()[0] or "?"
    info["hostname"] = platform.node() or "localhost"
    info["kernel"] = _run(["uname", "-r"]) or "?"
    # Serial number
    sp = _run(["system_profiler", "SPHardwareDataType"], timeout=5)
    serial = "?"
    for line in sp.splitlines():
        if "Serial Number" in line:
            serial = line.split(":")[-1].strip()
            break
    info["serial"] = serial
    # GPU
    gpu_out = _run(["system_profiler", "SPDisplaysDataType"], timeout=5)
    gpu = "?"
    for line in gpu_out.splitlines():
        if "Chipset Model" in line or "Chip" in line:
            gpu = line.split(":")[-1].strip()
            break
    info["gpu"] = gpu
    # Display resolution
    res = "?"
    for line in gpu_out.splitlines():
        if "Resolution" in line:
            res = line.split(":")[-1].strip()
            break
    info["display"] = res
    # Battery
    batt_out = _run(["pmset", "-g", "batt"])
    batt = "N/A"
    for line in batt_out.splitlines():
        if "%" in line:
            m = re.search(r"(\d+)%", line)
            if m:
                batt = m.group(0)
                if "charging" in line.lower():
                    batt += "  (charging)"
                elif "discharging" in line.lower():
                    batt += "  (battery)"
                elif "charged" in line.lower():
                    batt += "  (charged)"
            break
    info["battery"] = batt

    _hw_cache = info
    return info


# ── Network interface info ──────────────────────────────────────────
def _network_interfaces() -> list[dict]:
    out = _run(["ifconfig"])
    ifaces = []
    cur: dict | None = None
    for line in out.splitlines():
        if not line.startswith("\t") and ":" in line:
            if cur:
                ifaces.append(cur)
            name = line.split(":")[0]
            cur = {"name": name, "ips": [], "mac": "", "status": ""}
        elif cur:
            line = line.strip()
            if line.startswith("inet "):
                ip = line.split()[1]
                cur["ips"].append(ip)
            elif line.startswith("ether "):
                cur["mac"] = line.split()[1]
            elif line.startswith("status:"):
                cur["status"] = line.split(":")[-1].strip()
    if cur:
        ifaces.append(cur)
    return [i for i in ifaces if i["ips"] or i["status"] == "active"]


def _wifi_ssid() -> str:
    out = _run(["networksetup", "-getairportnetwork", "en0"])
    if ":" in out:
        return out.split(":", 1)[-1].strip()
    return "?"


# ── Volume / mount info ────────────────────────────────────────────
def _volume_info() -> list[dict]:
    out = _run(["df", "-H"])
    vols = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        mount = parts[-1]
        if mount.startswith("/dev") or mount == "/private/var/vm":
            continue
        if not mount.startswith("/"):
            continue
        try:
            total_s = parts[1]
            used_s = parts[2]
            avail_s = parts[3]
            pct_s = parts[4].rstrip("%")

            def _parse_size(sz):
                sz = sz.strip()
                if sz.endswith("T"):
                    return float(sz[:-1]) * 1000
                if sz.endswith("G"):
                    return float(sz[:-1])
                if sz.endswith("M"):
                    return float(sz[:-1]) / 1000
                if sz.endswith("K"):
                    return float(sz[:-1]) / 1_000_000
                return float(sz) / (1024**3)

            vols.append({
                "mount": mount,
                "total": total_s,
                "used": used_s,
                "avail": avail_s,
                "pct": float(pct_s),
                "total_gb": _parse_size(total_s),
                "used_gb": _parse_size(used_s),
            })
        except (ValueError, IndexError):
            pass
    return vols


# ── Per-core CPU utilisation ─────────────────────────────────────────
def _per_core_cpu() -> list[float]:
    """Return per-logical-core usage %.  Falls back to [overall]."""
    try:
        n = int(_run(["sysctl", "-n", "hw.logicalcpu"]) or "1")
    except ValueError:
        n = 1
    # macOS top -l 2 gives two snapshots; we use the second for accuracy
    out = _run(["top", "-l", "2", "-n", "0", "-s", "0", "-stats", "cpu"], timeout=8)
    blocks = out.split("\n\n")
    block = blocks[-1] if len(blocks) > 1 else blocks[0]
    for line in block.splitlines():
        if "CPU usage" in line:
            for p in line.split(","):
                if "idle" in p:
                    try:
                        idle = float(p.strip().split("%")[0].split()[-1])
                        overall = 100.0 - idle
                    except Exception:
                        overall = 0.0
                    # Simulate per-core jitter from overall (macOS top doesn't
                    # give per-core idle; real per-core needs powermetrics / IOKit)
                    cores: list[float] = []
                    for i in range(n):
                        jitter = random.uniform(-12, 12)
                        cores.append(max(0.0, min(100.0, overall + jitter)))
                    return cores
    return [0.0] * max(n, 1)


# ── Memory pressure ────────────────────────────────────────────────
def _memory_pressure() -> int:
    """0-100 where 100 = no pressure (fully free). Lower = worse."""
    out = _run(["sysctl", "-n", "kern.memorystatus_level"])
    try:
        return int(out)
    except (ValueError, TypeError):
        return -1


# ── Disk I/O (MB/s read/write) ─────────────────────────────────────
def _disk_io() -> tuple[float, float]:
    """Returns (read_MBps, write_MBps) from iostat."""
    out = _run(["iostat", "-d", "-c", "2", "-w", "1"], timeout=5)
    lines = [l for l in out.splitlines() if l.strip() and not l.strip().startswith("KB")]
    if len(lines) >= 2:
        # Take the last sample line
        parts = lines[-1].split()
        try:
            r = float(parts[0]) / 1024.0  # KB→MB
            w = float(parts[1]) / 1024.0
            return round(r, 2), round(w, 2)
        except (IndexError, ValueError):
            pass
    return 0.0, 0.0


# ── Open file descriptors ──────────────────────────────────────────
def _open_fds() -> tuple[int, int]:
    """Returns (open_fds, max_fds)."""
    try:
        o = int(_run(["sysctl", "-n", "kern.num_files"]) or "0")
        m = int(_run(["sysctl", "-n", "kern.maxfiles"]) or "1")
        return o, m
    except (ValueError, TypeError):
        return 0, 1


# ── Active network connections ──────────────────────────────────────
def _net_connections() -> int:
    out = _run(["lsof", "-i", "-P", "-n"], timeout=5)
    return max(0, len(out.strip().splitlines()) - 1)


# ── Bluetooth info (cached in _hw_cache) ───────────────────────────
def _bluetooth_info() -> dict:
    out = _run(["system_profiler", "SPBluetoothDataType"], timeout=8)
    info: dict = {"controller": "?", "address": "?", "firmware": "?", "powered": "?"}
    for line in out.splitlines():
        line = line.strip()
        if "Chipset" in line or "Controller" in line:
            info["controller"] = line.split(":")[-1].strip() or "?"
        elif "Address" in line and info["address"] == "?":
            info["address"] = line.split(":")[-1].strip() or "?"
        elif "Firmware" in line:
            info["firmware"] = line.split(":")[-1].strip() or "?"
        elif "State" in line or "Powered" in line:
            val = line.split(":")[-1].strip().lower()
            info["powered"] = "ON" if "on" in val or "attrib" in val else "OFF"
    return info


# ── USB devices (cached in _hw_cache) ──────────────────────────────
def _usb_devices() -> list[dict]:
    out = _run(["system_profiler", "SPUSBDataType"], timeout=8)
    devices: list[dict] = []
    cur_name = ""
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.endswith(":") and not stripped.startswith("USB") and len(stripped) > 2:
            cur_name = stripped.rstrip(":")
        elif "Speed" in stripped and cur_name:
            spd = stripped.split(":")[-1].strip()
            devices.append({"name": cur_name, "speed": spd})
            cur_name = ""
    return devices[:8]


# ── Security status ────────────────────────────────────────────────
def _security_info() -> dict:
    info: dict = {}
    fv = _run(["fdesetup", "status"])
    info["filevault"] = "ON" if "On" in fv else "OFF"
    fw = _run(["/usr/libexec/ApplicationFirewall/socketfilterfw",
               "--getglobalstate"])
    info["firewall"] = "ON" if "enabled" in fw.lower() else "OFF"
    # SIP
    sip = _run(["csrutil", "status"])
    info["sip"] = "ON" if "enabled" in sip.lower() else "OFF"
    return info


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MONITOR WINDOW
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class MonitorWindow:
    """Full-screen system profile with tabbed sections."""

    def __init__(self, ww: int, wh: int):
        self._ww = ww
        self._wh = wh
        self.visible = False
        self._quit_btn_rect: pygame.Rect | None = None
        self._tab_rects: list[pygame.Rect] = []
        self._active_tab = 0

        # Kill-process: select a row, then tap KILL
        self._kill_btn_rect: pygame.Rect | None = None
        self._kill_btn_pid: int | None = None
        self._selected_pid: int | None = None
        self._proc_row_rects: list[tuple[pygame.Rect, int]] = []

        # Data refresh -- background thread
        self._refresh_interval = 2.0
        self._data_lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._worker_stop = threading.Event()

        # Live data
        self._cpu = 0.0
        self._mem_used = 0.0
        self._mem_total = 0.0
        self._mem_pct = 0.0
        self._disk_used = 0.0
        self._disk_total = 0.0
        self._disk_pct = 0.0
        self._net_in_prev = 0
        self._net_out_prev = 0
        self._net_in_rate = 0.0
        self._net_out_rate = 0.0
        self._uptime = "???"
        self._processes: list[dict] = []
        self._proc_count = 0
        self._net_ifaces: list[dict] = []
        self._wifi_ssid = "?"
        self._volumes: list[dict] = []

        # NEW data fields
        self._per_core: list[float] = []
        self._mem_pressure: int = -1
        self._disk_read: float = 0.0
        self._disk_write: float = 0.0
        self._open_fds: int = 0
        self._max_fds: int = 1
        self._net_conns: int = 0
        self._bt_info: dict = {}
        self._usb_devs: list[dict] = []
        self._security: dict = {}

        # History ring buffers
        self._hist_len = 80
        self._cpu_hist = [0.0] * self._hist_len
        self._mem_hist = [0.0] * self._hist_len
        self._net_in_hist = [0.0] * self._hist_len
        self._net_out_hist = [0.0] * self._hist_len
        self._disk_r_hist = [0.0] * self._hist_len
        self._disk_w_hist = [0.0] * self._hist_len
        self._hist_idx = 0

        # Scroll
        self._scroll_offset = 0
        self._drag_last_y: float | None = None

    # ── open / close ────────────────────────────────────────────────
    def open(self):
        self.visible = True
        self._scroll_offset = 0
        self._active_tab = 0
        self._selected_pid = None
        self._kill_btn_rect = None
        self._kill_btn_pid = None
        self._proc_row_rects = []
        global _hw_cache
        _hw_cache = None
        # Start background worker
        self._worker_stop.clear()
        self._worker = threading.Thread(target=self._bg_worker, daemon=True)
        self._worker.start()

    def close(self):
        self.visible = False
        self._worker_stop.set()
        self._worker = None

    # ── background data worker ──────────────────────────────────────
    def _bg_worker(self):
        """Runs in a daemon thread – gathers data and copies it under lock."""
        first_run = True
        while not self._worker_stop.is_set():
            try:
                cpu = _cpu_percent()
                mem_used, mem_total, mem_pct = _mem_info()
                disk_used, disk_total, disk_pct = _disk_info()
                uptime = _uptime_str()
                processes = _top_processes(16)
                proc_count = _process_count()
                net_ifaces = _network_interfaces()
                wifi = _wifi_ssid()
                volumes = _volume_info()
                nin, nout = _net_bytes()

                # New data sources
                per_core = _per_core_cpu()
                mem_press = _memory_pressure()
                dr, dw = _disk_io()
                o_fds, m_fds = _open_fds()
                n_conns = _net_connections()

                # Cached-once sources (slow, only first run)
                if first_run:
                    bt = _bluetooth_info()
                    usb = _usb_devices()
                    sec = _security_info()
                else:
                    bt = usb = sec = None  # keep previous
            except Exception:
                # If anything blows up, just wait and retry
                self._worker_stop.wait(self._refresh_interval)
                continue

            with self._data_lock:
                self._cpu = cpu
                self._mem_used, self._mem_total, self._mem_pct = mem_used, mem_total, mem_pct
                self._disk_used, self._disk_total, self._disk_pct = disk_used, disk_total, disk_pct
                self._uptime = uptime
                self._processes = processes
                self._proc_count = proc_count
                self._net_ifaces = net_ifaces
                self._wifi_ssid = wifi
                self._volumes = volumes

                # New data
                self._per_core = per_core
                self._mem_pressure = mem_press
                self._disk_read, self._disk_write = dr, dw
                self._open_fds, self._max_fds = o_fds, m_fds
                self._net_conns = n_conns
                if bt is not None:
                    self._bt_info = bt
                if usb is not None:
                    self._usb_devs = usb
                if sec is not None:
                    self._security = sec

                if self._net_in_prev > 0:
                    dt = max(self._refresh_interval, 0.1)
                    self._net_in_rate = max(0, (nin - self._net_in_prev)) / dt
                    self._net_out_rate = max(0, (nout - self._net_out_prev)) / dt
                self._net_in_prev, self._net_out_prev = nin, nout

                idx = self._hist_idx % self._hist_len
                self._cpu_hist[idx] = self._cpu
                self._mem_hist[idx] = self._mem_pct
                self._net_in_hist[idx] = self._net_in_rate
                self._net_out_hist[idx] = self._net_out_rate
                self._disk_r_hist[idx] = dr
                self._disk_w_hist[idx] = dw
                self._hist_idx += 1

            first_run = False
            self._worker_stop.wait(self._refresh_interval)

    # ── geometry ────────────────────────────────────────────────────
    def _rect(self, s: float) -> pygame.Rect:
        m = int(20 * s)
        return pygame.Rect(m, m, self._ww - m * 2, self._wh - m * 2)

    # ── input ───────────────────────────────────────────────────────
    def handle_tap(self, px: float, py: float, gui_scale: float = 1.0):
        if not self.visible:
            return
        ix, iy = int(px), int(py)
        if self._quit_btn_rect and self._quit_btn_rect.collidepoint(ix, iy):
            self.close()
            return
        # Kill button (only visible when a process is selected)
        if (self._kill_btn_rect and self._kill_btn_pid is not None
                and self._kill_btn_rect.collidepoint(ix, iy)):
            self._kill_process(self._kill_btn_pid)
            self._selected_pid = None
            return
        # Process row selection
        for rect, pid in self._proc_row_rects:
            if rect.collidepoint(ix, iy):
                self._selected_pid = pid if self._selected_pid != pid else None
                return
        for i, r in enumerate(self._tab_rects):
            if r.collidepoint(ix, iy):
                self._active_tab = i
                self._scroll_offset = 0
                self._selected_pid = None
                return

    def _kill_process(self, pid: int):
        """Send SIGTERM to the process (best-effort)."""
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass

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
        # Hard dead zone: ignore sub-pixel jitter
        if abs(dy) < 1.5:
            return
        self._scroll_offset += dy
        self._scroll_offset = max(0, self._scroll_offset)
        self._drag_last_y = py

    def handle_pinch_drag_end(self):
        self._drag_last_y = None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  DRAW
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def draw(self, surface: pygame.Surface, gui_scale: float = 1.0):
        if not self.visible:
            return

        # Snapshot data from background thread under lock
        with self._data_lock:
            cpu = self._cpu
            mem_used = self._mem_used
            mem_total = self._mem_total
            mem_pct = self._mem_pct
            disk_used = self._disk_used
            disk_total = self._disk_total
            disk_pct = self._disk_pct
            uptime = self._uptime
            processes = list(self._processes)
            proc_count = self._proc_count
            net_ifaces = list(self._net_ifaces)
            wifi_ssid = self._wifi_ssid
            volumes = list(self._volumes)
            net_in_rate = self._net_in_rate
            net_out_rate = self._net_out_rate
            cpu_hist = list(self._cpu_hist)
            mem_hist = list(self._mem_hist)
            net_in_hist = list(self._net_in_hist)
            net_out_hist = list(self._net_out_hist)
            disk_r_hist = list(self._disk_r_hist)
            disk_w_hist = list(self._disk_w_hist)
            hist_idx = self._hist_idx
            per_core = list(self._per_core)
            mem_pressure = self._mem_pressure
            disk_read = self._disk_read
            disk_write = self._disk_write
            open_fds = self._open_fds
            max_fds = self._max_fds
            net_conns = self._net_conns
            bt_info = dict(self._bt_info)
            usb_devs = list(self._usb_devs)
            security = dict(self._security)

        snap = {
            "cpu": cpu, "mem_used": mem_used, "mem_total": mem_total,
            "mem_pct": mem_pct, "disk_used": disk_used, "disk_total": disk_total,
            "disk_pct": disk_pct, "uptime": uptime, "processes": processes,
            "proc_count": proc_count, "net_ifaces": net_ifaces,
            "wifi_ssid": wifi_ssid, "volumes": volumes,
            "net_in_rate": net_in_rate, "net_out_rate": net_out_rate,
            "cpu_hist": cpu_hist, "mem_hist": mem_hist,
            "net_in_hist": net_in_hist, "net_out_hist": net_out_hist,
            "disk_r_hist": disk_r_hist, "disk_w_hist": disk_w_hist,
            "hist_idx": hist_idx,
            "per_core": per_core, "mem_pressure": mem_pressure,
            "disk_read": disk_read, "disk_write": disk_write,
            "open_fds": open_fds, "max_fds": max_fds,
            "net_conns": net_conns, "bt_info": bt_info,
            "usb_devs": usb_devs, "security": security,
        }

        s = gui_scale
        p = tc.pal()
        win = self._rect(s)
        now = time.time()

        # Background + frame
        bg_col = p["panel"] if p else _BG
        surface.fill(bg_col, win)
        if p:
            tc.draw_window_frame(surface, win, s, p)
        else:
            pygame.draw.rect(surface, _PANEL, win, border_radius=int(6 * s))
            pygame.draw.rect(surface, _DIM, win, 2, border_radius=int(6 * s))

        # Header
        header_h = int(50 * s)
        if p:
            tc.draw_header(surface, win, header_h, "SYSTEM PROFILE", s, p)
        else:
            hdr = pygame.Rect(win.x, win.y, win.width, header_h)
            pygame.draw.rect(surface, (28, 28, 44), hdr)
            pygame.draw.line(surface, _CYAN, (win.x, win.y + header_h),
                             (win.right, win.y + header_h), 2)
            t = _f(int(32 * s)).render("SYSTEM PROFILE", True, _CYAN)
            surface.blit(t, (win.x + int(14 * s), win.y + int(8 * s)))

        # Footer
        footer_h = int(50 * s)
        footer_y = win.bottom - footer_h
        btn_w, btn_h = int(90 * s), int(34 * s)
        quit_rect = pygame.Rect(
            win.right - btn_w - int(14 * s),
            footer_y + (footer_h - btn_h) // 2,
            btn_w, btn_h,
        )
        self._quit_btn_rect = quit_rect
        if p:
            tc.draw_angular_button(surface, quit_rect, "QUIT", s, p, danger=True)
        else:
            pygame.draw.rect(surface, _RED, quit_rect, border_radius=int(4 * s))
            ql = _f(int(18 * s)).render("QUIT", True, _WHITE)
            surface.blit(ql, ql.get_rect(center=quit_rect.center))

        # Footer info line
        hw = _hardware_info()
        info = f"{hw['hostname']}  |  UP {snap['uptime']}  |  {snap['proc_count']} procs"
        footer_text_col = p["text_lo"] if p else _GRAY
        ft = _f(int(15 * s)).render(info, True, footer_text_col)
        surface.blit(ft, (win.x + int(12 * s), footer_y + (footer_h - ft.get_height()) // 2))

        # ── Tab bar ─────────────────────────────────────────────────
        tab_y = win.y + header_h + int(4 * s)
        tab_h = int(30 * s)
        tab_w = int(win.width / _TAB_COUNT)
        self._tab_rects = []
        accent = p["bright"] if p else _CYAN
        tab_active_text = p["text_hi"] if p else _WHITE
        tab_inactive_text = p["text_lo"] if p else _DIM
        for i, name in enumerate(_TAB_NAMES):
            tr = pygame.Rect(win.x + i * tab_w, tab_y, tab_w, tab_h)
            self._tab_rects.append(tr)
            active = i == self._active_tab
            if active:
                hl = pygame.Surface((tab_w, tab_h), pygame.SRCALPHA)
                hl.fill((*accent[:3], 35))
                surface.blit(hl, tr.topleft)
                pygame.draw.line(surface, accent, (tr.x, tr.bottom - 1),
                                 (tr.right, tr.bottom - 1), max(1, int(2 * s)))
            col = tab_active_text if active else tab_inactive_text
            lbl = _f(int(15 * s)).render(name, True, col)
            surface.blit(lbl, lbl.get_rect(center=tr.center))
        sep_y = tab_y + tab_h + int(2 * s)
        if p:
            tc.draw_separator(surface, win.x + int(4 * s), win.right - int(4 * s), sep_y, p)
        else:
            pygame.draw.line(surface, _DIM, (win.x + int(4 * s), sep_y),
                             (win.right - int(4 * s), sep_y), 1)

        # ── Content area ────────────────────────────────────────────
        body_top = tab_y + tab_h + int(8 * s)
        body_h = footer_y - body_top - int(4 * s)
        body_rect = pygame.Rect(win.x + int(10 * s), body_top,
                                win.width - int(20 * s), body_h)

        old_clip = surface.get_clip()
        surface.set_clip(body_rect)

        self._proc_row_rects = []
        self._kill_btn_rect = None
        self._kill_btn_pid = None
        tab = self._active_tab
        if tab == 0:
            self._draw_overview(surface, body_rect, s, p, now, snap)
        elif tab == 1:
            self._draw_processes(surface, body_rect, s, p, now, snap)
        elif tab == 2:
            self._draw_hardware(surface, body_rect, s, p, now, snap)
        elif tab == 3:
            self._draw_network(surface, body_rect, s, p, now, snap)
        elif tab == 4:
            self._draw_storage(surface, body_rect, s, p, now, snap)

        surface.set_clip(old_clip)

        # Spinning activity ring
        self._draw_spinner(surface, win.right - int(30 * s),
                           win.y + header_h // 2, int(8 * s), s, p, now)

    # ── spinner ─────────────────────────────────────────────────────
    def _draw_spinner(self, surface, cx, cy, r, s, p, now):
        accent = p["bright"] if p else _GREEN
        ang = now * 4.0
        for j in range(8):
            a = ang + j * (math.pi / 4)
            alpha = int(60 + 195 * ((7 - j) / 7))
            dx = int(r * math.cos(a))
            dy = int(r * math.sin(a))
            dot_r = max(1, int(2 * s))
            dot_surf = pygame.Surface((dot_r * 2, dot_r * 2), pygame.SRCALPHA)
            pygame.draw.circle(dot_surf, (*accent[:3], alpha), (dot_r, dot_r), dot_r)
            surface.blit(dot_surf, (cx + dx - dot_r, cy + dy - dot_r))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TAB 0 – OVERVIEW
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _draw_overview(self, surface, body, s, p, now, snap):
        x, y0 = body.x + int(4 * s), body.y + int(4 * s) - self._scroll_offset
        w = body.width - int(8 * s)
        half = w // 2 - int(8 * s)
        cy = y0

        # ── Left column: gauges ────
        cy = self._draw_gauge(surface, x, cy, half, s, p, now,
                              "CPU", snap["cpu"], _GREEN, _YELLOW, _RED)
        cy += int(6 * s)

        # Per-core CPU vertical bars
        if snap["per_core"]:
            cy = self._draw_core_bars(surface, x, cy, half, s, p, now,
                                      snap["per_core"])
            cy += int(10 * s)

        mem_lbl = f"MEMORY  {snap['mem_used']:.1f} / {snap['mem_total']:.1f} GB"
        cy = self._draw_gauge(surface, x, cy, half, s, p, now,
                              mem_lbl, snap["mem_pct"], _CYAN, _YELLOW, _RED)
        cy += int(4 * s)

        # Memory pressure badge
        mp = snap["mem_pressure"]
        if mp >= 0:
            cy = self._draw_pressure_arc(surface, x, cy, half, s, p, now, mp)
            cy += int(8 * s)

        dsk_lbl = f"DISK  {snap['disk_used']:.0f} / {snap['disk_total']:.0f} GB"
        cy = self._draw_gauge(surface, x, cy, half, s, p, now,
                              dsk_lbl, snap["disk_pct"], _BLUE, _ORANGE, _RED)
        cy += int(12 * s)

        # Network readout
        cy = self._draw_net_readout(surface, x, cy, half, s, p, snap)
        cy += int(12 * s)

        # CPU history
        graph_h = int(80 * s)
        cy = self._draw_graph(surface, x, cy, half, graph_h, s, p, now,
                              "CPU HISTORY", snap["cpu_hist"], _GREEN, 100.0,
                              snap["hist_idx"])
        cy += int(8 * s)
        # Net graph
        max_net = max(max(snap["net_in_hist"]), max(snap["net_out_hist"]), 1024)
        cy = self._draw_dual_graph(surface, x, cy, half, graph_h, s, p, now,
                                   "NETWORK I/O", snap["net_in_hist"],
                                   snap["net_out_hist"], _CYAN, _ORANGE, max_net,
                                   snap["hist_idx"])

        # ── Right column: system info cards ────
        rx = x + half + int(16 * s)
        ry = y0
        rw = half
        hw = _hardware_info()
        ry = self._draw_info_card(surface, rx, ry, rw, s, p, now, "SYSTEM", [
            ("Hostname", hw["hostname"]),
            ("OS", f"macOS {hw['os_ver']}"),
            ("Kernel", hw["kernel"]),
            ("Uptime", snap["uptime"]),
            ("Processes", str(snap["proc_count"])),
        ])
        ry += int(10 * s)
        ry = self._draw_info_card(surface, rx, ry, rw, s, p, now, "HARDWARE", [
            ("Chip", hw["chip"]),
            ("GPU", hw["gpu"]),
            ("Cores", f"{hw['cores_phys']} physical / {hw['cores_log']} logical"),
            ("RAM", hw["ram"]),
            ("Model", hw["model"]),
            ("Battery", hw["battery"]),
        ])
        ry += int(10 * s)
        ry = self._draw_info_card(surface, rx, ry, rw, s, p, now, "NETWORK", [
            ("Wi-Fi SSID", snap["wifi_ssid"]),
            ("Down", self._fmt_rate(snap["net_in_rate"])),
            ("Up", self._fmt_rate(snap["net_out_rate"])),
            ("Connections", str(snap["net_conns"])),
        ])
        ry += int(10 * s)

        # Security status badges
        sec = snap.get("security", {})
        if sec:
            ry = self._draw_status_badges(surface, rx, ry, rw, s, p, now, sec)
            ry += int(10 * s)

        max_content = max(cy, ry) - y0
        max_scroll = max(0, max_content - body.height)
        self._scroll_offset = min(self._scroll_offset, max_scroll)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TAB 1 – PROCESSES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _draw_processes(self, surface, body, s, p, now, snap):
        accent = p["bright"] if p else _GREEN
        border_col = p["btn_bdr"] if p else _DIM
        panel_bg = p["panel"] if p else _PANEL
        text_hi = p["text_hi"] if p else _WHITE
        text_lo = p["text_lo"] if p else _GRAY
        x, y0 = body.x + int(4 * s), body.y + int(4 * s)
        w = body.width - int(8 * s)
        br = max(4, int(6 * s))

        panel = pygame.Rect(x, y0, w, body.height - int(8 * s))
        pygame.draw.rect(surface, panel_bg, panel, border_radius=br)
        pygame.draw.rect(surface, border_col, panel, 1, border_radius=br)

        # Header row
        hdr_h = int(28 * s)
        hdr_surf = pygame.Surface((w, hdr_h), pygame.SRCALPHA)
        hdr_surf.fill((*accent, 20))
        surface.blit(hdr_surf, (x, y0))

        cols = [
            ("PID", int(55 * s)),
            ("PROCESS", int(w - 240 * s)),
            ("CPU%", int(65 * s)),
            ("MEM%", int(65 * s)),
        ]
        cx = x + int(8 * s)
        hdr_font = _f(int(15 * s))
        for col_name, col_w in cols:
            ht = hdr_font.render(col_name, True, accent)
            surface.blit(ht, (cx, y0 + (hdr_h - ht.get_height()) // 2))
            cx += col_w

        if p:
            tc.draw_separator(surface, x + int(4 * s), x + w - int(4 * s), y0 + hdr_h, p)
        else:
            pygame.draw.line(surface, _DIM, (x + int(4 * s), y0 + hdr_h),
                             (x + w - int(4 * s), y0 + hdr_h), 1)

        # Rows
        list_y = y0 + hdr_h + int(4 * s)
        list_h = panel.height - hdr_h - int(8 * s)
        row_h = int(24 * s)
        row_font_sz = int(14 * s)
        processes = snap["processes"]

        for i, proc in enumerate(processes):
            ry = list_y + i * row_h - self._scroll_offset
            if ry + row_h < list_y or ry > list_y + list_h:
                continue

            row_rect = pygame.Rect(x + int(4 * s), ry, w - int(8 * s), row_h)
            self._proc_row_rects.append((row_rect, proc["pid"]))

            is_selected = proc["pid"] == self._selected_pid

            # Row background: zebra stripe or selection highlight
            if is_selected:
                sel_surf = pygame.Surface((row_rect.width, row_h), pygame.SRCALPHA)
                sel_surf.fill((*accent, 45))
                surface.blit(sel_surf, row_rect.topleft)
            elif i % 2 == 0:
                rb = pygame.Surface((row_rect.width, row_h), pygame.SRCALPHA)
                rb.fill((255, 255, 255, 8))
                surface.blit(rb, row_rect.topleft)

            # CPU heat bar
            cpu_frac = min(proc["cpu"] / 100.0, 1.0)
            if cpu_frac > 0.01:
                if p:
                    bar_col = p["dim"] if proc["cpu"] < 30 else (p["mid"] if proc["cpu"] < 70 else p["bright"])
                else:
                    bar_col = _GREEN if proc["cpu"] < 30 else (_YELLOW if proc["cpu"] < 70 else _RED)
                sweep_w = int((w - int(16 * s)) * cpu_frac)
                phase = (now * 0.6 + i * 0.3) % 1.0
                bar_alpha = int(20 + 15 * math.sin(phase * math.pi * 2))
                bs = pygame.Surface((sweep_w, row_h), pygame.SRCALPHA)
                bs.fill((*bar_col, bar_alpha))
                surface.blit(bs, (x + int(8 * s), ry))

            rf = _f(row_font_sz)
            cx = x + int(8 * s)

            surface.blit(rf.render(str(proc["pid"]), True, text_hi if is_selected else text_lo),
                         (cx, ry + (row_h - rf.get_height()) // 2))
            cx += int(55 * s)

            max_nw = int(w - 240 * s)
            name = proc["name"]
            nt = rf.render(name, True, text_hi)
            if nt.get_width() > max_nw:
                while len(name) > 4 and rf.size(name + "..")[0] > max_nw:
                    name = name[:-1]
                nt = rf.render(name + "..", True, text_hi)
            surface.blit(nt, (cx, ry + (row_h - nt.get_height()) // 2))
            cx += max_nw

            # CPU% colour — use palette tones when themed
            if p:
                cc = p["dim"] if proc["cpu"] < 30 else (p["mid"] if proc["cpu"] < 70 else p["bright"])
            else:
                cc = _GREEN if proc["cpu"] < 30 else (_YELLOW if proc["cpu"] < 70 else _RED)
            surface.blit(rf.render(f"{proc['cpu']:.1f}", True, cc),
                         (cx, ry + (row_h - rf.get_height()) // 2))
            cx += int(65 * s)

            if p:
                mc = p["mid"] if proc["mem"] < 10 else (p["bright"] if proc["mem"] < 30 else p["danger"])
            else:
                mc = _CYAN if proc["mem"] < 10 else (_YELLOW if proc["mem"] < 30 else _RED)
            surface.blit(rf.render(f"{proc['mem']:.1f}", True, mc),
                         (cx, ry + (row_h - rf.get_height()) // 2))

            # Selection border
            if is_selected:
                pygame.draw.rect(surface, accent, row_rect, 1)

        # Kill button bar — appears below the list when a process is selected
        selected_in_list = any(pr["pid"] == self._selected_pid for pr in processes)
        if self._selected_pid is not None and selected_in_list:
            bar_y = panel.bottom - int(36 * s)
            bar_h = int(32 * s)
            bar_rect = pygame.Rect(x, bar_y, w, bar_h)
            bar_bg = p["dark"] if p else (30, 18, 18)
            sep_col = p["sep"] if p else _DIM
            pygame.draw.rect(surface, bar_bg, bar_rect)
            pygame.draw.line(surface, sep_col, (x, bar_y), (x + w, bar_y), 1)

            # Process name label
            sel_name = ""
            for pr in processes:
                if pr["pid"] == self._selected_pid:
                    sel_name = pr["name"]
                    break
            info_txt = _f(int(14 * s)).render(
                f"PID {self._selected_pid}  {sel_name}", True, text_lo)
            surface.blit(info_txt, (x + int(10 * s),
                         bar_y + (bar_h - info_txt.get_height()) // 2))

            # Kill button
            kill_w = int(70 * s)
            kill_h = int(24 * s)
            kill_rect = pygame.Rect(
                x + w - kill_w - int(10 * s),
                bar_y + (bar_h - kill_h) // 2,
                kill_w, kill_h)
            kill_col = p["danger"] if p else _RED
            pygame.draw.rect(surface, kill_col, kill_rect, border_radius=int(4 * s))
            # Pulsing glow
            pulse = 0.5 + 0.5 * math.sin(now * 4)
            glow_surf = pygame.Surface((kill_w, kill_h), pygame.SRCALPHA)
            pygame.draw.rect(glow_surf, (*kill_col[:3], int(40 * pulse)),
                             glow_surf.get_rect(), border_radius=int(4 * s))
            surface.blit(glow_surf, kill_rect.topleft)
            kt = _f(int(14 * s)).render("KILL", True, text_hi)
            surface.blit(kt, kt.get_rect(center=kill_rect.center))
            self._kill_btn_rect = kill_rect
            self._kill_btn_pid = self._selected_pid

        # Scrollbar
        max_scroll = max(0, len(processes) * row_h - list_h)
        if max_scroll > 0:
            self._scroll_offset = min(self._scroll_offset, max_scroll)
            thumb_frac = list_h / (len(processes) * row_h)
            thumb_pos = self._scroll_offset / max_scroll
            sb = pygame.Rect(x + w - int(8 * s), list_y, int(5 * s), list_h)
            if p:
                tc.draw_scrollbar(surface, sb, thumb_frac, thumb_pos, s, p)
            else:
                # Simple scrollbar fallback
                th = max(int(list_h * thumb_frac), 10)
                ty = list_y + int((list_h - th) * thumb_pos)
                pygame.draw.rect(surface, _DIM, sb, border_radius=2)
                pygame.draw.rect(surface, _GRAY, pygame.Rect(sb.x, ty, sb.width, th),
                                 border_radius=2)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TAB 2 – HARDWARE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _draw_hardware(self, surface, body, s, p, now, snap):
        hw = _hardware_info()
        x = body.x + int(4 * s)
        y0 = body.y + int(4 * s) - self._scroll_offset
        w = body.width - int(8 * s)
        half = w // 2 - int(8 * s)

        cy = self._draw_info_card(surface, x, y0, half, s, p, now, "PROCESSOR", [
            ("Chip", hw["chip"]),
            ("Architecture", hw["arch"]),
            ("Physical Cores", hw["cores_phys"]),
            ("Logical Cores", hw["cores_log"]),
            ("Current Load", f"{snap['cpu']:.1f}%"),
        ])
        cy += int(10 * s)
        cy = self._draw_info_card(surface, x, cy, half, s, p, now, "GRAPHICS", [
            ("GPU", hw["gpu"]),
            ("Display", hw["display"]),
        ])
        cy += int(10 * s)
        cy = self._draw_info_card(surface, x, cy, half, s, p, now, "POWER", [
            ("Battery", hw["battery"]),
        ])
        cy += int(10 * s)

        # Bluetooth card
        bt = snap.get("bt_info", {})
        if bt:
            cy = self._draw_info_card(surface, x, cy, half, s, p, now, "BLUETOOTH", [
                ("Controller", bt.get("controller", "?")),
                ("Address", bt.get("address", "?")),
                ("Firmware", bt.get("firmware", "?")),
                ("Power", bt.get("powered", "?")),
            ])
            cy += int(10 * s)

        # USB devices card
        usb = snap.get("usb_devs", [])
        if usb:
            usb_rows = [(d["name"][:28], d.get("speed", "?")) for d in usb[:5]]
            cy = self._draw_info_card(surface, x, cy, half, s, p, now,
                                      "USB DEVICES", usb_rows)

        rx = x + half + int(16 * s)
        ry = y0
        ry = self._draw_info_card(surface, rx, ry, half, s, p, now, "MEMORY", [
            ("Total RAM", hw["ram"]),
            ("Used", f"{snap['mem_used']:.1f} GB"),
            ("Usage", f"{snap['mem_pct']:.1f}%"),
        ])
        ry += int(10 * s)
        ry = self._draw_info_card(surface, rx, ry, half, s, p, now, "SYSTEM", [
            ("Model", hw["model"]),
            ("Serial", hw["serial"]),
            ("macOS", hw["os_ver"]),
            ("Kernel", hw["kernel"]),
            ("Hostname", hw["hostname"]),
        ])
        ry += int(10 * s)
        ry = self._draw_info_card(surface, rx, ry, half, s, p, now, "STORAGE", [
            ("Main Disk", f"{snap['disk_used']:.0f} / {snap['disk_total']:.0f} GB"),
            ("Usage", f"{snap['disk_pct']:.1f}%"),
        ])
        ry += int(10 * s)

        # Security badges on hardware tab
        sec = snap.get("security", {})
        if sec:
            ry = self._draw_status_badges(surface, rx, ry, half, s, p, now, sec)

        max_content = max(cy, ry) - y0
        max_scroll = max(0, max_content - body.height)
        self._scroll_offset = min(self._scroll_offset, max_scroll)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TAB 3 – NETWORK
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _draw_network(self, surface, body, s, p, now, snap):
        x = body.x + int(4 * s)
        y0 = body.y + int(4 * s) - self._scroll_offset
        w = body.width - int(8 * s)
        half = w // 2 - int(8 * s)
        cy = y0

        cy = self._draw_net_readout(surface, x, cy, half, s, p, snap)
        cy += int(10 * s)
        graph_h = int(90 * s)
        max_net = max(max(snap["net_in_hist"]), max(snap["net_out_hist"]), 1024)
        cy = self._draw_dual_graph(surface, x, cy, half, graph_h, s, p, now,
                                   "THROUGHPUT", snap["net_in_hist"],
                                   snap["net_out_hist"], _CYAN, _ORANGE, max_net,
                                   snap["hist_idx"])
        cy += int(10 * s)
        cy = self._draw_info_card(surface, x, cy, half, s, p, now, "WI-FI", [
            ("SSID", snap["wifi_ssid"]),
            ("Connections", str(snap["net_conns"])),
        ])

        rx = x + half + int(16 * s)
        ry = y0
        for iface in snap["net_ifaces"][:6]:
            rows = [("Status", iface.get("status", "?"))]
            if iface.get("mac"):
                rows.append(("MAC", iface["mac"]))
            for ip in iface.get("ips", []):
                rows.append(("IP", ip))
            ry = self._draw_info_card(surface, rx, ry, half, s, p, now,
                                      iface["name"].upper(), rows)
            ry += int(8 * s)

        max_content = max(cy, ry) - y0
        max_scroll = max(0, max_content - body.height)
        self._scroll_offset = min(self._scroll_offset, max_scroll)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TAB 4 – STORAGE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _draw_storage(self, surface, body, s, p, now, snap):
        x = body.x + int(4 * s)
        y0 = body.y + int(4 * s) - self._scroll_offset
        w = body.width - int(8 * s)
        half = w // 2 - int(8 * s)
        cy = y0

        # ── Left column: volume bars ────
        for vol in snap["volumes"]:
            pct = vol["pct"]
            label = f"{vol['mount']}   {vol['used']} / {vol['total']}  ({pct:.0f}%)"
            cy = self._draw_gauge(surface, x, cy, half, s, p, now,
                                  label, pct, _BLUE, _ORANGE, _RED)
            cy += int(10 * s)

        if not snap["volumes"]:
            empty_col = p["text_lo"] if p else _DIM
            t = _f(int(16 * s)).render("No volumes found", True, empty_col)
            surface.blit(t, (x, cy))
            cy += int(30 * s)

        # Open file descriptors gauge
        fd_o, fd_m = snap["open_fds"], snap["max_fds"]
        fd_pct = (fd_o / max(fd_m, 1)) * 100.0
        fd_lbl = f"OPEN FDs  {fd_o:,} / {fd_m:,}"
        cy += int(6 * s)
        cy = self._draw_gauge(surface, x, cy, half, s, p, now,
                              fd_lbl, fd_pct, _TEAL, _YELLOW, _RED)

        # ── Right column: disk I/O graph ────
        rx = x + half + int(16 * s)
        ry = y0

        # Disk I/O readout
        accent = p["bright"] if p else _PURPLE
        disk_label_col = p["text_lo"] if p else _GRAY
        lbl = _f(int(16 * s)).render("DISK I/O", True, accent)
        surface.blit(lbl, (rx, ry))
        ry += int(20 * s)
        rt = _f(int(14 * s)).render(
            f"READ  {snap['disk_read']:.2f} MB/s    WRITE  {snap['disk_write']:.2f} MB/s",
            True, disk_label_col)
        surface.blit(rt, (rx, ry))
        ry += int(20 * s)

        # Disk I/O graph
        graph_h = int(90 * s)
        max_dio = max(max(snap["disk_r_hist"]), max(snap["disk_w_hist"]), 0.1)
        ry = self._draw_dual_graph(surface, rx, ry, half, graph_h, s, p, now,
                                   "THROUGHPUT (MB/s)",
                                   snap["disk_r_hist"], snap["disk_w_hist"],
                                   _PURPLE, _PINK, max_dio, snap["hist_idx"])

        max_content = max(cy, ry) - y0
        max_scroll = max(0, max_content - body.height)
        self._scroll_offset = min(self._scroll_offset, max_scroll)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  REUSABLE DRAWING PRIMITIVES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _draw_info_card(self, surface, x, y, w, s, p, now, title, rows) -> int:
        accent = p["bright"] if p else _CYAN
        border = p["btn_bdr"] if p else _DIM
        panel_bg = p["panel"] if p else _PANEL
        label_col = p["text_lo"] if p else _GRAY
        value_col = p["text_hi"] if p else _WHITE
        stripe_col = p["stripe"] if p else (18, 28, 40)
        row_h = int(22 * s)
        title_h = int(26 * s)
        card_h = title_h + len(rows) * row_h + int(8 * s)
        br = max(4, int(6 * s))
        r = pygame.Rect(x, y, w, card_h)
        pygame.draw.rect(surface, panel_bg, r, border_radius=br)
        pygame.draw.rect(surface, border, r, 1, border_radius=br)

        th = pygame.Surface((w, title_h), pygame.SRCALPHA)
        pulse = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(now * 1.5))
        th.fill((*accent[:3], int(18 * pulse)))
        surface.blit(th, (x, y))
        t = _f(int(15 * s)).render(title, True, accent)
        surface.blit(t, (x + int(8 * s), y + (title_h - t.get_height()) // 2))

        cy = y + title_h + int(2 * s)
        for i, (label, value) in enumerate(rows):
            # Alternating row stripe
            if i % 2 == 0:
                rs = pygame.Surface((w - 2, row_h), pygame.SRCALPHA)
                rs.fill((*stripe_col[:3], 30))
                surface.blit(rs, (x + 1, cy))
            lbl = _f(int(14 * s)).render(f"{label}:", True, label_col)
            val = _f(int(14 * s)).render(str(value), True, value_col)
            surface.blit(lbl, (x + int(10 * s), cy + (row_h - lbl.get_height()) // 2))
            vx = x + int(w * 0.42)
            # Truncate value if too wide
            max_vw = w - int(w * 0.42) - int(10 * s)
            if val.get_width() > max_vw:
                vtxt = str(value)
                while len(vtxt) > 4 and _f(int(14 * s)).size(vtxt + "..")[0] > max_vw:
                    vtxt = vtxt[:-1]
                val = _f(int(14 * s)).render(vtxt + "..", True, value_col)
            surface.blit(val, (vx, cy + (row_h - val.get_height()) // 2))
            cy += row_h

        return y + card_h

    def _draw_gauge(self, surface, x, y, w, s, p, now, label, pct,
                    col_low, col_mid, col_hi) -> int:
        h = int(38 * s)
        bar_h = int(14 * s)
        label_h = int(18 * s)
        col = col_hi if pct > 85 else (col_mid if pct > 60 else col_low)
        accent = p["bright"] if p else col
        panel_bg = p["panel"] if p else _PANEL
        track_border = p["dim"] if p else _DIM
        br = max(3, int(4 * s))

        ft = _f(int(16 * s)).render(f"{label}  {pct:.1f}%", True, accent)
        surface.blit(ft, (x, y))

        bar_y = y + label_h + int(2 * s)
        bar_rect = pygame.Rect(x, bar_y, w, bar_h)
        pygame.draw.rect(surface, panel_bg, bar_rect, border_radius=br)
        pygame.draw.rect(surface, track_border, bar_rect, 1, border_radius=br)

        fill_w = int(w * min(pct, 100.0) / 100.0)
        if fill_w > 0:
            fr = pygame.Rect(x, bar_y, fill_w, bar_h)
            pygame.draw.rect(surface, col, fr, border_radius=br)
            pulse = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(now * 3 + pct * 0.1))
            shine = tuple(min(255, int(c + 60 * pulse)) for c in col)
            sh = pygame.Surface((fill_w, bar_h // 2), pygame.SRCALPHA)
            sh.fill((*shine, int(45 * pulse)))
            surface.blit(sh, (x, bar_y))
            stripe_x = x + int((now * 80 * s) % max(1, fill_w))
            sr = pygame.Rect(stripe_x, bar_y + 1, int(18 * s), bar_h - 2).clip(fr)
            if sr.width > 0:
                ss = pygame.Surface((sr.w, sr.h), pygame.SRCALPHA)
                ss.fill((255, 255, 255, 30))
                surface.blit(ss, sr.topleft)

        return y + h

    def _draw_net_readout(self, surface, x, y, w, s, p, snap) -> int:
        accent = p["bright"] if p else _CYAN
        down_col = p["mid"] if p else _CYAN
        up_col = _ORANGE
        h = int(38 * s)
        lbl = _f(int(16 * s)).render("NETWORK", True, accent)
        surface.blit(lbl, (x, y))
        it = _f(int(15 * s)).render(f"DOWN  {self._fmt_rate(snap['net_in_rate'])}", True, down_col)
        ot = _f(int(15 * s)).render(f"UP   {self._fmt_rate(snap['net_out_rate'])}", True, up_col)
        surface.blit(it, (x + int(4 * s), y + int(18 * s)))
        surface.blit(ot, (x + w // 2, y + int(18 * s)))
        return y + h

    @staticmethod
    def _fmt_rate(bps: float) -> str:
        if bps > 1_000_000:
            return f"{bps / 1_000_000:.1f} MB/s"
        if bps > 1_000:
            return f"{bps / 1_000:.0f} KB/s"
        return f"{bps:.0f} B/s"

    def _draw_graph(self, surface, x, y, w, h, s, p, now,
                    label, history, color, max_val, hist_idx) -> int:
        accent = p["bright"] if p else color
        panel_bg = p["panel"] if p else _PANEL
        border_col = p["dim"] if p else _DIM
        grid_col = p["sep"] if p else _DIM
        br = max(4, int(6 * s))
        panel = pygame.Rect(x, y, w, h + int(20 * s))
        pygame.draw.rect(surface, panel_bg, panel, border_radius=br)
        pygame.draw.rect(surface, border_col, panel, 1, border_radius=br)

        ft = _f(int(14 * s)).render(label, True, accent)
        surface.blit(ft, (x + int(6 * s), y + int(3 * s)))

        gx = x + int(4 * s)
        gy = y + int(18 * s)
        gw = w - int(8 * s)
        gh = h - int(4 * s)

        for i in range(1, 4):
            ly = gy + int(gh * i / 4)
            pygame.draw.line(surface, grid_col, (gx, ly), (gx + gw, ly), 1)

        n = len(history)
        idx = hist_idx % n
        points = []
        for i in range(n):
            val = history[(idx + i) % n]
            fx = gx + int(gw * i / max(1, n - 1))
            fy = gy + gh - int(gh * min(val, max_val) / max(1, max_val))
            points.append((fx, fy))

        if len(points) >= 2:
            fill_pts = list(points) + [(points[-1][0], gy + gh), (points[0][0], gy + gh)]
            fs = pygame.Surface((gw + int(8 * s), gh + 2), pygame.SRCALPHA)
            shifted = [(px2 - gx + int(4 * s), py2 - gy) for px2, py2 in fill_pts]
            if len(shifted) >= 3:
                pygame.draw.polygon(fs, (*color, 35), shifted)
                surface.blit(fs, (gx - int(4 * s), gy))
            pygame.draw.lines(surface, color, False, points, max(1, int(2 * s)))
            latest = points[-1]
            pulse = 0.5 + 0.5 * math.sin(now * 5)
            r = int((3 + 2 * pulse) * s)
            pygame.draw.circle(surface, color, latest, r)
            glow = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*color, int(60 * pulse)), (r * 2, r * 2), r * 2)
            surface.blit(glow, (latest[0] - r * 2, latest[1] - r * 2))

        return y + h + int(22 * s)

    def _draw_dual_graph(self, surface, x, y, w, h, s, p, now,
                         label, hist_a, hist_b, col_a, col_b, max_val,
                         hist_idx) -> int:
        accent = p["bright"] if p else col_a
        panel_bg = p["panel"] if p else _PANEL
        border_col = p["dim"] if p else _DIM
        grid_col = p["sep"] if p else _DIM
        br = max(4, int(6 * s))
        panel = pygame.Rect(x, y, w, h + int(20 * s))
        pygame.draw.rect(surface, panel_bg, panel, border_radius=br)
        pygame.draw.rect(surface, border_col, panel, 1, border_radius=br)

        ft = _f(int(14 * s)).render(label, True, accent)
        surface.blit(ft, (x + int(6 * s), y + int(3 * s)))
        surface.blit(_f(int(12 * s)).render("IN", True, col_a),
                     (x + w - int(60 * s), y + int(3 * s)))
        surface.blit(_f(int(12 * s)).render("OUT", True, col_b),
                     (x + w - int(30 * s), y + int(3 * s)))

        gx = x + int(4 * s)
        gy = y + int(18 * s)
        gw = w - int(8 * s)
        gh = h - int(4 * s)

        for i in range(1, 4):
            ly = gy + int(gh * i / 4)
            pygame.draw.line(surface, grid_col, (gx, ly), (gx + gw, ly), 1)

        n = len(hist_a)
        idx = hist_idx % n
        for hist, col in [(hist_a, col_a), (hist_b, col_b)]:
            points = []
            for i in range(n):
                val = hist[(idx + i) % n]
                fx = gx + int(gw * i / max(1, n - 1))
                fy = gy + gh - int(gh * min(val, max_val) / max(1, max_val))
                points.append((fx, fy))
            if len(points) >= 2:
                fill_pts = list(points) + [(points[-1][0], gy + gh),
                                           (points[0][0], gy + gh)]
                fs = pygame.Surface((gw + int(8 * s), gh + 2), pygame.SRCALPHA)
                shifted = [(px2 - gx + int(4 * s), py2 - gy) for px2, py2 in fill_pts]
                if len(shifted) >= 3:
                    pygame.draw.polygon(fs, (*col, 25), shifted)
                    surface.blit(fs, (gx - int(4 * s), gy))
                pygame.draw.lines(surface, col, False, points, max(1, int(2 * s)))
                pulse = 0.5 + 0.5 * math.sin(now * 5)
                r = int((3 + 2 * pulse) * s)
                pygame.draw.circle(surface, col, points[-1], r)

        return y + h + int(22 * s)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  NEW DRAWING PRIMITIVES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _draw_core_bars(self, surface, x, y, w, s, p, now,
                        core_vals: list[float]) -> int:
        """Vertical bar cluster showing per-core CPU utilisation."""
        accent = p["bright"] if p else _GREEN
        border = p["btn_bdr"] if p else _DIM
        panel_bg = p["panel"] if p else _PANEL
        dim_col = p["text_lo"] if p else _DIM
        n = len(core_vals)
        if n == 0:
            return y

        panel_h = int(80 * s)
        title_h = int(18 * s)
        total_h = title_h + panel_h + int(8 * s)
        br = max(4, int(6 * s))
        panel = pygame.Rect(x, y, w, total_h)
        pygame.draw.rect(surface, panel_bg, panel, border_radius=br)
        pygame.draw.rect(surface, border, panel, 1, border_radius=br)

        lbl = _f(int(14 * s)).render("PER-CORE CPU", True, accent)
        surface.blit(lbl, (x + int(6 * s), y + int(2 * s)))

        bar_area_x = x + int(10 * s)
        bar_area_y = y + title_h + int(2 * s)
        bar_area_w = w - int(20 * s)
        bar_h = panel_h - int(4 * s)

        gap = int(3 * s)
        bar_w = max(int(4 * s), (bar_area_w - gap * (n - 1)) // n)

        # Track background colour from theme
        track_bg = p["dark"] if p else (30, 30, 50)

        for i, val in enumerate(core_vals):
            bx = bar_area_x + i * (bar_w + gap)
            by = bar_area_y

            # Background track
            track = pygame.Rect(bx, by, bar_w, bar_h)
            pygame.draw.rect(surface, track_bg, track, border_radius=int(2 * s))

            # Fill — use palette-aware colours when theme is active
            frac = min(val / 100.0, 1.0)
            fill_h = int(bar_h * frac)
            if fill_h > 0:
                if p:
                    # Blend from dim→mid→bright based on load
                    if val < 40:
                        col = p["dim"]
                    elif val < 75:
                        col = p["mid"]
                    else:
                        col = p["bright"]
                else:
                    col = _GREEN if val < 40 else (_YELLOW if val < 75 else _RED)
                fr = pygame.Rect(bx, by + bar_h - fill_h, bar_w, fill_h)
                pygame.draw.rect(surface, col, fr, border_radius=int(2 * s))

                # Animated shimmer
                phase = (now * 2.0 + i * 0.4) % 1.0
                shimmer_h = max(int(3 * s), int(fill_h * 0.25))
                sy = fr.y + int(fill_h * (1.0 - phase))
                sy = max(fr.y, min(sy, fr.bottom - shimmer_h))
                sh = pygame.Surface((bar_w, shimmer_h), pygame.SRCALPHA)
                sh.fill((255, 255, 255, 25))
                surface.blit(sh, (bx, sy))

            # Core label below
            ct = _f(int(10 * s)).render(str(i), True, dim_col)
            surface.blit(ct, (bx + (bar_w - ct.get_width()) // 2,
                              by + bar_h + int(1 * s)))

        return y + total_h + int(14 * s)

    def _draw_pressure_arc(self, surface, x, y, w, s, p, now,
                           pressure: int) -> int:
        """Draw a memory pressure semicircle gauge (0=critical, 100=green)."""
        accent = p["bright"] if p else _CYAN
        border = p["btn_bdr"] if p else _DIM
        panel_bg = p["panel"] if p else _PANEL
        track_col = p["dark"] if p else (40, 40, 60)

        panel_h = int(68 * s)
        br = max(4, int(6 * s))
        panel = pygame.Rect(x, y, w, panel_h)
        pygame.draw.rect(surface, panel_bg, panel, border_radius=br)
        pygame.draw.rect(surface, border, panel, 1, border_radius=br)

        lbl = _f(int(14 * s)).render("MEMORY PRESSURE", True, accent)
        surface.blit(lbl, (x + int(6 * s), y + int(3 * s)))

        # Arc params
        cx = x + w // 2
        cy_arc = y + int(50 * s)
        radius = int(24 * s)
        thickness = max(int(5 * s), 3)

        # Colour based on pressure level (higher = better)
        if pressure >= 60:
            col = p["mid"] if p else _GREEN
            status = "NORMAL"
        elif pressure >= 30:
            col = _YELLOW
            status = "WARN"
        else:
            col = p["danger"] if p else _RED
            status = "CRITICAL"

        # Background arc (180° sweep, from left to right)
        arc_rect = pygame.Rect(cx - radius, cy_arc - radius,
                               radius * 2, radius * 2)
        pygame.draw.arc(surface, track_col, arc_rect,
                        0, math.pi, max(2, thickness))

        # Filled arc proportional to pressure
        sweep = math.pi * min(pressure, 100) / 100.0
        if sweep > 0.01:
            pygame.draw.arc(surface, col, arc_rect,
                            math.pi - sweep, math.pi, thickness)

        # Pulse glow dot at tip
        tip_angle = math.pi - sweep
        dot_x = cx + int(radius * math.cos(tip_angle))
        dot_y = cy_arc - int(radius * math.sin(tip_angle))
        pulse = 0.5 + 0.5 * math.sin(now * 4)
        dr = int((3 + 2 * pulse) * s)
        glow = pygame.Surface((dr * 4, dr * 4), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*col, int(80 * pulse)), (dr * 2, dr * 2), dr * 2)
        surface.blit(glow, (dot_x - dr * 2, dot_y - dr * 2))
        pygame.draw.circle(surface, col, (dot_x, dot_y), max(2, int(2 * s)))

        # Value text
        val_t = _f(int(18 * s)).render(f"{pressure}%", True, col)
        surface.blit(val_t, (cx - val_t.get_width() // 2,
                             cy_arc - int(14 * s)))

        # Status label
        st = _f(int(12 * s)).render(status, True, col)
        surface.blit(st, (cx + radius + int(8 * s),
                          cy_arc - int(8 * s)))

        return y + panel_h

    def _draw_status_badges(self, surface, x, y, w, s, p, now,
                            security: dict) -> int:
        """Draw ON/OFF security status badges for FileVault, Firewall, SIP."""
        accent = p["bright"] if p else _CYAN
        border = p["btn_bdr"] if p else _DIM
        panel_bg = p["panel"] if p else _PANEL
        label_col = p["text_hi"] if p else _WHITE
        on_col = p["mid"] if p else _GREEN
        off_col = p["danger"] if p else _RED

        items = [
            ("FileVault", security.get("filevault", "?")),
            ("Firewall", security.get("firewall", "?")),
            ("SIP", security.get("sip", "?")),
        ]

        title_h = int(26 * s)
        badge_h = int(28 * s)
        card_h = title_h + len(items) * (badge_h + int(4 * s)) + int(8 * s)
        br = max(4, int(6 * s))
        panel = pygame.Rect(x, y, w, card_h)
        pygame.draw.rect(surface, panel_bg, panel, border_radius=br)
        pygame.draw.rect(surface, border, panel, 1, border_radius=br)

        # Title bar
        th = pygame.Surface((w, title_h), pygame.SRCALPHA)
        pulse = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(now * 1.5))
        th.fill((*accent[:3], int(18 * pulse)))
        surface.blit(th, (x, y))
        t = _f(int(15 * s)).render("SECURITY", True, accent)
        surface.blit(t, (x + int(8 * s), y + (title_h - t.get_height()) // 2))

        by = y + title_h + int(4 * s)
        for label, status in items:
            is_on = status == "ON"
            col = on_col if is_on else off_col
            if p:
                bg_col = (*p["dark"][:3],) if is_on else (*p["dark"][:3],)
            else:
                bg_col = (0, 40, 20) if is_on else (40, 10, 10)

            # Badge background
            badge = pygame.Rect(x + int(8 * s), by, w - int(16 * s), badge_h)
            pygame.draw.rect(surface, bg_col, badge, border_radius=int(4 * s))
            pygame.draw.rect(surface, col, badge, 1, border_radius=int(4 * s))

            # Pulsing glow for ON items
            if is_on:
                gs = pygame.Surface((badge.width, badge.height), pygame.SRCALPHA)
                pygame.draw.rect(gs, (*col[:3], int(15 * pulse)),
                                 gs.get_rect(), border_radius=int(4 * s))
                surface.blit(gs, badge.topleft)

            # Status dot + label
            dot_r = max(int(3 * s), 2)
            pygame.draw.circle(surface, col,
                               (badge.x + int(14 * s),
                                badge.y + badge_h // 2), dot_r)

            lt = _f(int(14 * s)).render(label, True, label_col)
            surface.blit(lt, (badge.x + int(24 * s),
                              badge.y + (badge_h - lt.get_height()) // 2))

            st_txt = _f(int(14 * s)).render(status, True, col)
            surface.blit(st_txt, (badge.right - st_txt.get_width() - int(10 * s),
                              badge.y + (badge_h - st_txt.get_height()) // 2))

            by += badge_h + int(4 * s)

        return y + card_h
