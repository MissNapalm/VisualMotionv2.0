"""
Desert Sands — gesture-controlled falling sand / fluid simulation.
NumPy-accelerated grid for performance.
"""
import math
import random
import time
import pygame
import numpy as np

_CELL = 5
_FPS_SIM = 55

_BLACK = (0, 0, 0)
_PALE_YELLOW = (255, 255, 153)
_WALL_COLOR = (160, 32, 240)
_WHITE = (255, 255, 255)
_BTN_BG = (40, 40, 55)
_BTN_ACTIVE = (80, 255, 180)

EMPTY = 0
STATIC = 1
HEAVY = 2
FIRE = 3

_FUN_COLORS = [
    (255, 69, 0), (255, 105, 180), (255, 255, 0),
    (0, 255, 255), (124, 252, 0), (255, 165, 0), (0, 128, 255),
    (255, 255, 153),
]

_GNOME_COLORS = [
    (255, 100, 100), (100, 255, 100), (100, 100, 255),
    (255, 255, 100), (255, 100, 255), (100, 255, 255),
    (255, 180, 60), (200, 120, 255),
]

_FIRE_COLORS = [
    (255, 100, 0), (255, 140, 0), (255, 165, 0),
    (255, 69, 0), (255, 200, 50), (255, 120, 20),
]


class _Gnome:
    """A tiny stick figure that falls with gravity, lands on surfaces, and walks."""

    def __init__(self, gx, gy):
        self.gx = float(gx)
        self.gy = float(gy)
        self.vy = 0.0                   # vertical velocity (grid cells/step)
        self.dir = 1 if random.random() < 0.5 else -1   # walking direction
        self.grounded = False
        self.walk_timer = 0
        self.color = random.choice(_GNOME_COLORS)
        self.alive = True
        self.on_fire = False
        self.fire_start_time = 0.0

    def _can_walk(self, ix, iy, direction, grid):
        """Check if we can walk one step in the given direction.
        Returns (new_gx, new_gy) or None."""
        h, w = grid.shape
        next_x = ix + direction
        if next_x < 0 or next_x >= w:
            return None  # edge of world
        if grid[iy, next_x] == EMPTY or grid[iy, next_x] == FIRE:
            return (float(next_x), float(iy))
        else:
            # Blocked — try climbing 1 cell
            climb_y = iy - 1
            if climb_y >= 0 and (grid[climb_y, next_x] == EMPTY or grid[climb_y, next_x] == FIRE):
                return (float(next_x), float(climb_y))
            else:
                return None  # can't climb

    def step(self, grid):
        h, w = grid.shape
        ix, iy = int(self.gx), int(self.gy)

        # Off-screen check
        if ix < 0 or ix >= w or iy >= h:
            self.alive = False
            return

        # Check if standing in fire
        if 0 <= ix < w and 0 <= iy < h and grid[iy, ix] == FIRE:
            if not self.on_fire:
                self.on_fire = True
                self.fire_start_time = time.time()

        # Die after 7 seconds on fire
        if self.on_fire and (time.time() - self.fire_start_time) > 7.0:
            self.alive = False
            return

        # Walk speed: every 3 ticks normally, every 1 tick on fire
        walk_interval = 1 if self.on_fire else 3

        # --- gravity ---
        below_y = iy + 1
        on_ground = False
        if below_y >= h:
            on_ground = True          # bottom of screen
        elif grid[below_y, ix] != EMPTY and grid[below_y, ix] != FIRE:
            on_ground = True          # standing on wall or sand

        if on_ground:
            self.vy = 0.0
            self.grounded = True
            self.gy = float(iy)

            # --- walking ---
            self.walk_timer += 1
            if self.walk_timer >= walk_interval:
                self.walk_timer = 0

                # Try current direction
                result = self._can_walk(ix, iy, self.dir, grid)
                if result:
                    self.gx, self.gy = result
                else:
                    # Can't go forward — reverse immediately
                    self.dir *= -1
                    # Try the other direction right away
                    result2 = self._can_walk(ix, iy, self.dir, grid)
                    if result2:
                        self.gx, self.gy = result2
                    # else: stuck on both sides, just stand still
        else:
            # Falling
            self.grounded = False
            self.vy = min(self.vy + 0.4, 3.0)   # gravity acceleration, terminal vel
            new_y = self.gy + self.vy
            # Check each cell we'd pass through
            target_y = int(new_y)
            for check_y in range(iy + 1, min(target_y + 1, h)):
                if grid[check_y, ix] != EMPTY:
                    # Land on top of this cell
                    self.gy = float(check_y - 1)
                    self.vy = 0.0
                    self.grounded = True
                    return
            if target_y >= h:
                self.alive = False
                return
            self.gy = new_y


class _SandState:
    """NumPy grid-based sand sim. Much faster than dict."""

    def __init__(self, w, h):
        self.width = w
        self.height = h
        # 0 = empty, 1 = static wall, 2 = heavy/sand
        self.grid = np.zeros((h, w), dtype=np.uint8)
        # RGB color per cell
        self.colors = np.zeros((h, w, 3), dtype=np.uint8)

    def add(self, ptype, x, y, color):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.grid[y, x] = ptype
            self.colors[y, x] = color

    def erase_circle(self, cx, cy, radius):
        ys, xs = np.ogrid[max(0, cy - radius):min(self.height, cy + radius + 1),
                          max(0, cx - radius):min(self.width, cx + radius + 1)]
        mask = (xs - cx) ** 2 + (ys - cy) ** 2 <= radius * radius
        y_off = max(0, cy - radius)
        x_off = max(0, cx - radius)
        self.grid[y_off:y_off + mask.shape[0], x_off:x_off + mask.shape[1]][mask] = EMPTY

    def clear_all(self):
        self.grid[:] = 0
        self.colors[:] = 0

    def count(self):
        return int(np.count_nonzero(self.grid))


def _step(state, wind_active=False, wind_dir=1, reverse_gravity=False):
    """Vectorized physics step using numpy."""
    g = state.grid
    c = state.colors
    h, w = g.shape

    # Find all heavy (sand) particles
    sand = (g == HEAVY)
    if not np.any(sand):
        return

    ys, xs = np.where(sand)

    # Shuffle order to avoid directional bias
    order = np.arange(len(ys))
    np.random.shuffle(order)
    ys = ys[order]
    xs = xs[order]

    grav = -1 if reverse_gravity else 1

    for i in range(len(ys)):
        y, x = int(ys[i]), int(xs[i])
        if g[y, x] != HEAVY:
            continue  # already moved by another particle this step
        col = c[y, x].copy()

        ny = y + grav
        moved = False

        # Try straight down
        if 0 <= ny < h and g[ny, x] == EMPTY:
            g[y, x] = EMPTY
            g[ny, x] = HEAVY
            c[ny, x] = col
            y = ny
            moved = True
        else:
            # Try diagonal left/right (random order)
            if random.random() < 0.5:
                tries = [(x - 1, ny), (x + 1, ny)]
            else:
                tries = [(x + 1, ny), (x - 1, ny)]
            for tx, ty in tries:
                if 0 <= tx < w and 0 <= ty < h and g[ty, tx] == EMPTY:
                    g[y, x] = EMPTY
                    g[ty, tx] = HEAVY
                    c[ty, tx] = col
                    x, y = tx, ty
                    moved = True
                    break

        # If didn't fall, try lateral slide
        if not moved:
            if random.random() < 0.3:
                lx = x + (1 if random.random() < 0.5 else -1)
                if 0 <= lx < w and g[y, lx] == EMPTY:
                    g[y, x] = EMPTY
                    g[y, lx] = HEAVY
                    c[y, lx] = col
                    x = lx
                    moved = True

        # Wind push
        if wind_active and moved:
            wx = x + wind_dir
            if 0 <= wx < w and g[y, wx] == EMPTY:
                g[y, x] = EMPTY
                g[y, wx] = HEAVY
                c[y, wx] = col


def _step_fire(state):
    """Physics step for fire particles: rise upward, spread, consume."""
    g = state.grid
    c = state.colors
    h, w = g.shape

    fire = (g == FIRE)
    if not np.any(fire):
        return

    ys, xs = np.where(fire)
    order = np.arange(len(ys))
    np.random.shuffle(order)
    ys = ys[order]
    xs = xs[order]

    for i in range(len(ys)):
        y, x = int(ys[i]), int(xs[i])
        if g[y, x] != FIRE:
            continue
        col = tuple(random.choice(_FIRE_COLORS))

        # Consume neighbors — turn adjacent HEAVY or STATIC into FIRE
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
            nx, ny2 = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny2 < h:
                if g[ny2, nx] == HEAVY or g[ny2, nx] == STATIC:
                    if random.random() < 0.08:
                        g[ny2, nx] = FIRE
                        c[ny2, nx] = random.choice(_FIRE_COLORS)

        # Fire rises upward (opposite of sand)
        ny = y - 1
        moved = False

        if 0 <= ny < h and g[ny, x] == EMPTY:
            g[y, x] = EMPTY
            g[ny, x] = FIRE
            c[ny, x] = col
            y = ny
            moved = True
        else:
            # Try diagonal up-left/up-right
            if random.random() < 0.5:
                tries = [(x - 1, ny), (x + 1, ny)]
            else:
                tries = [(x + 1, ny), (x - 1, ny)]
            for tx, ty in tries:
                if 0 <= tx < w and 0 <= ty < h and g[ty, tx] == EMPTY:
                    g[y, x] = EMPTY
                    g[ty, tx] = FIRE
                    c[ty, tx] = col
                    x, y = tx, ty
                    moved = True
                    break

        # Random lateral drift
        if not moved:
            if random.random() < 0.4:
                lx = x + (1 if random.random() < 0.5 else -1)
                if 0 <= lx < w and g[y, lx] == EMPTY:
                    g[y, x] = EMPTY
                    g[y, lx] = FIRE
                    c[y, lx] = col
                    moved = True

        # Fire has a chance to die out
        if random.random() < 0.005:
            g[y, x] = EMPTY


def _bresenham(x0, y0, x1, y1):
    points = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
    return points


class _Button:
    def __init__(self, x, y, w, h, label, color=_BTN_BG, active_color=_BTN_ACTIVE, font_size=30):
        self.rect = pygame.Rect(x, y, w, h)
        self.label = label
        self.color = color
        self.active_color = active_color
        self.active = False
        self.font_size = font_size
        self.swatch_color = None

    def draw(self, surface, font=None):
        c = self.active_color if self.active else self.color
        pygame.draw.rect(surface, c, self.rect, border_radius=12)
        pygame.draw.rect(surface, (100, 100, 120), self.rect, 2, border_radius=12)
        f = font or pygame.font.Font(None, self.font_size)
        tc = _WHITE if not self.active else _BLACK
        txt = f.render(self.label, True, tc)
        tr = txt.get_rect(center=self.rect.center)
        if self.swatch_color:
            tr.centerx = self.rect.centerx - 14
        surface.blit(txt, tr)
        if self.swatch_color:
            sw = pygame.Rect(tr.right + 8, self.rect.centery - 12, 24, 24)
            pygame.draw.rect(surface, self.swatch_color, sw, border_radius=5)
            pygame.draw.rect(surface, _WHITE, sw, 1, border_radius=5)

    def hit(self, px, py):
        # Inflated hit area (10px padding) for easier gesture targeting
        expanded = self.rect.inflate(20, 20)
        return expanded.collidepoint(int(px), int(py))


class SandWindow:
    MODE_POUR = 0
    MODE_WALL = 1
    MODE_ERASE = 2
    MODE_GNOME = 3
    MODE_FIRE = 4

    def __init__(self, window_width, window_height):
        self.visible = False
        self._ww = window_width
        self._wh = window_height
        self._gw = window_width // _CELL
        self._gh = window_height // _CELL
        self._state = _SandState(self._gw, self._gh)
        self._mode = self.MODE_POUR
        self._color = _PALE_YELLOW
        self._color_idx = 7
        self._wind_active = False
        self._wind_dir = 1
        self._reverse_gravity = False
        self._sim_accum = 0.0
        self._last_tick = 0.0
        self._last_wall_gx = None
        self._last_wall_gy = None
        self._gnomes = []
        self._gnome_spawned_this_pinch = False
        self._pixel_surf = pygame.Surface((self._gw, self._gh), pygame.SRCALPHA)
        self._buttons = []
        self._build_buttons()

    def _build_buttons(self):
        bw = 160
        bh = 70
        margin = 10
        row2_y = self._wh - bh - margin
        row1_y = row2_y - bh - margin

        x = margin
        self._btn_pour = _Button(x, row1_y, bw, bh, "SAND", font_size=34); x += bw + margin
        self._btn_wall = _Button(x, row1_y, bw, bh, "WALL", font_size=34); x += bw + margin
        self._btn_erase = _Button(x, row1_y, bw, bh, "ERASE", font_size=34); x += bw + margin
        self._btn_color = _Button(x, row1_y, bw + 30, bh, "COLOR", font_size=34); x += bw + 30 + margin
        self._btn_gnome = _Button(x, row1_y, bw, bh, "GNOME", font_size=34); x += bw + margin
        self._btn_fire = _Button(x, row1_y, bw, bh, "FIRE", font_size=34); x += bw + margin

        x = margin
        self._btn_wind = _Button(x, row2_y, bw, bh, "WIND", font_size=34); x += bw + margin
        self._btn_wind_dir = _Button(x, row2_y, bw, bh, "WIND >", font_size=34); x += bw + margin
        self._btn_gravity = _Button(x, row2_y, bw, bh, "GRAVITY", font_size=34); x += bw + margin
        self._btn_clear = _Button(x, row2_y, bw, bh, "CLEAR", font_size=34); x += bw + margin

        quit_h = bh * 2 + margin
        self._btn_quit = _Button(self._ww - bw - margin, row1_y, bw, quit_h, "QUIT",
                                 color=(120, 30, 30), active_color=(255, 60, 60), font_size=38)

        self._buttons = [
            self._btn_pour, self._btn_wall, self._btn_erase, self._btn_color,
            self._btn_gnome, self._btn_fire,
            self._btn_wind, self._btn_wind_dir, self._btn_gravity, self._btn_clear,
            self._btn_quit,
        ]

    def open(self):
        self.visible = True
        self._state = _SandState(self._gw, self._gh)
        self._mode = self.MODE_POUR
        self._color = _PALE_YELLOW
        self._color_idx = 7
        self._wind_active = False
        self._wind_dir = 1
        self._reverse_gravity = False
        self._sim_accum = 0.0
        self._last_tick = time.time()
        self._last_wall_gx = None
        self._last_wall_gy = None
        self._gnomes = []
        self._gnome_spawned_this_pinch = False
        self._update_button_states()

    def close(self):
        self.visible = False

    def random_color(self):
        self._color_idx = (self._color_idx + 1) % len(_FUN_COLORS)
        self._color = _FUN_COLORS[self._color_idx]

    def _update_button_states(self):
        self._btn_pour.active = (self._mode == self.MODE_POUR)
        self._btn_wall.active = (self._mode == self.MODE_WALL)
        self._btn_erase.active = (self._mode == self.MODE_ERASE)
        self._btn_gnome.active = (self._mode == self.MODE_GNOME)
        self._btn_fire.active = (self._mode == self.MODE_FIRE)
        self._btn_wind.active = self._wind_active
        self._btn_gravity.active = self._reverse_gravity
        self._btn_wind.label = "WIND ON" if self._wind_active else "WIND"
        self._btn_wind_dir.label = "< WIND" if self._wind_dir == -1 else "WIND >"
        self._btn_gravity.label = "GRAV UP" if self._reverse_gravity else "GRAVITY"
        self._btn_color.swatch_color = self._color

    def _in_ui_zone(self, px, py):
        for btn in self._buttons:
            if btn.hit(px, py):
                return True
        return False

    def handle_tap(self, px, py):
        if self._btn_quit.hit(px, py):
            self.close()
            print("Closed Sand (quit button)")
            return
        if self._btn_pour.hit(px, py):
            self._mode = self.MODE_POUR
            self._update_button_states(); return
        if self._btn_wall.hit(px, py):
            self._mode = self.MODE_WALL
            self._update_button_states(); return
        if self._btn_erase.hit(px, py):
            self._mode = self.MODE_ERASE
            self._update_button_states(); return
        if self._btn_gnome.hit(px, py):
            self._mode = self.MODE_GNOME
            self._update_button_states(); return
        if self._btn_fire.hit(px, py):
            self._mode = self.MODE_FIRE
            self._update_button_states(); return
        if self._btn_color.hit(px, py):
            self.random_color()
            self._update_button_states(); return
        if self._btn_wind.hit(px, py):
            self._wind_active = not self._wind_active
            self._update_button_states(); return
        if self._btn_wind_dir.hit(px, py):
            self._wind_dir *= -1
            self._update_button_states(); return
        if self._btn_gravity.hit(px, py):
            self._reverse_gravity = not self._reverse_gravity
            self._update_button_states(); return
        if self._btn_clear.hit(px, py):
            self._state.clear_all()
            self._gnomes = []
            return
        if not self._in_ui_zone(px, py):
            gx, gy = int(px) // _CELL, int(py) // _CELL
            if self._mode == self.MODE_POUR:
                for _ in range(25):
                    rx = gx + random.randint(-5, 5)
                    ry = gy + random.randint(-5, 2)
                    self._state.add(HEAVY, rx, ry, self._color)
            elif self._mode == self.MODE_WALL:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        self._state.add(STATIC, gx + dx, gy + dy, _WALL_COLOR)
            elif self._mode == self.MODE_GNOME:
                self._gnomes.append(_Gnome(gx, gy))
            elif self._mode == self.MODE_FIRE:
                for _ in range(15):
                    rx = gx + random.randint(-3, 3)
                    ry = gy + random.randint(-2, 2)
                    self._state.add(FIRE, rx, ry, random.choice(_FIRE_COLORS))

    def handle_pinch(self, px, py):
        if self._in_ui_zone(px, py):
            self._last_wall_gx = None
            self._last_wall_gy = None
            return
        gx, gy = int(px) // _CELL, int(py) // _CELL
        if self._mode == self.MODE_POUR:
            for _ in range(10):
                rx = gx + random.randint(-3, 3)
                ry = gy + random.randint(-2, 1)
                self._state.add(HEAVY, rx, ry, self._color)
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_WALL:
            # Draw at current position; connect with short bresenham only if
            # the previous point is close (within 8 cells) to avoid long jumps
            if (self._last_wall_gx is not None and self._last_wall_gy is not None
                    and abs(gx - self._last_wall_gx) <= 8
                    and abs(gy - self._last_wall_gy) <= 8):
                line_pts = _bresenham(self._last_wall_gx, self._last_wall_gy, gx, gy)
                for lx, ly in line_pts:
                    for dx in range(-1, 2):
                        for dy in range(-1, 2):
                            self._state.add(STATIC, lx + dx, ly + dy, _WALL_COLOR)
            else:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        self._state.add(STATIC, gx + dx, gy + dy, _WALL_COLOR)
            self._last_wall_gx = gx
            self._last_wall_gy = gy
        elif self._mode == self.MODE_ERASE:
            self._state.erase_circle(gx, gy, 6)
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_GNOME:
            # Don't spawn continuously while pinching — only on first frame
            if not getattr(self, '_gnome_spawned_this_pinch', False):
                self._gnomes.append(_Gnome(gx, gy))
                self._gnome_spawned_this_pinch = True
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_FIRE:
            for _ in range(8):
                rx = gx + random.randint(-2, 2)
                ry = gy + random.randint(-2, 2)
                self._state.add(FIRE, rx, ry, random.choice(_FIRE_COLORS))
            self._last_wall_gx = None
            self._last_wall_gy = None

    def handle_pinch_end(self):
        self._gnome_spawned_this_pinch = False
        self._last_wall_gx = None
        self._last_wall_gy = None

    def draw(self, surface, gui_scale):
        now = time.time()
        dt = now - self._last_tick if self._last_tick else 0.016
        self._last_tick = now

        self._sim_accum += dt
        step_dt = 1.0 / _FPS_SIM
        steps = 0
        while self._sim_accum >= step_dt and steps < 5:
            _step(self._state, self._wind_active, self._wind_dir, self._reverse_gravity)
            _step_fire(self._state)
            # Step all gnomes
            for gnome in self._gnomes:
                gnome.step(self._state.grid)
            self._gnomes = [g for g in self._gnomes if g.alive]
            self._sim_accum -= step_dt
            steps += 1

        surface.fill(_BLACK)

        # Fast pixel rendering — build a surface from the color array directly
        st = self._state
        # Create an RGB array at grid resolution, then scale up
        rgb = st.colors.copy()
        # Black out empty cells
        empty_mask = (st.grid == EMPTY)
        rgb[empty_mask] = 0

        # Transpose to (width, height, 3) for pygame surfarray
        surf_small = pygame.surfarray.make_surface(rgb.transpose(1, 0, 2))
        scaled = pygame.transform.scale(surf_small, (self._ww, self._wh))
        surface.blit(scaled, (0, 0))

        # Draw gnomes as stick figures (2× size)
        for gnome in self._gnomes:
            sx = int(gnome.gx * _CELL + _CELL // 2)
            sy = int(gnome.gy * _CELL + _CELL // 2)
            c = gnome.color
            # If on fire, flicker between orange/red
            if gnome.on_fire:
                c = random.choice([(255, 80, 0), (255, 0, 0), (255, 180, 0)])
            # Head
            pygame.draw.circle(surface, c, (sx, sy - 16), 8)
            # Body
            pygame.draw.line(surface, c, (sx, sy - 8), (sx, sy + 12), 3)
            # Arms
            arm_wave = 4 if gnome.grounded and gnome.walk_timer == 0 else 0
            if gnome.on_fire:
                arm_wave = random.randint(-6, 6)  # frantic arm waving
            pygame.draw.line(surface, c, (sx - 10, sy + arm_wave), (sx + 10, sy - arm_wave), 3)
            # Legs — animate walking
            if gnome.grounded:
                leg_off = 8 if gnome.walk_timer == 0 else 4
                pygame.draw.line(surface, c, (sx, sy + 12), (sx - leg_off, sy + 24), 3)
                pygame.draw.line(surface, c, (sx, sy + 12), (sx + leg_off, sy + 24), 3)
            else:
                # Falling — legs together
                pygame.draw.line(surface, c, (sx, sy + 12), (sx - 4, sy + 24), 3)
                pygame.draw.line(surface, c, (sx, sy + 12), (sx + 4, sy + 24), 3)
            # Direction indicator — eye dot
            eye_x = sx + (4 * gnome.dir)
            pygame.draw.circle(surface, (255, 255, 255), (eye_x, sy - 18), 2)
            # Fire particles around burning gnome
            if gnome.on_fire:
                for _ in range(3):
                    fx = sx + random.randint(-8, 8)
                    fy = sy + random.randint(-20, 10)
                    pygame.draw.circle(surface, random.choice(_FIRE_COLORS), (fx, fy), random.randint(2, 4))

        # Draw buttons
        self._update_button_states()
        for btn in self._buttons:
            btn.draw(surface)

        # Particle count
        small = pygame.font.Font(None, 24)
        count = st.count()
        n_gnomes = len(self._gnomes)
        info = f"{count} particles"
        if n_gnomes:
            info += f"  |  {n_gnomes} gnomes"
        ct = small.render(info, True, (70, 70, 70))
        surface.blit(ct, (self._ww - 140, 16))

        # Title
        title = pygame.font.Font(None, 36).render("DESERT SANDS", True, (255, 200, 100))
        surface.blit(title, (self._ww // 2 - 80, 16))
