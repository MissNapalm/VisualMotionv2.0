"""
File Explorer app — browse real folders and files.
Pinch-tap to navigate folders and select files.
Sound effects: browse.mp3 (enter folder), select.mp3 (select file),
               whoosh.mp3 (back / up).
"""
import os
import subprocess
import pygame
import theme_chrome as tc

# ── Colours ─────────────────────────────────────────────────────────
_BG        = (22, 22, 34)
_HEADER    = (32, 32, 52)
_WHITE     = (255, 255, 255)
_GRAY      = (160, 160, 180)
_LTGRAY    = (80, 80, 100)
_BLUE      = (70, 140, 240)
_CYAN      = (0, 200, 180)
_FOLDER_C  = (255, 200, 60)
_FILE_C    = (180, 200, 220)
_SELECTED  = (50, 80, 130)
_STRIPE    = (28, 28, 44)
_BTN_BG    = (45, 55, 80)
_BTN_HOVER = (60, 80, 120)
_BTN_TEXT  = (200, 220, 255)
_PATH_BG   = (26, 26, 40)
_SCROLLBAR = (60, 70, 100)
_SCROLLBAR_T = (90, 110, 160)
_DARK      = (18, 18, 28)

# ── Font cache ──────────────────────────────────────────────────────
_fc: dict[int, pygame.font.Font] = {}


def _f(size: int) -> pygame.font.Font:
    size = max(10, size)
    if size not in _fc:
        _fc[size] = pygame.font.Font(None, size)
    return _fc[size]


# ── helpers ─────────────────────────────────────────────────────────
def _human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.0f} {unit}" if unit == "B" else f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


# ── FilesWindow ─────────────────────────────────────────────────────

class FilesWindow:
    """Full-screen file explorer with pinch navigation."""

    def __init__(self, screen_w: int, screen_h: int):
        self.visible = False
        self._sw = screen_w
        self._sh = screen_h

        # navigation state
        self._cwd = os.path.expanduser("~")
        self._history: list[str] = []       # stack for back button
        self._entries: list[dict] = []       # cached dir listing
        self._selected_idx: int = -1        # currently highlighted entry
        self._scroll_offset: int = 0        # pixel scroll offset

        # hit areas rebuilt each frame
        self._entry_rects: list[tuple[pygame.Rect, int]] = []  # (rect, entry_index)
        self._back_btn_rect: pygame.Rect | None = None
        self._up_btn_rect:   pygame.Rect | None = None
        self._quit_btn_rect: pygame.Rect | None = None

        # pinch-drag scroll state
        self._drag_last_y: float | None = None

        # sounds
        try:
            self._snd_browse = pygame.mixer.Sound("browse.mp3")
            self._snd_browse.set_volume(0.5)
        except Exception:
            self._snd_browse = None
        try:
            self._snd_select = pygame.mixer.Sound("select.mp3")
            self._snd_select.set_volume(0.5)
        except Exception:
            self._snd_select = None
        try:
            self._snd_whoosh = pygame.mixer.Sound("whoosh.mp3")
            self._snd_whoosh.set_volume(0.5)
        except Exception:
            self._snd_whoosh = None

        self._ROW_H = 42  # row height in pixels (before gui_scale)

    # ── open / close ────────────────────────────────────────────────
    def open(self):
        self.visible = True
        self._history.clear()
        self._cwd = os.path.expanduser("~")
        self._selected_idx = -1
        self._scroll_offset = 0
        self._refresh()

    def close(self):
        self.visible = False

    # ── directory listing ───────────────────────────────────────────
    def _refresh(self):
        """Re-read the current directory."""
        self._entries.clear()
        self._selected_idx = -1
        self._scroll_offset = 0
        try:
            raw = os.listdir(self._cwd)
        except OSError:
            raw = []
        dirs = []
        files = []
        for name in sorted(raw, key=str.lower):
            if name.startswith("."):
                continue  # skip hidden
            full = os.path.join(self._cwd, name)
            try:
                is_dir = os.path.isdir(full)
            except OSError:
                continue
            try:
                size = os.path.getsize(full) if not is_dir else 0
            except OSError:
                size = 0
            entry = {"name": name, "is_dir": is_dir, "size": size, "path": full}
            if is_dir:
                dirs.append(entry)
            else:
                files.append(entry)
        self._entries = dirs + files

    def _navigate(self, path: str):
        """Enter a directory, pushing current to history."""
        self._history.append(self._cwd)
        self._cwd = path
        self._refresh()
        if self._snd_browse:
            self._snd_browse.play()

    def _go_back(self):
        """Pop history stack."""
        if self._history:
            self._cwd = self._history.pop()
            self._refresh()
            if self._snd_whoosh:
                self._snd_whoosh.play()

    def _go_up(self):
        """Navigate to parent directory."""
        parent = os.path.dirname(self._cwd)
        if parent and parent != self._cwd:
            self._history.append(self._cwd)
            self._cwd = parent
            self._refresh()
            if self._snd_whoosh:
                self._snd_whoosh.play()

    # ── layout helpers ──────────────────────────────────────────────
    def _rect(self, s: float) -> pygame.Rect:
        """Main window rect (padded from screen edges)."""
        w = min(int(1200 * s), self._sw - 20)
        h = min(int(720 * s), self._sh - 20)
        return pygame.Rect((self._sw - w) // 2, (self._sh - h) // 2, w, h)

    # ── handle_tap ──────────────────────────────────────────────────
    def handle_tap(self, px: float, py: float, gui_scale: float = 1.0) -> bool:
        """Process a pinch-tap or mouse click. Returns True if consumed.
        Single tap SELECTS items (puts a box around them).
        Use handle_double_tap() to open folders."""
        if not self.visible:
            return False
        ipx, ipy = int(px), int(py)

        # Quit button
        if self._quit_btn_rect and self._quit_btn_rect.collidepoint(ipx, ipy):
            self.close()
            if self._snd_whoosh:
                self._snd_whoosh.play()
            return True

        # Back button
        if self._back_btn_rect and self._back_btn_rect.collidepoint(ipx, ipy):
            self._go_back()
            return True

        # Up button
        if self._up_btn_rect and self._up_btn_rect.collidepoint(ipx, ipy):
            self._go_up()
            return True

        # Entry icons — single tap = select / deselect
        for rect, idx in self._entry_rects:
            if rect.collidepoint(ipx, ipy):
                if self._selected_idx == idx:
                    self._selected_idx = -1   # deselect
                else:
                    self._selected_idx = idx  # select
                if self._snd_select:
                    self._snd_select.play()
                return True
        return False

    def handle_double_tap(self, px: float, py: float, gui_scale: float = 1.0) -> bool:
        """Double-pinch / double-click opens a folder or a file with the OS."""
        if not self.visible:
            return False
        ipx, ipy = int(px), int(py)
        for rect, idx in self._entry_rects:
            if rect.collidepoint(ipx, ipy):
                entry = self._entries[idx]
                if entry["is_dir"]:
                    self._navigate(entry["path"])
                    return True
                else:
                    # Open the file with the default OS application
                    try:
                        subprocess.Popen(["open", entry["path"]])
                    except Exception:
                        pass
                    return True
        return False

    def handle_scroll(self, dy: int):
        """Mouse wheel scroll."""
        if not self.visible:
            return
        self._scroll_offset += dy * 30
        self._clamp_scroll(1.0)

    def handle_pinch_drag(self, px: float, py: float, gui_scale: float = 1.0):
        """Pinch-drag scrolling inside the explorer window."""
        if not self.visible:
            return
        win = self._rect(gui_scale)
        if not win.collidepoint(int(px), int(py)):
            return
        if self._drag_last_y is None:
            self._drag_last_y = py
            return
        dy = self._drag_last_y - py   # drag up => positive offset => scroll down
        self._scroll_offset += dy
        self._clamp_scroll(gui_scale)
        self._drag_last_y = py

    def handle_pinch_drag_end(self):
        """Reset drag tracking when pinch is released."""
        self._drag_last_y = None

    def _clamp_scroll(self, s: float):
        win = self._rect(s)
        header_h = int(60 * s)
        footer_h = int(80 * s)
        body_h = win.height - header_h - footer_h
        # Icon grid layout
        icon_cell_w = int(110 * s)
        icon_cell_h = int(100 * s)
        pad = int(16 * s)
        cols = max(1, (win.width - pad * 2) // icon_cell_w)
        rows = (len(self._entries) + cols - 1) // cols if self._entries else 1
        content_h = rows * icon_cell_h
        max_scroll = max(0, content_h - body_h)
        self._scroll_offset = max(0, min(self._scroll_offset, max_scroll))

    # ── hit_test (for close-by-tap-outside) ─────────────────────────
    def hit_test(self, px, py, gui_scale):
        return self._rect(gui_scale).collidepoint(int(px), int(py))

    # ── draw ────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface, gui_scale: float = 1.0):
        if not self.visible:
            return
        s = gui_scale
        win = self._rect(s)
        self._clamp_scroll(s)

        p = tc.pal()  # None if classic

        # ── Background ──
        if p:
            tc.draw_window_frame(surface, win, s, p)
        else:
            bg = pygame.Surface((win.width, win.height), pygame.SRCALPHA)
            bg.fill(_BG)
            surface.blit(bg, win.topleft)
            pygame.draw.rect(surface, _LTGRAY, win, width=2, border_radius=8)

        self._entry_rects.clear()

        # ── Layout constants ──
        header_h = int(60 * s)
        footer_h = int(80 * s)

        # ── Header: title + path bar ──
        if p:
            tc.draw_header(surface, win, header_h, "FILE EXPLORER", s, p)
        else:
            header_r = pygame.Rect(win.x, win.y, win.width, header_h)
            pygame.draw.rect(surface, _HEADER, header_r)
            pygame.draw.line(surface, _LTGRAY, (win.x, win.y + header_h),
                             (win.right, win.y + header_h), 2)
            title = _f(int(28 * s)).render("File Explorer", True, _WHITE)
            surface.blit(title, (win.x + int(20 * s), win.y + int(6 * s)))

        # Path bar (inside header, right of title)
        path_r = pygame.Rect(win.x + int(220 * s), win.y + int(6 * s),
                              win.width - int(240 * s), int(26 * s))
        if p:
            tc.draw_path_bar(surface, self._cwd, path_r, s, p)
        else:
            max_path_w = path_r.width - int(16 * s)
            path_text = self._cwd
            path_font = _f(int(18 * s))
            while path_font.size(path_text)[0] > max_path_w and len(path_text) > 20:
                path_text = "..." + path_text[4:]
            pygame.draw.rect(surface, _PATH_BG, path_r, border_radius=6)
            path_img = path_font.render(path_text, True, _GRAY)
            surface.blit(path_img, (path_r.x + int(8 * s),
                                    path_r.centery - path_img.get_height() // 2))

        # Entry count (below title in header)
        n_dirs = sum(1 for e in self._entries if e["is_dir"])
        n_files = len(self._entries) - n_dirs
        count_text = f"{n_dirs} folders, {n_files} files"
        count_c = p["text_lo"] if p else _LTGRAY
        count_img = _f(int(16 * s)).render(count_text, True, count_c)
        surface.blit(count_img, (win.x + int(20 * s), win.y + int(36 * s)))

        # ── Icon grid body ──
        body_top = win.y + header_h + 2
        body_h = win.height - header_h - footer_h - 2

        icon_cell_w = int(110 * s)
        icon_cell_h = int(100 * s)
        pad = int(16 * s)
        cols = max(1, (win.width - pad * 2) // icon_cell_w)
        grid_w = cols * icon_cell_w
        grid_x0 = win.x + (win.width - grid_w) // 2

        # Clip to body area
        clip_rect = pygame.Rect(win.x, body_top, win.width, body_h)
        old_clip = surface.get_clip()
        surface.set_clip(clip_rect)

        if not self._entries:
            empty_c = p["text_lo"] if p else _LTGRAY
            empty = _f(int(24 * s)).render("(empty folder)", True, empty_c)
            surface.blit(empty, empty.get_rect(center=(win.centerx, body_top + body_h // 2)))
        else:
            total_rows = (len(self._entries) + cols - 1) // cols
            first_row = max(0, int(self._scroll_offset / icon_cell_h) - 1)
            last_row = min(total_rows, int((self._scroll_offset + body_h) / icon_cell_h) + 2)

            for row in range(first_row, last_row):
                for col in range(cols):
                    idx = row * cols + col
                    if idx >= len(self._entries):
                        break
                    entry = self._entries[idx]
                    cx = grid_x0 + col * icon_cell_w + icon_cell_w // 2
                    cy = body_top + row * icon_cell_h - self._scroll_offset + icon_cell_h // 2

                    if cy + icon_cell_h // 2 < body_top or cy - icon_cell_h // 2 > body_top + body_h:
                        continue

                    cell_rect = pygame.Rect(cx - icon_cell_w // 2, cy - icon_cell_h // 2,
                                            icon_cell_w, icon_cell_h)

                    # ── OS-style icon box ──
                    box_inset = int(3 * s)
                    box_r = pygame.Rect(cell_rect.x + box_inset, cell_rect.y + box_inset,
                                        cell_rect.width - box_inset * 2,
                                        cell_rect.height - box_inset * 2)
                    br = max(4, int(8 * s))

                    if idx == self._selected_idx:
                        # Selected: filled highlight + bright border
                        if p:
                            sel_s = pygame.Surface((box_r.width, box_r.height), pygame.SRCALPHA)
                            sel_c = p["sel_bg"] if len(p["sel_bg"]) == 4 else (*p["sel_bg"][:3], 120)
                            sel_s.fill(sel_c)
                            surface.blit(sel_s, box_r.topleft)
                            pygame.draw.rect(surface, p["bright"], box_r, max(2, int(2 * s)), br)
                        else:
                            pygame.draw.rect(surface, _SELECTED, box_r, border_radius=br)
                            pygame.draw.rect(surface, _BLUE, box_r, width=2, border_radius=br)
                    else:
                        # Unselected: subtle outline box (like OS explorer)
                        if p:
                            pygame.draw.rect(surface, (*p["dim"][:3], 50) if len(p["dim"]) == 3
                                             else p["dim"], box_r, max(1, int(1 * s)), br)
                        else:
                            pygame.draw.rect(surface, (45, 45, 65), box_r, width=1, border_radius=br)

                    # Icon
                    icon_sz = int(44 * s)
                    icon_y = cy - int(14 * s)

                    if entry["is_dir"]:
                        self._draw_folder_icon(surface, cx, icon_y, icon_sz, s, p)
                    else:
                        self._draw_file_icon(surface, cx, icon_y, icon_sz, s, p, entry["name"])

                    # Name label
                    name_y = icon_y + icon_sz // 2 + int(6 * s)
                    if p:
                        name_c = p["folder"] if entry["is_dir"] else p["text_hi"]
                    else:
                        name_c = _FOLDER_C if entry["is_dir"] else _WHITE
                    name_font = _f(int(16 * s))
                    display_name = entry["name"]
                    max_name_w = icon_cell_w - int(8 * s)
                    if name_font.size(display_name)[0] > max_name_w:
                        while len(display_name) > 4 and name_font.size(display_name + "...")[0] > max_name_w:
                            display_name = display_name[:-1]
                        display_name = display_name + "..."
                    name_img = name_font.render(display_name, True, name_c)
                    surface.blit(name_img, name_img.get_rect(centerx=cx, top=name_y))

                    # Size label for files
                    if not entry["is_dir"]:
                        size_y = name_y + name_img.get_height() + int(1 * s)
                        size_c = p["text_lo"] if p else _GRAY
                        size_img = _f(int(12 * s)).render(_human_size(entry["size"]), True, size_c)
                        surface.blit(size_img, size_img.get_rect(centerx=cx, top=size_y))

                    self._entry_rects.append((cell_rect, idx))

        surface.set_clip(old_clip)

        # ── Scrollbar ──
        total_rows = max(1, (len(self._entries) + cols - 1) // cols) if self._entries else 1
        content_h = total_rows * icon_cell_h
        if content_h > body_h and content_h > 0:
            sb_w = int(5 * s)
            sb_x = win.right - int(8 * s)
            if p:
                track_r = pygame.Rect(sb_x, body_top + 2, sb_w, body_h - 4)
                thumb_frac = body_h / content_h
                pos_frac = self._scroll_offset / max(1, content_h - body_h)
                tc.draw_scrollbar(surface, track_r, thumb_frac, pos_frac, s, p)
            else:
                sb_track_h = body_h - 4
                sb_thumb_h = max(int(20 * s), int(sb_track_h * body_h / content_h))
                sb_thumb_y = body_top + 2 + int((sb_track_h - sb_thumb_h) *
                             self._scroll_offset / max(1, content_h - body_h))
                pygame.draw.rect(surface, _SCROLLBAR,
                                 (sb_x, body_top + 2, sb_w, sb_track_h), border_radius=3)
                pygame.draw.rect(surface, _SCROLLBAR_T,
                                 (sb_x, sb_thumb_y, sb_w, sb_thumb_h), border_radius=3)

        # ── Footer: BACK / UP / QUIT buttons at the BOTTOM ──
        footer_y = win.bottom - footer_h
        # Separator line above footer
        if p:
            tc.draw_separator(surface, win.x + int(8 * s), win.right - int(8 * s), footer_y, p)
        else:
            pygame.draw.line(surface, _LTGRAY, (win.x, footer_y), (win.right, footer_y), 2)

        btn_w = int(200 * s)
        btn_h = int(55 * s)
        btn_y = footer_y + (footer_h - btn_h) // 2
        btn_gap = int(14 * s)

        # Back button (bottom-left)
        btn_x = win.x + int(16 * s)
        self._back_btn_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
        can_back = len(self._history) > 0
        if p:
            tc.draw_angular_button(surface, self._back_btn_rect, "<  BACK", s, p, enabled=can_back)
        else:
            bbg = _BTN_BG if can_back else (35, 35, 50)
            bbc = _BLUE if can_back else _LTGRAY
            pygame.draw.rect(surface, bbg, self._back_btn_rect, border_radius=10)
            pygame.draw.rect(surface, bbc, self._back_btn_rect, width=2, border_radius=10)
            bl = _f(int(28 * s)).render("<  BACK", True, _BTN_TEXT if can_back else _LTGRAY)
            surface.blit(bl, bl.get_rect(center=self._back_btn_rect.center))

        # Up button (next to back)
        ux = btn_x + btn_w + btn_gap
        self._up_btn_rect = pygame.Rect(ux, btn_y, btn_w, btn_h)
        if p:
            tc.draw_angular_button(surface, self._up_btn_rect, "^  UP", s, p)
        else:
            pygame.draw.rect(surface, _BTN_BG, self._up_btn_rect, border_radius=10)
            pygame.draw.rect(surface, _BLUE, self._up_btn_rect, width=2, border_radius=10)
            ul = _f(int(28 * s)).render("^  UP", True, _BTN_TEXT)
            surface.blit(ul, ul.get_rect(center=self._up_btn_rect.center))

        # Quit button (bottom-right)
        qx = win.right - btn_w - int(16 * s)
        self._quit_btn_rect = pygame.Rect(qx, btn_y, btn_w, btn_h)
        if p:
            tc.draw_angular_button(surface, self._quit_btn_rect, "X  QUIT", s, p, danger=True)
        else:
            pygame.draw.rect(surface, (140, 50, 50), self._quit_btn_rect, border_radius=10)
            pygame.draw.rect(surface, (200, 80, 80), self._quit_btn_rect, width=2, border_radius=10)
            ql = _f(int(28 * s)).render("X  QUIT", True, _WHITE)
            surface.blit(ql, ql.get_rect(center=self._quit_btn_rect.center))

    # ── Icon drawing helpers ────────────────────────────────────────
    def _draw_folder_icon(self, surface, cx, cy, sz, s, p):
        """Draw an OS-style folder icon centred at (cx, cy)."""
        w = sz
        h = int(sz * 0.75)
        x, y = cx - w // 2, cy - h // 2
        tab_w = int(w * 0.4)
        tab_h = int(h * 0.15)
        body_top = y + tab_h

        if p:
            # Angular sci-fi folder
            cut = max(3, int(6 * s))
            # Tab
            tab_pts = [(x, body_top), (x, y), (x + tab_w, y),
                       (x + tab_w + int(6 * s), body_top)]
            pygame.draw.polygon(surface, p["folder"], tab_pts)
            # Body
            body_pts = [
                (x, body_top),
                (x + w - cut, body_top),
                (x + w, body_top + cut),
                (x + w, y + h),
                (x + cut, y + h),
                (x, y + h - cut),
            ]
            pygame.draw.polygon(surface, p["folder"], body_pts)
            # Outline
            pygame.draw.polygon(surface, p["dim"], body_pts, max(1, int(2 * s)))
            # Inner line
            pygame.draw.line(surface, p["panel"],
                             (x + int(4 * s), body_top + int(4 * s)),
                             (x + w - int(4 * s), body_top + int(4 * s)),
                             max(1, int(2 * s)))
        else:
            # Classic warm folder
            base = _FOLDER_C
            dark = (200, 160, 30)
            # Tab
            tab_pts = [(x, body_top), (x, y), (x + tab_w, y),
                       (x + tab_w + int(6 * s), body_top)]
            pygame.draw.polygon(surface, base, tab_pts)
            pygame.draw.polygon(surface, dark, tab_pts, 1)
            # Body
            body_r = pygame.Rect(x, body_top, w, h - tab_h)
            pygame.draw.rect(surface, base, body_r, border_radius=max(2, int(4 * s)))
            pygame.draw.rect(surface, dark, body_r, width=1, border_radius=max(2, int(4 * s)))
            # Highlight line
            pygame.draw.line(surface, (255, 230, 130),
                             (x + 3, body_top + 3), (x + w - 3, body_top + 3), 1)

    def _draw_file_icon(self, surface, cx, cy, sz, s, p, filename):
        """Draw an OS-style file/document icon centred at (cx, cy)."""
        w = int(sz * 0.7)
        h = sz
        x, y = cx - w // 2, cy - h // 2
        fold = max(4, int(w * 0.25))

        # Determine accent color from file extension
        ext = os.path.splitext(filename)[1].lower()
        ext_colors_classic = {
            ".py": (80, 180, 80), ".js": (240, 220, 60), ".ts": (60, 120, 220),
            ".html": (230, 100, 50), ".css": (60, 150, 220), ".json": (180, 140, 60),
            ".md": (120, 160, 200), ".txt": (180, 200, 220), ".pdf": (220, 60, 60),
            ".png": (180, 100, 220), ".jpg": (180, 100, 220), ".jpeg": (180, 100, 220),
            ".mp3": (220, 80, 160), ".mp4": (100, 80, 220), ".zip": (160, 140, 100),
        }
        if p:
            file_body = p["panel"]
            file_border = p["file"]
            # Extension tag color
            ext_tag = p["bright"] if ext in (".py", ".js", ".ts") else p["mid"]
        else:
            file_body = _FILE_C
            file_border = (140, 160, 180)
            ext_tag = ext_colors_classic.get(ext, (160, 170, 190))

        # Document shape with folded corner
        pts = [
            (x, y), (x + w - fold, y), (x + w, y + fold),
            (x + w, y + h), (x, y + h),
        ]

        if p:
            pygame.draw.polygon(surface, file_body, pts)
            pygame.draw.polygon(surface, file_border, pts, max(1, int(2 * s)))
            # Fold triangle
            fold_pts = [(x + w - fold, y), (x + w, y + fold), (x + w - fold, y + fold)]
            pygame.draw.polygon(surface, p["dim"], fold_pts)
            pygame.draw.polygon(surface, file_border, fold_pts, 1)
            # Data lines
            for li in range(4):
                ly = y + fold + int((4 + li * 5) * s)
                if ly < y + h - int(4 * s):
                    lw = w - int(8 * s) - (int(8 * s) if li == 3 else 0)
                    pygame.draw.line(surface, p["dim"],
                                     (x + int(4 * s), ly), (x + int(4 * s) + lw, ly), 1)
            # Extension tag
            if ext:
                tag_font = _f(max(8, int(11 * s)))
                tag_text = ext[1:].upper()[:4]
                tag_img = tag_font.render(tag_text, True, ext_tag)
                surface.blit(tag_img, tag_img.get_rect(centerx=cx,
                             bottom=y + h - int(3 * s)))
        else:
            pygame.draw.polygon(surface, file_body, pts)
            pygame.draw.polygon(surface, file_border, pts, 1)
            # Fold
            fold_pts = [(x + w - fold, y), (x + w, y + fold), (x + w - fold, y + fold)]
            pygame.draw.polygon(surface, file_border, fold_pts)
            # Lines
            for li in range(4):
                ly = y + fold + int((4 + li * 5) * s)
                if ly < y + h - int(4 * s):
                    lw = w - int(8 * s) - (int(6 * s) if li == 3 else 0)
                    pygame.draw.line(surface, (140, 155, 170),
                                     (x + int(4 * s), ly), (x + int(4 * s) + lw, ly), 1)
            # Extension tag
            if ext:
                tag_font = _f(max(8, int(11 * s)))
                tag_text = ext[1:].upper()[:4]
                tag_img = tag_font.render(tag_text, True, ext_tag)
                tag_bg = pygame.Rect(0, 0, tag_img.get_width() + int(6 * s),
                                     tag_img.get_height() + int(2 * s))
                tag_bg.centerx = cx
                tag_bg.bottom = y + h - int(2 * s)
                pygame.draw.rect(surface, ext_tag, tag_bg, border_radius=2)
                tag_txt = tag_font.render(tag_text, True, (30, 30, 40))
                surface.blit(tag_txt, tag_txt.get_rect(center=tag_bg.center))
