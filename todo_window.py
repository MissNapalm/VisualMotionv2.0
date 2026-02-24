"""
To-Do List app with on-screen keyboard.
Pinch-tap to interact with buttons and type.
"""
import pygame
import theme_chrome as tc

# ── Colours ─────────────────────────────────────────────────────────
_BG = (30, 30, 50)
_HEADER = (45, 45, 70)
_WHITE = (255, 255, 255)
_GRAY = (160, 160, 180)
_LTGRAY = (80, 80, 100)
_GREEN = (60, 200, 100)
_RED = (220, 60, 60)
_BLUE = (70, 130, 230)
_YELLOW = (255, 200, 60)
_DARK = (25, 25, 40)
_KEY_BG = (55, 55, 80)
_KEY_PRESS = (90, 90, 120)
_INPUT_BG = (40, 40, 65)
_CHECK = (80, 220, 120)
_UNCHECK = (100, 100, 130)

# ── Keyboard layout ─────────────────────────────────────────────────
_ROWS = [
    list("QWERTYUIOP"),
    list("ASDFGHJKL"),
    list("ZXCVBNM"),
]
_SPECIAL_ROW = ["SPACE", "⌫", "DONE"]

# ── Font cache ──────────────────────────────────────────────────────
_fc: dict[int, pygame.font.Font] = {}


def _f(size: int) -> pygame.font.Font:
    size = max(10, size)
    if size not in _fc:
        _fc[size] = pygame.font.Font(None, size)
    return _fc[size]


# ── TodoWindow ──────────────────────────────────────────────────────

class TodoWindow:
    """Full-screen to-do list with on-screen keyboard."""

    def __init__(self, screen_w: int, screen_h: int):
        self.visible = False
        self._sw = screen_w
        self._sh = screen_h
        self.tasks = []           # list of {"text": str, "done": bool}
        self._keyboard_open = False
        self._input_text = ""
        self._edit_index = -1     # -1 = adding new, >= 0 = editing
        self._scroll_offset = 0
        self._key_rects = []      # [(rect, label), ...] rebuilt each frame
        self._task_hit_areas = [] # [(kind, idx, rect), ...] rebuilt each frame

    def open(self):
        self.visible = True
        self._keyboard_open = False
        self._input_text = ""
        self._edit_index = -1

    def close(self):
        self.visible = False
        self._keyboard_open = False

    def hit_test(self, px, py, gui_scale):
        r = self._rect(gui_scale)
        return r.collidepoint(int(px), int(py))

    def _rect(self, s):
        w = min(int(1200 * s), self._sw - 20)
        h = min(int(680 * s), self._sh - 20)
        return pygame.Rect((self._sw - w) // 2, (self._sh - h) // 2, w, h)

    # ────────────────────────────────────────────────────────────────
    def handle_tap(self, px, py, gui_scale):
        """Process a pinch-tap at screen coords (px, py). Returns True if consumed."""
        if not self.visible:
            return False
        s = gui_scale
        win = self._rect(s)
        if not win.collidepoint(int(px), int(py)):
            return False

        # Check keyboard keys first
        if self._keyboard_open:
            for rect, label in self._key_rects:
                if rect.collidepoint(int(px), int(py)):
                    self._on_key(label)
                    return True

        # Check + Add button
        add_btn = self._add_btn_rect(s, win)
        if add_btn and add_btn.collidepoint(int(px), int(py)):
            self._keyboard_open = True
            self._input_text = ""
            self._edit_index = -1
            return True

        # Check task rows (checkboxes, edit, delete)
        for info in self._task_hit_areas:
            kind, idx, rect = info
            if rect.collidepoint(int(px), int(py)):
                if kind == "check":
                    self.tasks[idx]["done"] = not self.tasks[idx]["done"]
                elif kind == "delete":
                    self.tasks.pop(idx)
                elif kind == "edit":
                    self._keyboard_open = True
                    self._input_text = self.tasks[idx]["text"]
                    self._edit_index = idx
                return True

        return True  # consumed but no button hit

    def _on_key(self, label):
        if label == "DONE":
            txt = self._input_text.strip()
            if txt:
                if self._edit_index >= 0 and self._edit_index < len(self.tasks):
                    self.tasks[self._edit_index]["text"] = txt
                else:
                    self.tasks.append({"text": txt, "done": False})
            self._keyboard_open = False
            self._input_text = ""
            self._edit_index = -1
        elif label == "⌫":
            self._input_text = self._input_text[:-1]
        elif label == "SPACE":
            self._input_text += " "
        else:
            self._input_text += label

    def _add_btn_rect(self, s, win):
        if self._keyboard_open:
            return None
        bw = max(200, int(360 * s))
        bh = max(60, int(88 * s))
        bx = win.x + (win.width - bw) // 2
        by = win.bottom - bh - int(14 * s)
        return pygame.Rect(bx, by, bw, bh)

    # ────────────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface, gui_scale: float = 1.0):
        if not self.visible:
            return
        s = gui_scale
        win = self._rect(s)
        ox, oy = win.x, win.y
        W, H = win.width, win.height

        prev_clip = surface.get_clip()
        surface.set_clip(win)

        p = tc.pal()  # None if classic

        # Background
        if p:
            tc.draw_window_frame(surface, win, s, p)
        else:
            pygame.draw.rect(surface, _BG, win)

        # Header bar
        hdr_h = max(40, int(56 * s))
        if p:
            tc.draw_header(surface, win, hdr_h, "TO-DO LIST", s, p)
        else:
            hdr = pygame.Rect(ox, oy, W, hdr_h)
            pygame.draw.rect(surface, _HEADER, hdr)
            title = _f(max(20, int(36 * s))).render("To-Do List", True, _WHITE)
            surface.blit(title, title.get_rect(midleft=(ox + int(20 * s), oy + hdr_h // 2)))

        # + Add button (only when keyboard closed)
        add_btn = self._add_btn_rect(s, win)
        if add_btn:
            if p:
                tc.draw_angular_button(surface, add_btn,
                                       "+ ADD TASK", s, p)
            else:
                pygame.draw.rect(surface, _GREEN, add_btn, border_radius=max(6, int(14 * s)))
                albl = _f(max(28, int(48 * s))).render("+ Add Task", True, _WHITE)
                surface.blit(albl, albl.get_rect(center=add_btn.center))

        # Task area
        self._task_hit_areas = []
        task_y = oy + hdr_h + int(8 * s)
        row_h = max(36, int(50 * s))
        pad = int(16 * s)

        # How much space for tasks
        if self._keyboard_open:
            kb_total_h = int(320 * s)
            input_h = max(36, int(48 * s))
            avail_h = H - hdr_h - int(8 * s) - kb_total_h - input_h - int(24 * s)
        else:
            add_reserve = max(60, int(88 * s)) + int(28 * s)  # button + gap
            avail_h = H - hdr_h - int(16 * s) - add_reserve
            # Close hint above the add button
            hint_c = p["text_lo"] if p else _GRAY
            hint = _f(max(14, int(22 * s))).render("double pinch to close", True, hint_c)
            surface.blit(hint, hint.get_rect(centerx=ox + W // 2, bottom=win.bottom - add_reserve + int(4 * s)))

        max_visible = max(1, int(avail_h / row_h))

        if len(self.tasks) == 0 and not self._keyboard_open:
            empty_c = p["text_lo"] if p else _GRAY
            empty = _f(max(16, int(30 * s))).render("No tasks yet — tap + Add Task", True, empty_c)
            surface.blit(empty, empty.get_rect(center=(ox + W // 2, task_y + avail_h // 2)))
        else:
            for i, task in enumerate(self.tasks):
                ry = task_y + i * row_h
                if ry + row_h > task_y + avail_h:
                    break

                # Row background
                row_rect = pygame.Rect(ox + pad, ry, W - pad * 2, row_h - int(4 * s))
                if p:
                    row_bg_s = pygame.Surface((row_rect.width, row_rect.height), pygame.SRCALPHA)
                    row_bg_s.fill((*p["stripe"][:3], 50))
                    surface.blit(row_bg_s, row_rect.topleft)
                    # Left accent bar
                    accent_c = p["bright"] if task["done"] else p["dim"]
                    pygame.draw.rect(surface, accent_c,
                                     (row_rect.x, ry, max(2, int(3 * s)), row_h - int(4 * s)))
                else:
                    pygame.draw.rect(surface, _DARK, row_rect, border_radius=max(4, int(8 * s)))

                # Checkbox
                cb_size = max(16, int(26 * s))
                cb_x = ox + pad + int(12 * s)
                cb_y = ry + (row_h - cb_size) // 2
                cb_rect = pygame.Rect(cb_x, cb_y, cb_size, cb_size)
                if p:
                    cut = max(3, int(5 * s))
                    cb_pts = [(cb_rect.x, cb_rect.y),
                              (cb_rect.right - cut, cb_rect.y),
                              (cb_rect.right, cb_rect.y + cut),
                              (cb_rect.right, cb_rect.bottom),
                              (cb_rect.x + cut, cb_rect.bottom),
                              (cb_rect.x, cb_rect.bottom - cut)]
                    if task["done"]:
                        pygame.draw.polygon(surface, p["bright"], cb_pts)
                        ck = _f(max(12, int(22 * s))).render("OK", True, p["panel"])
                        surface.blit(ck, ck.get_rect(center=cb_rect.center))
                    else:
                        pygame.draw.polygon(surface, p["dim"], cb_pts, max(1, int(2 * s)))
                else:
                    if task["done"]:
                        pygame.draw.rect(surface, _CHECK, cb_rect, border_radius=max(2, int(5 * s)))
                        ck = _f(max(12, int(22 * s))).render("✓", True, _WHITE)
                        surface.blit(ck, ck.get_rect(center=cb_rect.center))
                    else:
                        pygame.draw.rect(surface, _UNCHECK, cb_rect, border_radius=max(2, int(5 * s)))
                self._task_hit_areas.append(("check", i, cb_rect.inflate(int(10*s), int(10*s))))

                # Task text
                if p:
                    txt_color = p["text_lo"] if task["done"] else p["text_hi"]
                else:
                    txt_color = _GRAY if task["done"] else _WHITE
                txt_font = _f(max(14, int(26 * s)))
                display_text = task["text"]
                if task["done"]:
                    display_text = "  " + task["text"]
                tlbl = txt_font.render(display_text, True, txt_color)
                tx = cb_x + cb_size + int(14 * s)
                surface.blit(tlbl, tlbl.get_rect(midleft=(tx, ry + row_h // 2)))

                # Edit button
                ebw = max(36, int(56 * s))
                ebh = max(22, int(32 * s))
                ex = row_rect.right - ebw * 2 - int(20 * s)
                ey = ry + (row_h - ebh) // 2
                edit_rect = pygame.Rect(ex, ey, ebw, ebh)
                if p:
                    tc.draw_angular_button(surface, edit_rect, "EDIT", s, p)
                else:
                    pygame.draw.rect(surface, _BLUE, edit_rect, border_radius=max(3, int(6 * s)))
                    elbl = _f(max(12, int(20 * s))).render("Edit", True, _WHITE)
                    surface.blit(elbl, elbl.get_rect(center=edit_rect.center))
                self._task_hit_areas.append(("edit", i, edit_rect))

                # Delete button
                dx = row_rect.right - ebw - int(8 * s)
                del_rect = pygame.Rect(dx, ey, ebw, ebh)
                if p:
                    tc.draw_angular_button(surface, del_rect, "DEL", s, p, danger=True)
                else:
                    pygame.draw.rect(surface, _RED, del_rect, border_radius=max(3, int(6 * s)))
                    dlbl = _f(max(12, int(20 * s))).render("Del", True, _WHITE)
                    surface.blit(dlbl, dlbl.get_rect(center=del_rect.center))
                self._task_hit_areas.append(("delete", i, del_rect))

        # ── Keyboard section ──
        self._key_rects = []
        if self._keyboard_open:
            kb_y = win.bottom - int(320 * s)

            # Input field
            input_h = max(36, int(48 * s))
            inp_rect = pygame.Rect(ox + pad, kb_y - input_h - int(8 * s), W - pad * 2, input_h)
            if p:
                inp_cut = max(4, int(8 * s))
                inp_pts = [
                    (inp_rect.x, inp_rect.y),
                    (inp_rect.right - inp_cut, inp_rect.y),
                    (inp_rect.right, inp_rect.y + inp_cut),
                    (inp_rect.right, inp_rect.bottom),
                    (inp_rect.x + inp_cut, inp_rect.bottom),
                    (inp_rect.x, inp_rect.bottom - inp_cut),
                ]
                pygame.draw.polygon(surface, p["panel"], inp_pts)
                pygame.draw.polygon(surface, p["bright"], inp_pts, max(1, int(2 * s)))
            else:
                pygame.draw.rect(surface, _INPUT_BG, inp_rect, border_radius=max(4, int(8 * s)))
                pygame.draw.rect(surface, _BLUE, inp_rect, width=2, border_radius=max(4, int(8 * s)))

            # Cursor blink
            cursor = "|" if (pygame.time.get_ticks() // 500) % 2 == 0 else ""
            inp_font = _f(max(16, int(28 * s)))
            inp_c = p["text_hi"] if p else _WHITE
            inp_lbl = inp_font.render(self._input_text + cursor, True, inp_c)
            surface.blit(inp_lbl, inp_lbl.get_rect(midleft=(inp_rect.x + int(12 * s), inp_rect.centery)))

            # Editing indicator
            if self._edit_index >= 0:
                ei_c = p["text_md"] if p else _YELLOW
                edit_hint = _f(max(12, int(20 * s))).render("Editing task...", True, ei_c)
                surface.blit(edit_hint, edit_hint.get_rect(midright=(inp_rect.right - int(12 * s), inp_rect.centery)))

            # Keyboard background
            kb_rect = pygame.Rect(ox, kb_y, W, win.bottom - kb_y)
            kb_bg_c = p["header"] if p else (35, 35, 55)
            pygame.draw.rect(surface, kb_bg_c, kb_rect)
            if p:
                # Accent line above keyboard
                pygame.draw.line(surface, p["dim"], (ox, kb_y), (ox + W, kb_y), 1)

            # Draw key rows
            key_h = max(38, int(56 * s))
            key_gap = max(3, int(5 * s))
            row_gap = max(3, int(7 * s))

            cur_y = kb_y + int(6 * s)
            for row_idx, row in enumerate(_ROWS):
                num_keys = len(row)
                total_gap = key_gap * (num_keys - 1)
                key_w = (W - pad * 2 - total_gap) // num_keys
                row_width = key_w * num_keys + total_gap
                start_x = ox + (W - row_width) // 2

                for k_idx, ch in enumerate(row):
                    kx = start_x + k_idx * (key_w + key_gap)
                    kr = pygame.Rect(kx, cur_y, key_w, key_h)
                    if p:
                        kcut = max(3, int(5 * s))
                        kpts = [(kr.x, kr.y), (kr.right - kcut, kr.y),
                                (kr.right, kr.y + kcut), (kr.right, kr.bottom),
                                (kr.x + kcut, kr.bottom), (kr.x, kr.bottom - kcut)]
                        pygame.draw.polygon(surface, p["btn_bg"], kpts)
                        pygame.draw.polygon(surface, p["dim"], kpts, 1)
                        klbl = _f(max(18, int(32 * s))).render(ch, True, p["text_hi"])
                    else:
                        pygame.draw.rect(surface, _KEY_BG, kr, border_radius=max(3, int(6 * s)))
                        klbl = _f(max(18, int(32 * s))).render(ch, True, _WHITE)
                    surface.blit(klbl, klbl.get_rect(center=kr.center))
                    self._key_rects.append((kr, ch))

                cur_y += key_h + row_gap

            # Special row: SPACE, BACKSPACE, DONE
            spec_labels = _SPECIAL_ROW
            spec_colors_classic = [_KEY_BG, _RED, _GREEN]
            spec_widths = [0.55, 0.2, 0.2]
            total_spec_gap = key_gap * (len(spec_labels) - 1)
            usable_w = W - pad * 2 - total_spec_gap
            sx = ox + pad
            for si, (slbl, sw_frac) in enumerate(zip(spec_labels, spec_widths)):
                skw = int(usable_w * sw_frac)
                sr = pygame.Rect(sx, cur_y, skw, key_h)
                if p:
                    is_danger = (slbl == "⌫")
                    tc.draw_angular_button(surface, sr, slbl, s, p, danger=is_danger)
                else:
                    scol = spec_colors_classic[si]
                    pygame.draw.rect(surface, scol, sr, border_radius=max(3, int(6 * s)))
                    stxt = _f(max(18, int(30 * s))).render(slbl, True, _WHITE)
                    surface.blit(stxt, stxt.get_rect(center=sr.center))
                self._key_rects.append((sr, slbl))
                sx += skw + key_gap

        # Restore clip, draw border
        surface.set_clip(prev_clip)
        if not p:
            pygame.draw.rect(surface, _WHITE, win, width=3, border_radius=max(8, int(22 * s)))
