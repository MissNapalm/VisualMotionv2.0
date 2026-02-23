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
_FPS_SIM = 36
_PERF_CAP = 12000     # above this many active particles, process a random subset

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
WOOD = 4
CONCRETE = 5
GUNPOWDER = 6
NAPALM = 7
GASOLINE = 8
WATER = 9
CONFETTI = 10
POISON = 11
HOLYWATER = 12

_WOOD_COLOR = (139, 90, 43)
_WOOD_COLORS = [(139, 90, 43), (120, 75, 35), (160, 105, 50), (110, 70, 30)]
_CONCRETE_COLOR = (140, 140, 145)
_GUNPOWDER_COLORS = [(80, 80, 80), (60, 60, 60), (40, 40, 40), (100, 100, 100), (30, 30, 30)]
_NAPALM_COLORS = [(255, 60, 0), (255, 100, 0), (255, 40, 20), (200, 50, 0), (255, 120, 30)]
_GASOLINE_COLORS = [(180, 200, 50), (160, 180, 40), (200, 210, 60), (140, 170, 30), (190, 190, 55)]
_WATER_COLORS = [(30, 100, 220), (40, 120, 240), (20, 80, 200), (50, 130, 255), (35, 110, 230)]
_POISON_COLORS = [(50, 180, 20), (30, 160, 10), (70, 200, 30), (40, 140, 15), (60, 190, 25)]
_HOLYWATER_COLORS = [(200, 200, 255), (180, 180, 255), (220, 220, 255), (160, 180, 255), (210, 210, 240)]

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

_HAT_COLORS = [
    (200, 0, 0), (0, 160, 0), (0, 0, 200),
    (180, 120, 0), (160, 0, 160), (0, 140, 140),
    (220, 60, 0), (100, 60, 180),
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
        self.hat_color = random.choice(_HAT_COLORS)
        self.alive = True
        self.on_fire = False
        self.fire_start_time = 0.0
        self.held = False               # being carried by HAND mode
        self.fall_start = 0.0           # when falling started
        self.has_parachute = True        # parachute available
        self.parachute_open = False      # currently deployed
        # Celebration state
        self.celebrating = False
        self.celebrate_start = 0.0      # time.time() when celebration began
        # Zombie state
        self.is_zombie = False
        self.zombie_target = None       # gnome we're chasing
        self.frozen = False             # freeze on contact
        self.freeze_start = 0.0         # time.time() when freeze began

    def _can_walk(self, ix, iy, direction, grid):
        """Check if we can walk one step in the given direction.
        Returns (new_gx, new_gy) or None."""
        _passable = (EMPTY, FIRE, NAPALM, WATER, POISON, HOLYWATER)
        h, w = grid.shape
        next_x = ix + direction
        if next_x < 0 or next_x >= w:
            return None  # edge of world
        if grid[iy, next_x] in _passable:
            return (float(next_x), float(iy))
        else:
            # Blocked — try climbing 1 cell
            climb_y = iy - 1
            if climb_y >= 0 and grid[climb_y, next_x] in _passable:
                return (float(next_x), float(climb_y))
            else:
                return None  # can't climb

    def step(self, grid):
        if self.held:
            return  # being carried, skip physics
        h, w = grid.shape
        ix, iy = int(self.gx), int(self.gy)

        # Off-screen check
        if ix < 0 or ix >= w or iy >= h:
            self.alive = False
            return

        # --- Frozen (zombie bite freeze) ---
        if self.frozen:
            if time.time() - self.freeze_start >= 1.0:
                self.frozen = False
            else:
                return  # can't move while frozen

        # Check if standing in or near fire (2-cell radius)
        if not self.on_fire:
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    cx, cy = ix + dx, iy + dy
                    if 0 <= cx < w and 0 <= cy < h and grid[cy, cx] in (FIRE, NAPALM):
                        self.on_fire = True
                        self.fire_start_time = time.time()
                        break
                if self.on_fire:
                    break

        # Check if touching poison — turns into zombie
        if not self.is_zombie and not self.on_fire:
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    cx, cy = ix + dx, iy + dy
                    if 0 <= cx < w and 0 <= cy < h and grid[cy, cx] == POISON:
                        self.is_zombie = True
                        self.color = (30, 160, 30)
                        self.hat_color = (20, 100, 20)
                        self.has_parachute = False
                        self.parachute_open = False
                        self.celebrating = False
                        break
                if self.is_zombie:
                    break

        # Check if zombie touching holy water — cured!
        if self.is_zombie:
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    cx, cy = ix + dx, iy + dy
                    if 0 <= cx < w and 0 <= cy < h and grid[cy, cx] == HOLYWATER:
                        self.is_zombie = False
                        self.color = random.choice(_GNOME_COLORS)
                        self.hat_color = random.choice(_HAT_COLORS)
                        self.has_parachute = True
                        break
                if not self.is_zombie:
                    break

        # Check if touching confetti — triggers celebration hop
        if not self.celebrating and not self.on_fire and not self.is_zombie:
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    cx, cy = ix + dx, iy + dy
                    if 0 <= cx < w and 0 <= cy < h and grid[cy, cx] == CONFETTI:
                        self.celebrating = True
                        self.celebrate_start = time.time()
                        break
                if self.celebrating:
                    break

        # Water puts out a burning gnome
        if self.on_fire and 0 <= ix < w and 0 <= iy < h and grid[iy, ix] == WATER:
            self.on_fire = False

        # Die after 3 seconds on fire
        if self.on_fire and (time.time() - self.fire_start_time) > 3.0:
            self.alive = False
            return

        # Walk speed: every 5 ticks normally, every 3 on fire, every 10 in water
        # Zombies walk slightly slower (7)
        in_water = (0 <= ix < w and 0 <= iy < h and grid[iy, ix] == WATER)
        if self.on_fire:
            walk_interval = 3
        elif self.is_zombie:
            walk_interval = 7
        elif in_water:
            walk_interval = 10
        else:
            walk_interval = 5

        # --- gravity ---
        below_y = iy + 1
        on_ground = False
        if below_y >= h:
            on_ground = True          # bottom of screen
        elif grid[below_y, ix] != EMPTY and grid[below_y, ix] not in (FIRE, NAPALM, WATER, POISON, HOLYWATER):
            on_ground = True          # standing on wall or sand (water is passable)

        if on_ground:
            self.vy = 0.0
            self.grounded = True
            self.gy = float(iy)
            self.fall_start = 0.0
            self.parachute_open = False

            # --- celebration hop ---
            if self.celebrating:
                if time.time() - self.celebrate_start >= 3.5:
                    self.celebrating = False
                else:
                    self.vy = -2.5
                    self.gy -= 0.5
                    self.grounded = False
                    return  # skip walking

            # --- walking ---
            # Zombies chase nearest living gnome
            if self.is_zombie and self.zombie_target is not None:
                tgt = self.zombie_target
                if tgt.alive and not tgt.is_zombie:
                    self.dir = 1 if tgt.gx > self.gx else -1
                else:
                    self.zombie_target = None

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
            if self.fall_start == 0.0:
                self.fall_start = time.time()

            # Deploy parachute after 0.2s of falling (if still available)
            # Don't deploy while doing a confetti celebration hop
            fall_dur = time.time() - self.fall_start
            if fall_dur >= 0.2 and self.has_parachute and not self.parachute_open and not self.celebrating and not self.is_zombie:
                self.parachute_open = True

            # Burn parachute if gnome is on fire
            if self.on_fire and self.has_parachute:
                self.has_parachute = False
                self.parachute_open = False

            # Check if fire/napalm nearby burns the parachute
            if self.parachute_open:
                for ddx in range(-2, 3):
                    for ddy in range(-4, 1):
                        cx, cy = ix + ddx, iy + ddy
                        if 0 <= cx < w and 0 <= cy < h and grid[cy, cx] in (FIRE, NAPALM):
                            self.has_parachute = False
                            self.parachute_open = False
                            break
                    else:
                        continue
                    break

            if self.parachute_open:
                # Parachute: slow descent
                self.vy = min(self.vy + 0.05, 0.5)
            elif in_water:
                # Water: half gravity, half terminal velocity
                self.vy = min(self.vy + 0.2, 1.5)
            else:
                self.vy = min(self.vy + 0.4, 3.0)   # gravity acceleration, terminal vel
            new_y = self.gy + self.vy
            # Check each cell we'd pass through
            target_y = int(new_y)
            for check_y in range(iy + 1, min(target_y + 1, h)):
                cell = grid[check_y, ix]
                if cell != EMPTY and cell not in (FIRE, NAPALM, WATER, POISON, HOLYWATER):
                    # Land on top of this cell
                    self.gy = float(check_y - 1)
                    self.vy = 0.0
                    self.grounded = True
                    return
            if target_y >= h:
                self.alive = False
                return
            self.gy = new_y


# ────────────────────────────────────────────
# Gibs — bouncing body pieces from explosions
# ────────────────────────────────────────────

_GIB_COLORS = [
    (200, 60, 60), (180, 50, 50), (160, 40, 40),
    (220, 80, 80), (140, 30, 30), (190, 70, 50),
]


class _Gib:
    """A small bouncing chunk that sprays out when a gnome dies."""

    def __init__(self, x, y, color=None):
        self.x = float(x)
        self.y = float(y)
        self.vx = random.uniform(-3.0, 3.0)
        self.vy = random.uniform(-5.0, -1.0)
        self.color = color or random.choice(_GIB_COLORS)
        self.alive = True
        self.rest_timer = 0  # frames at rest

    def step(self, grid):
        h, w = grid.shape
        # Gravity
        self.vy += 0.35
        # Move X
        new_x = self.x + self.vx
        ix, iy = int(new_x), int(self.y)
        if ix < 0 or ix >= w:
            self.vx = -self.vx * 0.6  # bounce off side walls
            new_x = self.x + self.vx
        elif 0 <= iy < h and grid[iy, ix] not in (EMPTY, FIRE, NAPALM, WATER):
            self.vx = -self.vx * 0.6  # bounce off solid
            new_x = self.x
        self.x = new_x

        # Move Y
        new_y = self.y + self.vy
        ix2 = int(self.x)
        iy2 = int(new_y)
        if iy2 >= h:
            # Hit bottom — rest on floor
            self.y = float(h - 1)
            self.vy = 0.0
            self.vx *= 0.5
            self.rest_timer += 1
        elif 0 <= iy2 < h and 0 <= ix2 < w and grid[iy2, ix2] not in (EMPTY, FIRE, NAPALM, WATER):
            # Hit something solid — bounce
            if self.vy > 0:
                self.vy = -self.vy * 0.4
                self.vx *= 0.8
                self.rest_timer += 1
            else:
                self.vy = 0.0
                self.rest_timer += 1
            new_y = self.y
        else:
            self.rest_timer = 0
        self.y = new_y

        # Clamp
        if self.x < 0:
            self.x = 0.0
        if self.x >= w:
            self.x = float(w - 1)

        # Die after resting long enough (30 frames ≈ 1s)
        if self.rest_timer > 30:
            # Check if effectively stopped
            if abs(self.vx) < 0.1 and abs(self.vy) < 0.5:
                self.alive = False


# ────────────────────────────────────────────
# Confetti
# ────────────────────────────────────────────

_CONFETTI_COLORS = [
    (255, 50, 50), (50, 255, 50), (80, 80, 255),
    (255, 255, 50), (255, 50, 255), (50, 255, 255),
    (255, 150, 0), (255, 100, 200), (150, 255, 100),
]


class _SandState:
    """NumPy grid-based sand sim. Much faster than dict."""

    def __init__(self, w, h):
        self.width = w
        self.height = h
        # 0=empty, 1=static wall, 2=heavy/sand, 3=fire, 4=wood, 5=concrete
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


def _throttle(ys, xs, cap=_PERF_CAP):
    """If there are more particles than cap, randomly sample a subset.
    Returns (ys, xs) — possibly trimmed."""
    n = len(ys)
    if n <= cap:
        return ys, xs
    # Process a random fraction so the per-frame cost stays bounded
    keep = np.random.choice(n, size=cap, replace=False)
    return ys[keep], xs[keep]


def _step(state, wind_active=False, wind_dir=1, reverse_gravity=False):
    """Vectorized physics step using numpy."""
    g = state.grid
    c = state.colors
    h, w = g.shape

    # Find all falling particles: sand, gunpowder, gasoline, water, confetti, poison, holy water
    falling = (g == HEAVY) | (g == GUNPOWDER) | (g == GASOLINE) | (g == WATER) | (g == CONFETTI) | (g == POISON) | (g == HOLYWATER)
    if not np.any(falling):
        return

    ys, xs = np.where(falling)

    # Shuffle order to avoid directional bias
    order = np.arange(len(ys))
    np.random.shuffle(order)
    ys = ys[order]
    xs = xs[order]

    # Throttle: skip particles when count is very high
    ys, xs = _throttle(ys, xs)

    grav = -1 if reverse_gravity else 1

    for i in range(len(ys)):
        y, x = int(ys[i]), int(xs[i])
        ptype = g[y, x]
        if ptype not in (HEAVY, GUNPOWDER, GASOLINE, WATER, CONFETTI, POISON, HOLYWATER):
            continue  # already moved by another particle this step
        col = c[y, x].copy()

        # Gasoline and water are more fluid — higher lateral slide chance
        # Confetti flutters — very high lateral drift
        if ptype == CONFETTI:
            slide_chance = 0.85
        elif ptype in (GASOLINE, WATER, POISON, HOLYWATER):
            slide_chance = 0.7
        else:
            slide_chance = 0.3

        ny = y + grav
        moved = False

        # Confetti flutters — 50% chance to skip falling, just drift sideways
        if ptype == CONFETTI and random.random() < 0.5:
            lx = x + (1 if random.random() < 0.5 else -1)
            if 0 <= lx < w and g[y, lx] == EMPTY:
                g[y, x] = EMPTY
                g[y, lx] = ptype
                c[y, lx] = col
            continue

        # Try straight down
        if 0 <= ny < h and g[ny, x] == EMPTY:
            g[y, x] = EMPTY
            g[ny, x] = ptype
            c[ny, x] = col
            y = ny
            moved = True
        else:
            # Confetti destroys on contact — can't land, just vanishes
            if ptype == CONFETTI:
                g[y, x] = EMPTY
                c[y, x] = (0, 0, 0)
                continue
            # Try diagonal left/right (random order)
            if random.random() < 0.5:
                tries = [(x - 1, ny), (x + 1, ny)]
            else:
                tries = [(x + 1, ny), (x - 1, ny)]
            for tx, ty in tries:
                if 0 <= tx < w and 0 <= ty < h and g[ty, tx] == EMPTY:
                    g[y, x] = EMPTY
                    g[ty, tx] = ptype
                    c[ty, tx] = col
                    x, y = tx, ty
                    moved = True
                    break

        # If didn't fall, try lateral slide
        if not moved:
            if random.random() < slide_chance:
                lx = x + (1 if random.random() < 0.5 else -1)
                if 0 <= lx < w and g[y, lx] == EMPTY:
                    g[y, x] = EMPTY
                    g[y, lx] = ptype
                    c[y, lx] = col
                    x = lx
                    moved = True

        # Wind push
        if wind_active and moved:
            wx = x + wind_dir
            if 0 <= wx < w and g[y, wx] == EMPTY:
                g[y, x] = EMPTY
                g[y, wx] = ptype
                c[y, wx] = col


def _ignite_gunpowder(state, start_x, start_y):
    """BFS chain-reaction: instantly convert ALL connected gunpowder to FIRE."""
    from collections import deque
    g = state.grid
    c = state.colors
    h, w = g.shape
    queue = deque()
    queue.append((start_x, start_y))
    visited = set()
    visited.add((start_x, start_y))
    while queue:
        cx, cy = queue.popleft()
        g[cy, cx] = FIRE
        c[cy, cx] = random.choice(_FIRE_COLORS)
        # Also blast neighbors: small chance to destroy adjacent non-gunpowder cells
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                visited.add((nx, ny))
                if g[ny, nx] == GUNPOWDER:
                    queue.append((nx, ny))
                elif g[ny, nx] == GASOLINE:
                    # Gasoline ignites instantly from explosion
                    g[ny, nx] = FIRE
                    c[ny, nx] = random.choice(_FIRE_COLORS)
                elif g[ny, nx] in (HEAVY, STATIC, WOOD) and random.random() < 0.4:
                    # Explosion blasts nearby materials
                    g[ny, nx] = FIRE
                    c[ny, nx] = random.choice(_FIRE_COLORS)


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

    # Throttle fire processing when particle count is huge
    ys, xs = _throttle(ys, xs)

    for i in range(len(ys)):
        y, x = int(ys[i]), int(xs[i])
        if g[y, x] != FIRE:
            continue
        col = tuple(random.choice(_FIRE_COLORS))

        # Consume neighbors — spread to adjacent flammable cells
        # CONCRETE is fireproof.  WOOD burns slowly.  HEAVY/STATIC burn faster.
        # WATER extinguishes fire on contact.
        extinguished = False
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
            nx, ny2 = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny2 < h:
                cell = g[ny2, nx]
                if cell == WATER:
                    # Water extinguishes this fire particle
                    g[y, x] = EMPTY
                    extinguished = True
                    break
                elif cell == WOOD:
                    if random.random() < 0.018:      # wood burns moderate
                        g[ny2, nx] = FIRE
                        c[ny2, nx] = random.choice(_FIRE_COLORS)
                elif cell == HEAVY or cell == STATIC:
                    if random.random() < 0.009:      # sand/wall burns slow
                        g[ny2, nx] = FIRE
                        c[ny2, nx] = random.choice(_FIRE_COLORS)
                elif cell == GUNPOWDER:
                    # Chain-reaction: BFS ignite ALL connected gunpowder instantly
                    _ignite_gunpowder(state, nx, ny2)
                elif cell == GASOLINE:
                    # Gasoline ignites instantly on contact with fire
                    g[ny2, nx] = FIRE
                    c[ny2, nx] = random.choice(_FIRE_COLORS)
                # CONCRETE: never catches fire
        if extinguished:
            continue

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
        if random.random() < 0.012:
            g[y, x] = EMPTY


def _step_napalm(state):
    """Physics step for napalm: like fire but FALLS downward (gravity-affected fire).
    Also spreads to flammable neighbors."""
    g = state.grid
    c = state.colors
    h, w = g.shape

    nap = (g == NAPALM)
    if not np.any(nap):
        return

    ys, xs = np.where(nap)
    order = np.arange(len(ys))
    np.random.shuffle(order)
    ys = ys[order]
    xs = xs[order]

    # Throttle napalm processing when particle count is huge
    ys, xs = _throttle(ys, xs)

    for i in range(len(ys)):
        y, x = int(ys[i]), int(xs[i])
        if g[y, x] != NAPALM:
            continue
        col = tuple(random.choice(_NAPALM_COLORS))

        # Spread fire to neighbors just like regular fire
        # WATER extinguishes napalm on contact.
        extinguished = False
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
            nx, ny2 = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny2 < h:
                cell = g[ny2, nx]
                if cell == WATER:
                    g[y, x] = EMPTY
                    extinguished = True
                    break
                elif cell == WOOD:
                    if random.random() < 0.018:
                        g[ny2, nx] = FIRE
                        c[ny2, nx] = random.choice(_FIRE_COLORS)
                elif cell == HEAVY or cell == STATIC:
                    if random.random() < 0.009:
                        g[ny2, nx] = FIRE
                        c[ny2, nx] = random.choice(_FIRE_COLORS)
                elif cell == GUNPOWDER:
                    _ignite_gunpowder(state, nx, ny2)
                elif cell == GASOLINE:
                    g[ny2, nx] = FIRE
                    c[ny2, nx] = random.choice(_FIRE_COLORS)
        if extinguished:
            continue

        # Napalm FALLS downward (like sand, but fire)
        ny = y + 1
        moved = False

        if 0 <= ny < h and g[ny, x] == EMPTY:
            g[y, x] = EMPTY
            g[ny, x] = NAPALM
            c[ny, x] = col
            y = ny
            moved = True
        else:
            # Try diagonal down-left/down-right
            if random.random() < 0.5:
                tries = [(x - 1, ny), (x + 1, ny)]
            else:
                tries = [(x + 1, ny), (x - 1, ny)]
            for tx, ty in tries:
                if 0 <= tx < w and 0 <= ty < h and g[ty, tx] == EMPTY:
                    g[y, x] = EMPTY
                    g[ty, tx] = NAPALM
                    c[ty, tx] = col
                    x, y = tx, ty
                    moved = True
                    break

        # Random lateral drift
        if not moved:
            if random.random() < 0.3:
                lx = x + (1 if random.random() < 0.5 else -1)
                if 0 <= lx < w and g[y, lx] == EMPTY:
                    g[y, x] = EMPTY
                    g[y, lx] = NAPALM
                    c[y, lx] = col
                    moved = True

        # Napalm lasts longer than fire (lower die-out chance)
        if random.random() < 0.007:
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
        self._font = pygame.font.Font(None, font_size)

    def draw(self, surface, font=None):
        c = self.active_color if self.active else self.color
        pygame.draw.rect(surface, c, self.rect, border_radius=8)
        pygame.draw.rect(surface, (100, 100, 120), self.rect, 2, border_radius=8)
        f = font or self._font
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
    MODE_WOOD = 5
    MODE_CONCRETE = 6
    MODE_FILL = 7
    MODE_GUNPOWDER = 8
    MODE_NAPALM = 9
    MODE_GASOLINE = 10
    MODE_WATER = 11
    MODE_HAND = 12
    MODE_CONFETTI = 13
    MODE_POISON = 14
    MODE_HOLYWATER = 15

    def __init__(self, window_width, window_height):
        self.visible = False
        self._ww = window_width
        self._wh = window_height
        self._gw = window_width // _CELL
        self._gh = window_height // _CELL
        self._state = _SandState(self._gw, self._gh)
        self._mode = self.MODE_POUR
        self._fill_material = self.MODE_POUR
        self._color = _PALE_YELLOW
        self._color_idx = 7
        self._wind_active = False
        self._wind_dir = 1
        self._reverse_gravity = False
        self._sim_tick = 0
        self._last_tick = 0.0
        self._last_wall_gx = None
        self._last_wall_gy = None
        self._gnomes = []
        self._gibs = []
        self._gnome_spawned_this_pinch = False
        self._fill_done_this_pinch = False
        self._held_gnome = None
        self._pixel_surf = pygame.Surface((self._gw, self._gh))
        self._scaled_surf = pygame.Surface((window_width, window_height))
        self._rgb_buf = np.zeros((self._gh, self._gw, 3), dtype=np.uint8)
        self._font_small = pygame.font.Font(None, 24)
        self._font_title = pygame.font.Font(None, 36)
        self._sim_tick = 0               # frame counter for sim stepping
        self._buttons = []
        self._build_buttons()

    def _build_buttons(self):
        bw = 88
        bh = 50
        margin = 5
        row2_y = self._wh - bh - margin
        row1_y = row2_y - bh - margin

        x = margin
        self._btn_pour = _Button(x, row1_y, bw, bh, "SAND", font_size=24); x += bw + margin
        self._btn_hand = _Button(x, row1_y, bw, bh, "HAND", font_size=24,
                                 color=(80, 60, 40), active_color=(220, 180, 120)); x += bw + margin
        self._btn_wood = _Button(x, row1_y, bw, bh, "WOOD", font_size=24,
                                 color=(70, 45, 20), active_color=(180, 120, 60)); x += bw + margin
        self._btn_concrete = _Button(x, row1_y, bw, bh, "CONCRT", font_size=22,
                                     color=(60, 60, 65), active_color=(160, 160, 170)); x += bw + margin
        self._btn_erase = _Button(x, row1_y, bw, bh, "ERASE", font_size=24); x += bw + margin
        self._btn_color = _Button(x, row1_y, bw, bh, "COLOR", font_size=24); x += bw + margin
        self._btn_gnome = _Button(x, row1_y, bw, bh, "GNOME", font_size=24); x += bw + margin
        self._btn_fire = _Button(x, row1_y, bw, bh, "FIRE", font_size=24,
                                 color=(80, 30, 0), active_color=(255, 120, 0)); x += bw + margin
        self._btn_confetti = _Button(x, row1_y, bw, bh, "CONFTI", font_size=22,
                                     color=(100, 40, 100), active_color=(255, 100, 255)); x += bw + margin

        x = margin
        self._btn_wind = _Button(x, row2_y, bw, bh, "WIND", font_size=24); x += bw + margin
        self._btn_wind_dir = _Button(x, row2_y, bw, bh, "WIND>", font_size=22); x += bw + margin
        self._btn_gravity = _Button(x, row2_y, bw, bh, "GRAV", font_size=24); x += bw + margin
        self._btn_clear = _Button(x, row2_y, bw, bh, "CLEAR", font_size=24); x += bw + margin
        self._btn_fill = _Button(x, row2_y, bw, bh, "FILL", font_size=24,
                                 color=(50, 50, 80), active_color=(120, 180, 255)); x += bw + margin
        self._btn_gunpowder = _Button(x, row2_y, bw, bh, "GUNPW", font_size=22,
                                      color=(50, 50, 50), active_color=(120, 120, 120)); x += bw + margin
        self._btn_napalm = _Button(x, row2_y, bw, bh, "NAPLM", font_size=22,
                                   color=(120, 30, 0), active_color=(255, 60, 0)); x += bw + margin
        self._btn_gasoline = _Button(x, row2_y, bw, bh, "GAS", font_size=24,
                                     color=(70, 80, 20), active_color=(200, 220, 60)); x += bw + margin
        self._btn_water = _Button(x, row2_y, bw, bh, "WATER", font_size=24,
                                  color=(15, 50, 120), active_color=(40, 130, 255)); x += bw + margin
        self._btn_poison = _Button(x, row2_y, bw, bh, "ZOMBI", font_size=22,
                                   color=(20, 80, 10), active_color=(50, 200, 30)); x += bw + margin
        self._btn_holywater = _Button(x, row2_y, bw, bh, "HOLY", font_size=24,
                                      color=(80, 80, 130), active_color=(200, 200, 255)); x += bw + margin

        quit_h = bh * 2 + margin
        self._btn_quit = _Button(self._ww - bw - margin, row1_y, bw, quit_h, "QUIT",
                                 color=(120, 30, 30), active_color=(255, 60, 60), font_size=28)

        self._buttons = [
            self._btn_pour, self._btn_hand, self._btn_wood, self._btn_concrete,
            self._btn_erase, self._btn_color,
            self._btn_gnome, self._btn_fire, self._btn_gunpowder, self._btn_napalm,
            self._btn_gasoline, self._btn_water, self._btn_confetti,
            self._btn_poison, self._btn_holywater,
            self._btn_wind, self._btn_wind_dir, self._btn_gravity, self._btn_clear,
            self._btn_fill,
            self._btn_quit,
        ]

    def open(self):
        self.visible = True
        self._state = _SandState(self._gw, self._gh)
        self._mode = self.MODE_POUR
        self._fill_material = self.MODE_POUR
        self._color = _PALE_YELLOW
        self._color_idx = 7
        self._wind_active = False
        self._wind_dir = 1
        self._reverse_gravity = False
        self._sim_tick = 0
        self._last_tick = time.time()
        self._last_wall_gx = None
        self._last_wall_gy = None
        self._gnomes = []
        self._gibs = []
        self._gnome_spawned_this_pinch = False
        self._fill_done_this_pinch = False
        self._held_gnome = None
        self._update_button_states()

    def close(self):
        self.visible = False

    def random_color(self):
        self._color_idx = (self._color_idx + 1) % len(_FUN_COLORS)
        self._color = _FUN_COLORS[self._color_idx]

    def _update_button_states(self):
        self._btn_pour.active = (self._mode == self.MODE_POUR)
        self._btn_hand.active = (self._mode == self.MODE_HAND)
        self._btn_wood.active = (self._mode == self.MODE_WOOD)
        self._btn_concrete.active = (self._mode == self.MODE_CONCRETE)
        self._btn_erase.active = (self._mode == self.MODE_ERASE)
        self._btn_gnome.active = (self._mode == self.MODE_GNOME)
        self._btn_fire.active = (self._mode == self.MODE_FIRE)
        self._btn_gunpowder.active = (self._mode == self.MODE_GUNPOWDER)
        self._btn_napalm.active = (self._mode == self.MODE_NAPALM)
        self._btn_gasoline.active = (self._mode == self.MODE_GASOLINE)
        self._btn_water.active = (self._mode == self.MODE_WATER)
        self._btn_confetti.active = (self._mode == self.MODE_CONFETTI)
        self._btn_poison.active = (self._mode == self.MODE_POISON)
        self._btn_holywater.active = (self._mode == self.MODE_HOLYWATER)
        self._btn_fill.active = (self._mode == self.MODE_FILL)
        # Show what material fill will use
        _fill_names = {
            self.MODE_POUR: "FILL:S",
            self.MODE_WOOD: "FILL:Wd", self.MODE_CONCRETE: "FILL:C",
            self.MODE_FIRE: "FILL:F", self.MODE_GUNPOWDER: "FILL:GP",
            self.MODE_NAPALM: "FILL:N", self.MODE_GASOLINE: "FILL:G",
            self.MODE_WATER: "FILL:Wt",
        }
        self._btn_fill.label = _fill_names.get(self._fill_material, "FILL")
        self._btn_wind.active = self._wind_active
        self._btn_gravity.active = self._reverse_gravity
        self._btn_wind.label = "WIND ON" if self._wind_active else "WIND"
        self._btn_wind_dir.label = "< WIND" if self._wind_dir == -1 else "WIND >"
        self._btn_gravity.label = "GRV UP" if self._reverse_gravity else "GRAV"
        self._btn_color.swatch_color = self._color

    def _in_ui_zone(self, px, py):
        for btn in self._buttons:
            if btn.hit(px, py):
                return True
        return False

    def _flood_fill(self, gx, gy):
        """Paint-bucket flood fill: fills contiguous EMPTY cells with the
        current fill material, bounded by any non-empty cell.
        Capped at 50 000 cells to avoid freezing on huge open areas."""
        g = self._state.grid
        h, w = g.shape
        if gx < 0 or gx >= w or gy < 0 or gy >= h:
            return
        if g[gy, gx] != EMPTY:
            return   # must click on an empty cell

        # Determine fill type and color from _fill_material
        mat = self._fill_material
        if mat == self.MODE_POUR:
            ptype, color_fn = HEAVY, lambda: self._color
        elif mat == self.MODE_WALL:
            ptype, color_fn = STATIC, lambda: _WALL_COLOR
        elif mat == self.MODE_WOOD:
            ptype, color_fn = WOOD, lambda: random.choice(_WOOD_COLORS)
        elif mat == self.MODE_CONCRETE:
            ptype, color_fn = CONCRETE, lambda: _CONCRETE_COLOR
        elif mat == self.MODE_FIRE:
            ptype, color_fn = FIRE, lambda: random.choice(_FIRE_COLORS)
        elif mat == self.MODE_GUNPOWDER:
            ptype, color_fn = GUNPOWDER, lambda: random.choice(_GUNPOWDER_COLORS)
        elif mat == self.MODE_NAPALM:
            ptype, color_fn = NAPALM, lambda: random.choice(_NAPALM_COLORS)
        elif mat == self.MODE_GASOLINE:
            ptype, color_fn = GASOLINE, lambda: random.choice(_GASOLINE_COLORS)
        elif mat == self.MODE_WATER:
            ptype, color_fn = WATER, lambda: random.choice(_WATER_COLORS)
        else:
            ptype, color_fn = HEAVY, lambda: self._color

        # BFS flood fill
        from collections import deque
        queue = deque()
        queue.append((gx, gy))
        visited = set()
        visited.add((gx, gy))
        cap = 50000
        filled = 0
        while queue and filled < cap:
            cx, cy = queue.popleft()
            self._state.add(ptype, cx, cy, color_fn())
            filled += 1
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                    if g[ny, nx] == EMPTY:
                        visited.add((nx, ny))
                        queue.append((nx, ny))
        if filled > 0:
            print(f"Flood fill: {filled} cells")

    def handle_tap(self, px, py):
        if self._btn_quit.hit(px, py):
            self.close()
            print("Closed Sand (quit button)")
            return
        if self._btn_pour.hit(px, py):
            self._mode = self.MODE_POUR
            self._fill_material = self.MODE_POUR
            self._update_button_states(); return
        if self._btn_hand.hit(px, py):
            self._mode = self.MODE_HAND
            self._update_button_states(); return
        if self._btn_wood.hit(px, py):
            self._mode = self.MODE_WOOD
            self._fill_material = self.MODE_WOOD
            self._update_button_states(); return
        if self._btn_concrete.hit(px, py):
            self._mode = self.MODE_CONCRETE
            self._fill_material = self.MODE_CONCRETE
            self._update_button_states(); return
        if self._btn_erase.hit(px, py):
            self._mode = self.MODE_ERASE
            self._update_button_states(); return
        if self._btn_gnome.hit(px, py):
            self._mode = self.MODE_GNOME
            self._update_button_states(); return
        if self._btn_fire.hit(px, py):
            self._mode = self.MODE_FIRE
            self._fill_material = self.MODE_FIRE
            self._update_button_states(); return
        if self._btn_gunpowder.hit(px, py):
            self._mode = self.MODE_GUNPOWDER
            self._fill_material = self.MODE_GUNPOWDER
            self._update_button_states(); return
        if self._btn_napalm.hit(px, py):
            self._mode = self.MODE_NAPALM
            self._fill_material = self.MODE_NAPALM
            self._update_button_states(); return
        if self._btn_gasoline.hit(px, py):
            self._mode = self.MODE_GASOLINE
            self._fill_material = self.MODE_GASOLINE
            self._update_button_states(); return
        if self._btn_water.hit(px, py):
            self._mode = self.MODE_WATER
            self._fill_material = self.MODE_WATER
            self._update_button_states(); return
        if self._btn_confetti.hit(px, py):
            self._mode = self.MODE_CONFETTI
            self._update_button_states(); return
        if self._btn_poison.hit(px, py):
            self._mode = self.MODE_POISON
            self._update_button_states(); return
        if self._btn_holywater.hit(px, py):
            self._mode = self.MODE_HOLYWATER
            self._update_button_states(); return
        if self._btn_fill.hit(px, py):
            self._mode = self.MODE_FILL
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
            self._gibs = []
            return
        if not self._in_ui_zone(px, py):
            gx, gy = int(px) // _CELL, int(py) // _CELL
            if self._mode == self.MODE_POUR:
                for _ in range(25):
                    rx = gx + random.randint(-5, 5)
                    ry = gy + random.randint(-5, 2)
                    self._state.add(HEAVY, rx, ry, self._color)
            elif self._mode == self.MODE_HAND:
                # Pick up nearest gnome within 6 grid cells
                best, best_d = None, 6.0
                for gnome in self._gnomes:
                    d = math.hypot(gnome.gx - gx, gnome.gy - gy)
                    if d < best_d:
                        best_d = d
                        best = gnome
                if best:
                    best.held = True
                    best.vy = 0.0
                    self._held_gnome = best
            elif self._mode == self.MODE_WOOD:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        self._state.add(WOOD, gx + dx, gy + dy, random.choice(_WOOD_COLORS))
            elif self._mode == self.MODE_CONCRETE:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        self._state.add(CONCRETE, gx + dx, gy + dy, _CONCRETE_COLOR)
            elif self._mode == self.MODE_GNOME:
                self._gnomes.append(_Gnome(gx, gy))
            elif self._mode == self.MODE_FIRE:
                for _ in range(15):
                    rx = gx + random.randint(-3, 3)
                    ry = gy + random.randint(-2, 2)
                    self._state.add(FIRE, rx, ry, random.choice(_FIRE_COLORS))
            elif self._mode == self.MODE_GUNPOWDER:
                for _ in range(25):
                    rx = gx + random.randint(-5, 5)
                    ry = gy + random.randint(-5, 2)
                    self._state.add(GUNPOWDER, rx, ry, random.choice(_GUNPOWDER_COLORS))
            elif self._mode == self.MODE_NAPALM:
                for _ in range(15):
                    rx = gx + random.randint(-3, 3)
                    ry = gy + random.randint(-2, 2)
                    self._state.add(NAPALM, rx, ry, random.choice(_NAPALM_COLORS))
            elif self._mode == self.MODE_GASOLINE:
                for _ in range(25):
                    rx = gx + random.randint(-5, 5)
                    ry = gy + random.randint(-5, 2)
                    self._state.add(GASOLINE, rx, ry, random.choice(_GASOLINE_COLORS))
            elif self._mode == self.MODE_WATER:
                for _ in range(25):
                    rx = gx + random.randint(-5, 5)
                    ry = gy + random.randint(-5, 2)
                    self._state.add(WATER, rx, ry, random.choice(_WATER_COLORS))
            elif self._mode == self.MODE_CONFETTI:
                for _ in range(25):
                    rx = gx + random.randint(-5, 5)
                    ry = gy + random.randint(-5, 2)
                    self._state.add(CONFETTI, rx, ry, random.choice(_CONFETTI_COLORS))
            elif self._mode == self.MODE_POISON:
                for _ in range(15):
                    rx = gx + random.randint(-3, 3)
                    ry = gy + random.randint(-3, 1)
                    self._state.add(POISON, rx, ry, random.choice(_POISON_COLORS))
            elif self._mode == self.MODE_HOLYWATER:
                for _ in range(20):
                    rx = gx + random.randint(-4, 4)
                    ry = gy + random.randint(-4, 1)
                    self._state.add(HOLYWATER, rx, ry, random.choice(_HOLYWATER_COLORS))
            elif self._mode == self.MODE_FILL:
                self._flood_fill(gx, gy)

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
        elif self._mode == self.MODE_HAND:
            # Carry held gnome to cursor position
            if self._held_gnome and self._held_gnome.alive:
                self._held_gnome.gx = float(gx)
                self._held_gnome.gy = float(gy)
            else:
                # Try to grab nearest gnome
                best, best_d = None, 6.0
                for gnome in self._gnomes:
                    d = math.hypot(gnome.gx - gx, gnome.gy - gy)
                    if d < best_d:
                        best_d = d
                        best = gnome
                if best:
                    best.held = True
                    best.vy = 0.0
                    self._held_gnome = best
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_WOOD:
            if (self._last_wall_gx is not None and self._last_wall_gy is not None
                    and abs(gx - self._last_wall_gx) <= 8
                    and abs(gy - self._last_wall_gy) <= 8):
                line_pts = _bresenham(self._last_wall_gx, self._last_wall_gy, gx, gy)
                for lx, ly in line_pts:
                    for dx in range(-1, 2):
                        for dy in range(-1, 2):
                            self._state.add(WOOD, lx + dx, ly + dy, random.choice(_WOOD_COLORS))
            else:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        self._state.add(WOOD, gx + dx, gy + dy, random.choice(_WOOD_COLORS))
            self._last_wall_gx = gx
            self._last_wall_gy = gy
        elif self._mode == self.MODE_CONCRETE:
            if (self._last_wall_gx is not None and self._last_wall_gy is not None
                    and abs(gx - self._last_wall_gx) <= 8
                    and abs(gy - self._last_wall_gy) <= 8):
                line_pts = _bresenham(self._last_wall_gx, self._last_wall_gy, gx, gy)
                for lx, ly in line_pts:
                    for dx in range(-1, 2):
                        for dy in range(-1, 2):
                            self._state.add(CONCRETE, lx + dx, ly + dy, _CONCRETE_COLOR)
            else:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        self._state.add(CONCRETE, gx + dx, gy + dy, _CONCRETE_COLOR)
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
        elif self._mode == self.MODE_GUNPOWDER:
            for _ in range(10):
                rx = gx + random.randint(-3, 3)
                ry = gy + random.randint(-2, 1)
                self._state.add(GUNPOWDER, rx, ry, random.choice(_GUNPOWDER_COLORS))
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_NAPALM:
            for _ in range(8):
                rx = gx + random.randint(-2, 2)
                ry = gy + random.randint(-2, 2)
                self._state.add(NAPALM, rx, ry, random.choice(_NAPALM_COLORS))
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_GASOLINE:
            for _ in range(10):
                rx = gx + random.randint(-3, 3)
                ry = gy + random.randint(-2, 1)
                self._state.add(GASOLINE, rx, ry, random.choice(_GASOLINE_COLORS))
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_WATER:
            for _ in range(10):
                rx = gx + random.randint(-3, 3)
                ry = gy + random.randint(-2, 1)
                self._state.add(WATER, rx, ry, random.choice(_WATER_COLORS))
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_CONFETTI:
            for _ in range(10):
                rx = gx + random.randint(-3, 3)
                ry = gy + random.randint(-2, 1)
                self._state.add(CONFETTI, rx, ry, random.choice(_CONFETTI_COLORS))
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_POISON:
            for _ in range(8):
                rx = gx + random.randint(-2, 2)
                ry = gy + random.randint(-2, 1)
                self._state.add(POISON, rx, ry, random.choice(_POISON_COLORS))
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_HOLYWATER:
            for _ in range(10):
                rx = gx + random.randint(-3, 3)
                ry = gy + random.randint(-2, 1)
                self._state.add(HOLYWATER, rx, ry, random.choice(_HOLYWATER_COLORS))
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_FILL:
            # One-shot fill per pinch, same as gnome
            if not getattr(self, '_fill_done_this_pinch', False):
                self._flood_fill(gx, gy)
                self._fill_done_this_pinch = True
            self._last_wall_gx = None
            self._last_wall_gy = None

    def handle_pinch_end(self):
        self._gnome_spawned_this_pinch = False
        self._fill_done_this_pinch = False
        self._last_wall_gx = None
        self._last_wall_gy = None
        # Drop held gnome
        if self._held_gnome:
            self._held_gnome.held = False
            self._held_gnome.vy = 0.0
            self._held_gnome.fall_start = 0.0
            self._held_gnome.parachute_open = False
            self._held_gnome = None

    # Ordered list of modes the scroll wheel cycles through
    _SCROLL_MODES = [
        MODE_POUR, MODE_HAND, MODE_WOOD, MODE_CONCRETE, MODE_ERASE,
        MODE_GNOME, MODE_FIRE, MODE_GUNPOWDER, MODE_NAPALM, MODE_GASOLINE,
        MODE_WATER, MODE_CONFETTI, MODE_POISON, MODE_HOLYWATER, MODE_FILL,
    ]

    def handle_scroll(self, direction):
        """Cycle through tool modes. direction: +1 = next, -1 = previous."""
        try:
            idx = self._SCROLL_MODES.index(self._mode)
        except ValueError:
            idx = 0
        idx = (idx + direction) % len(self._SCROLL_MODES)
        self._mode = self._SCROLL_MODES[idx]
        # Update fill material for material modes
        if self._mode not in (self.MODE_ERASE, self.MODE_GNOME, self.MODE_HAND, self.MODE_FILL, self.MODE_CONFETTI, self.MODE_POISON, self.MODE_HOLYWATER):
            self._fill_material = self._mode
        self._update_button_states()

    def draw(self, surface, gui_scale):
        now = time.time()
        dt = now - self._last_tick if self._last_tick else 0.016
        self._last_tick = now

        # Fixed 1 sim step per frame — no accumulator, no catch-up, no jitter.
        # Main loop runs at 60fps; we step the sim every other frame to hit ~30fps sim rate.
        self._sim_tick += 1
        if self._sim_tick % 2 == 0:
            _step(self._state, self._wind_active, self._wind_dir, self._reverse_gravity)
            _step_fire(self._state)
            _step_napalm(self._state)

            # Assign zombie targets — each zombie chases nearest living gnome
            living = [g for g in self._gnomes if g.alive and not g.is_zombie and not g.frozen]
            for gnome in self._gnomes:
                if gnome.is_zombie and gnome.alive and not gnome.frozen:
                    best, best_d = None, 999.0
                    for lg in living:
                        d = abs(gnome.gx - lg.gx) + abs(gnome.gy - lg.gy)
                        if d < best_d:
                            best_d = d
                            best = lg
                    gnome.zombie_target = best

            for gnome in self._gnomes:
                gnome.step(self._state.grid)

            # Zombie bite — zombie touches living gnome: both freeze 1s, then living turns zombie
            zombies = [g for g in self._gnomes if g.alive and g.is_zombie and not g.frozen]
            alive_live = [g for g in self._gnomes if g.alive and not g.is_zombie and not g.frozen]
            for zg in zombies:
                for lg in alive_live:
                    if abs(zg.gx - lg.gx) < 3 and abs(zg.gy - lg.gy) < 3:
                        # Freeze both for 1 second
                        zg.frozen = True
                        zg.freeze_start = time.time()
                        lg.frozen = True
                        lg.freeze_start = time.time()
                        # Convert living to zombie after freeze
                        lg.is_zombie = True
                        lg.color = (30, 160, 30)
                        lg.hat_color = (20, 100, 20)
                        lg.has_parachute = False
                        lg.parachute_open = False
                        lg.celebrating = False
                        break

            # Spawn gibs when gnomes die from fire
            new_gnomes = []
            for gnome in self._gnomes:
                if gnome.alive:
                    new_gnomes.append(gnome)
                else:
                    # Dead gnome — spray gibs
                    gx, gy = int(gnome.gx), int(gnome.gy)
                    gib_color = gnome.color if not gnome.on_fire else random.choice(_GIB_COLORS)
                    for _ in range(random.randint(6, 12)):
                        self._gibs.append(_Gib(gx, gy, gib_color))
            self._gnomes = new_gnomes

            # Step gibs
            for gib in self._gibs:
                gib.step(self._state.grid)
            self._gibs = [g for g in self._gibs if g.alive]

        surface.fill(_BLACK)

        # Fast pixel rendering — reuse buffer to avoid per-frame allocation
        st = self._state
        # Copy colors into pre-allocated buffer, zero out empty cells in-place
        np.copyto(self._rgb_buf, st.colors)
        self._rgb_buf[st.grid == EMPTY] = 0

        # Blit into pre-allocated small surface, then scale into pre-allocated large surface
        pygame.surfarray.blit_array(self._pixel_surf, self._rgb_buf.transpose(1, 0, 2))
        pygame.transform.scale(self._pixel_surf, (self._ww, self._wh), self._scaled_surf)
        surface.blit(self._scaled_surf, (0, 0))

        # Draw gnomes as stick figures
        for gnome in self._gnomes:
            sx = int(gnome.gx * _CELL + _CELL // 2)
            # Offset sy so feet land on the top of the cell below
            sy = int(gnome.gy * _CELL + _CELL) - 22
            c = gnome.color
            # If on fire, flicker between orange/red
            if gnome.on_fire:
                c = random.choice([(255, 80, 0), (255, 0, 0), (255, 180, 0)])

            # Head
            pygame.draw.circle(surface, c, (sx, sy - 14), 8)
            # Hat — pointy gnome hat
            hat_c = gnome.hat_color if not gnome.on_fire else c
            pygame.draw.polygon(surface, hat_c, [
                (sx - 8, sy - 20),      # left brim
                (sx + 8, sy - 20),      # right brim
                (sx + gnome.dir * 3, sy - 35),  # pointy tip leans in walk dir
            ])
            # Parachute — drawn above gnome when deployed
            if gnome.parachute_open:
                chute_c = (240, 240, 240)
                # Canopy arc
                pygame.draw.arc(surface, chute_c,
                                (sx - 21, sy - 57, 42, 34), 0, math.pi, 3)
                # Fill canopy
                pygame.draw.ellipse(surface, (220, 220, 230),
                                    (sx - 21, sy - 57, 42, 17))
                # Strings from canopy edges to shoulders
                pygame.draw.line(surface, chute_c, (sx - 18, sy - 47), (sx - 5, sy - 20), 1)
                pygame.draw.line(surface, chute_c, (sx + 18, sy - 47), (sx + 5, sy - 20), 1)
                pygame.draw.line(surface, chute_c, (sx, sy - 55), (sx, sy - 35), 1)
            # Held indicator — draw a little hand icon above
            if gnome.held:
                pygame.draw.circle(surface, (220, 180, 120), (sx, sy - 43), 5)
                pygame.draw.line(surface, (220, 180, 120), (sx, sy - 38), (sx, sy - 28), 2)
            # Body
            pygame.draw.line(surface, c, (sx, sy - 6), (sx, sy + 12), 3)
            # Arms
            arm_wave = 4 if gnome.grounded and gnome.walk_timer == 0 else 0
            if gnome.on_fire:
                arm_wave = random.randint(-5, 5)  # frantic arm waving
            if gnome.celebrating:
                # Arms raised in celebration — wave them!
                wave = random.randint(-3, 3)
                pygame.draw.line(surface, c, (sx, sy), (sx - 10, sy - 14 + wave), 3)
                pygame.draw.line(surface, c, (sx, sy), (sx + 10, sy - 14 - wave), 3)
            elif gnome.parachute_open:
                # Arms up holding chute strings
                pygame.draw.line(surface, c, (sx, sy), (sx - 10, sy - 14), 3)
                pygame.draw.line(surface, c, (sx, sy), (sx + 10, sy - 14), 3)
            else:
                pygame.draw.line(surface, c, (sx - 9, sy + arm_wave), (sx + 9, sy - arm_wave), 3)
            # Legs — animate walking
            if gnome.grounded:
                leg_off = 8 if gnome.walk_timer == 0 else 4
                pygame.draw.line(surface, c, (sx, sy + 12), (sx - leg_off, sy + 22), 3)
                pygame.draw.line(surface, c, (sx, sy + 12), (sx + leg_off, sy + 22), 3)
            else:
                # Falling — legs together
                pygame.draw.line(surface, c, (sx, sy + 12), (sx - 4, sy + 22), 3)
                pygame.draw.line(surface, c, (sx, sy + 12), (sx + 4, sy + 22), 3)
            # Direction indicator — eye dot
            eye_x = sx + (4 * gnome.dir)
            eye_color = (255, 0, 0) if gnome.is_zombie else (255, 255, 255)
            pygame.draw.circle(surface, eye_color, (eye_x, sy - 16), 2)
            # Frozen indicator — icy shimmer
            if gnome.frozen:
                pygame.draw.circle(surface, (150, 200, 255), (sx, sy - 5), 18, 2)
            # Fire particles around burning gnome
            if gnome.on_fire:
                for _ in range(3):
                    fx = sx + random.randint(-8, 8)
                    fy = sy + random.randint(-18, 9)
                    pygame.draw.circle(surface, random.choice(_FIRE_COLORS), (fx, fy), random.randint(2, 4))

        # Draw gibs (bouncing body pieces)
        for gib in self._gibs:
            gx_px = int(gib.x * _CELL + _CELL // 2)
            gy_px = int(gib.y * _CELL + _CELL // 2)
            pygame.draw.rect(surface, gib.color, (gx_px - 2, gy_px - 2, 5, 5))

        # Draw buttons
        for btn in self._buttons:
            btn.draw(surface)

        # Particle count (cached font)
        count = st.count()
        n_gnomes = len(self._gnomes)
        info = f"{count} particles"
        if n_gnomes:
            info += f"  |  {n_gnomes} gnomes"
        ct = self._font_small.render(info, True, (70, 70, 70))
        surface.blit(ct, (self._ww - 140, 16))

        # Title (cached font)
        title = self._font_title.render("DESERT SANDS", True, (255, 200, 100))
        surface.blit(title, (self._ww // 2 - 80, 16))
