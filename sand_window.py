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
ICE = 13
MONEY = 14
DIRT = 15
MAGMA = 16
SEED = 17
PLANT = 18
STEAM = 19
TUNNEL = 20
GLASS = 21

_WOOD_COLOR = (139, 90, 43)
_WOOD_COLORS = [(139, 90, 43), (120, 75, 35), (160, 105, 50), (110, 70, 30)]
_CONCRETE_COLOR = (140, 140, 145)
_GUNPOWDER_COLORS = [(80, 80, 80), (60, 60, 60), (40, 40, 40), (100, 100, 100), (30, 30, 30)]
_NAPALM_COLORS = [(255, 60, 0), (255, 100, 0), (255, 40, 20), (200, 50, 0), (255, 120, 30)]
_GASOLINE_COLORS = [(180, 200, 50), (160, 180, 40), (200, 210, 60), (140, 170, 30), (190, 190, 55)]
_WATER_COLORS = [(30, 100, 220), (40, 120, 240), (20, 80, 200), (50, 130, 255), (35, 110, 230)]
_POISON_COLORS = [(50, 180, 20), (30, 160, 10), (70, 200, 30), (40, 140, 15), (60, 190, 25)]
_HOLYWATER_COLORS = [(200, 200, 255), (180, 180, 255), (220, 220, 255), (160, 180, 255), (210, 210, 240)]
_ICE_COLORS = [(180, 220, 255), (160, 210, 250), (200, 230, 255), (140, 200, 245), (190, 225, 255)]
_MONEY_COLORS = [(40, 180, 40), (30, 160, 30), (60, 200, 50), (20, 140, 20), (50, 190, 45)]
_DIRT_COLORS = [(101, 67, 33), (85, 55, 25), (120, 80, 40), (90, 60, 30), (110, 72, 36)]
_MAGMA_COLORS = [(255, 80, 0), (255, 50, 10), (255, 120, 20), (220, 40, 0), (255, 160, 30)]
_SEED_COLORS = [(120, 80, 20), (100, 70, 15), (140, 95, 30), (90, 60, 10), (130, 85, 25)]
_PLANT_COLORS = [(30, 140, 30), (20, 120, 20), (40, 160, 40), (50, 180, 50), (25, 130, 25),
                 (60, 170, 35), (35, 150, 45)]
_STEAM_COLORS = [(200, 200, 210), (180, 185, 195), (220, 220, 230), (160, 165, 175), (210, 215, 225)]
_GLASS_COLORS = [(180, 220, 240), (160, 200, 230), (200, 235, 250), (140, 195, 225), (190, 230, 245)]

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
        self.zombie_pending = False     # will turn zombie when freeze ends
        # Ice freeze state
        self.ice_frozen = False          # frozen solid by touching ice
        self._original_color = None      # saved color before ice tint
        self._original_hat = None
        # Money state
        self.money_target = None         # grid (x,y) of money pile we're heading to
        self.collecting_money = False    # standing on money, picking it up
        self.collect_start = 0.0        # when we started collecting
        self.money_happy = False        # hopping after collecting
        self.money_happy_start = 0.0

    def _can_walk(self, ix, iy, direction, grid):
        """Check if we can walk one step in the given direction.
        Returns (new_gx, new_gy) or None."""
        _passable = (EMPTY, FIRE, NAPALM, WATER, POISON, HOLYWATER, MONEY)
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
            if time.time() - self.freeze_start >= 2.0:
                self.frozen = False
                # Convert to zombie now that freeze is over
                if self.zombie_pending:
                    self.zombie_pending = False
                    self.is_zombie = True
                    self.color = (30, 160, 30)
                    self.hat_color = (20, 100, 20)
                    self.has_parachute = False
                    self.parachute_open = False
                    self.celebrating = False
            else:
                return  # can't move while frozen

        # --- Ice freeze: check if touching ice ---
        touching_ice = False
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                cx, cy = ix + dx, iy + dy
                if 0 <= cx < w and 0 <= cy < h and grid[cy, cx] == ICE:
                    touching_ice = True
                    break
            if touching_ice:
                break
        if touching_ice:
            if not self.ice_frozen:
                # Freeze solid — save original colors, turn light blue
                self.ice_frozen = True
                self._original_color = self.color
                self._original_hat = self.hat_color
                self.color = (160, 210, 255)
                self.hat_color = (130, 180, 240)
            return  # can't move while touching ice
        elif self.ice_frozen:
            # No longer touching ice — thaw out, restore colors
            self.ice_frozen = False
            if self._original_color:
                self.color = self._original_color
                self.hat_color = self._original_hat
                self._original_color = None
                self._original_hat = None

        # Check if standing in or near fire (2-cell radius)
        if not self.on_fire:
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    cx, cy = ix + dx, iy + dy
                    if 0 <= cx < w and 0 <= cy < h and grid[cy, cx] in (FIRE, NAPALM, MAGMA):
                        self.on_fire = True
                        self.fire_start_time = time.time()
                        break
                if self.on_fire:
                    break

        # Check if touching poison — freeze 2s then turn zombie
        if not self.is_zombie and not self.on_fire and not self.frozen:
            touched_poison = False
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    cx, cy = ix + dx, iy + dy
                    if 0 <= cx < w and 0 <= cy < h and grid[cy, cx] == POISON:
                        touched_poison = True
                        break
                if touched_poison:
                    break
            if touched_poison:
                self.frozen = True
                self.freeze_start = time.time()
                self.zombie_pending = True

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

        # --- Money collection behavior (non-zombie, non-fire gnomes) ---
        if not self.is_zombie and not self.on_fire and not self.celebrating:
            # If currently collecting money — slowly destroy money under feet
            if self.collecting_money:
                # Check if still touching money
                touching_money = False
                for dx in range(-2, 3):
                    for dy in range(-1, 3):
                        cx2, cy2 = ix + dx, iy + dy
                        if 0 <= cx2 < w and 0 <= cy2 < h and grid[cy2, cx2] == MONEY:
                            touching_money = True
                            break
                    if touching_money:
                        break
                if touching_money:
                    # Slowly destroy one money cell every ~8 ticks
                    if random.random() < 0.12:
                        for dx in range(-2, 3):
                            for dy in range(-1, 3):
                                cx2, cy2 = ix + dx, iy + dy
                                if 0 <= cx2 < w and 0 <= cy2 < h and grid[cy2, cx2] == MONEY:
                                    grid[cy2, cx2] = EMPTY
                                    break
                            else:
                                continue
                            break
                else:
                    # All money gone — happy hop!
                    self.collecting_money = False
                    self.money_target = None
                    self.money_happy = True
                    self.money_happy_start = time.time()
            elif self.money_happy:
                # Hop for 2 seconds after collecting
                if time.time() - self.money_happy_start >= 2.0:
                    self.money_happy = False
            elif self.money_target is None:
                # Scan for nearby money (wide radius)
                best_money = None
                best_dist = 40.0  # max detection range in grid cells
                for dx in range(-40, 41, 2):
                    for dy in range(-20, 21, 2):
                        cx2, cy2 = ix + dx, iy + dy
                        if 0 <= cx2 < w and 0 <= cy2 < h and grid[cy2, cx2] == MONEY:
                            d = math.hypot(dx, dy)
                            if d < best_dist:
                                best_dist = d
                                best_money = (cx2, cy2)
                if best_money:
                    self.money_target = best_money

        # Water puts out a burning gnome
        if self.on_fire and 0 <= ix < w and 0 <= iy < h and grid[iy, ix] == WATER:
            self.on_fire = False

        # Die after 3 seconds on fire
        if self.on_fire and (time.time() - self.fire_start_time) > 3.0:
            self.alive = False
            return

        # Walk speed: every 5 ticks normally, every 3 on fire, every 10 in water
        # Zombies always walk at 7 (don't speed up on fire)
        in_water = (0 <= ix < w and 0 <= iy < h and grid[iy, ix] == WATER)
        if self.is_zombie:
            walk_interval = 7
        elif self.on_fire:
            walk_interval = 3
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

            # --- money happy hop ---
            if self.money_happy:
                if time.time() - self.money_happy_start >= 2.0:
                    self.money_happy = False
                else:
                    self.vy = -2.0
                    self.gy -= 0.5
                    self.grounded = False
                    return  # skip walking

            # --- collecting money: stand still ---
            if self.collecting_money:
                return  # stay put while picking up money

            # --- walking ---
            # Zombies chase nearest living gnome
            if self.is_zombie and self.zombie_target is not None:
                tgt = self.zombie_target
                if tgt.alive and not tgt.is_zombie:
                    self.dir = 1 if tgt.gx > self.gx else -1
                else:
                    self.zombie_target = None

            # Non-zombie gnomes chase money
            if not self.is_zombie and self.money_target is not None:
                mx, my = self.money_target
                if 0 <= mx < w and 0 <= my < h and grid[my, mx] == MONEY:
                    dist = math.hypot(mx - ix, my - iy)
                    if dist < 3:
                        # Close enough — start collecting
                        self.collecting_money = True
                        self.collect_start = time.time()
                    else:
                        self.dir = 1 if mx > self.gx else -1
                else:
                    # Money gone — clear target
                    self.money_target = None

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

            # Deploy parachute after 1.25s of falling (if still available)
            # Don't deploy while doing a confetti celebration hop
            fall_dur = time.time() - self.fall_start
            if fall_dur >= 1.25 and self.has_parachute and not self.parachute_open and not self.celebrating and not self.is_zombie:
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
                    # Hard landing death — fell 1.4s+ without parachute
                    if (self.fall_start > 0
                            and not self.parachute_open
                            and time.time() - self.fall_start >= 1.4):
                        self.alive = False
                        return
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
# Spark — short-lived visual particle from explosions
# ────────────────────────────────────────────

_SPARK_COLORS = [
    (255, 255, 100), (255, 220, 50), (255, 180, 30),
    (255, 150, 0), (255, 255, 200), (255, 200, 80),
]

class _Spark:
    """A tiny spark that flies outward from an explosion.
    Dies instantly on touching anything or leaving bounds."""

    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(2.0, 8.0)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed - random.uniform(1.0, 3.0)  # bias upward
        self.color = random.choice(_SPARK_COLORS)
        self.alive = True
        self.life = 0

    def step(self, grid):
        h, w = grid.shape
        self.vy += 0.25  # lighter gravity than gibs
        self.x += self.vx
        self.y += self.vy
        self.life += 1
        ix, iy = int(self.x), int(self.y)
        # Die if out of bounds
        if ix < 0 or ix >= w or iy < 0 or iy >= h:
            self.alive = False
            return
        # Die if touching anything solid (TUNNEL is open space)
        if grid[iy, ix] != EMPTY and grid[iy, ix] != TUNNEL:
            self.alive = False
            return
        # Die after 40 frames max (~1s)
        if self.life > 40:
            self.alive = False


# ────────────────────────────────────────────
# SplashDrop — water droplet flung upward by an impact
# ────────────────────────────────────────────

_SPLASH_COLORS = [
    (100, 160, 255), (120, 180, 255), (80, 140, 240),
    (150, 200, 255), (200, 230, 255),
]

class _SplashDrop:
    """A droplet of water ejected by a splash.  Arcs upward then falls
    back down, re-inserting itself as a water particle when it lands."""

    def __init__(self, x, y, fluid_type=WATER, fluid_color=None):
        self.x = float(x)
        self.y = float(y)
        angle = random.uniform(math.pi * 0.15, math.pi * 0.85)  # upward arc
        speed = random.uniform(2.0, 5.0)
        self.vx = math.cos(angle) * speed * random.choice([-1, 1])
        self.vy = -math.sin(angle) * speed  # upward
        self.color = random.choice(_SPLASH_COLORS)
        self.fluid_type = fluid_type
        self.fluid_color = fluid_color if fluid_color is not None else self.color
        self.alive = True
        self.life = 0

    def step(self, grid, colors):
        h, w = grid.shape
        self.vy += 0.3  # gravity
        self.x += self.vx
        self.y += self.vy
        self.life += 1
        ix, iy = int(self.x), int(self.y)

        # Out of bounds — die without placing
        if ix < 0 or ix >= w or iy >= h:
            self.alive = False
            return
        if iy < 0:
            return  # still rising above screen, keep going

        # Falling and hit something? Place water on top
        if self.vy > 0 and grid[iy, ix] != EMPTY:
            # Find the empty cell right above
            place_y = iy - 1
            if 0 <= place_y < h and grid[place_y, ix] == EMPTY:
                grid[place_y, ix] = self.fluid_type
                colors[place_y, ix] = self.fluid_color
            self.alive = False
            return

        # Die after 60 frames (~1.7s) — place water at current spot
        if self.life > 60:
            if 0 <= iy < h and 0 <= ix < w and grid[iy, ix] == EMPTY:
                grid[iy, ix] = self.fluid_type
                colors[iy, ix] = self.fluid_color
            self.alive = False


# ────────────────────────────────────────────
# Worm — burrows through dirt, leaving tunnels
# ────────────────────────────────────────────

_WORM_COLORS = [(200, 120, 150), (180, 100, 130), (220, 140, 160), (190, 110, 140)]
_TUNNEL_COLOR = (30, 20, 15)   # dark background for tunnels

class _Worm:
    """A worm that moves through dirt, eating it and leaving TUNNEL cells behind.
    Moves 3 cells per sim tick in a wandering direction, carving 3×3 tunnels."""

    def __init__(self, gx, gy):
        self.gx = gx
        self.gy = gy
        # Pick a random direction (one of 8 neighbours)
        angle = random.uniform(0, 2 * math.pi)
        self.dx = math.cos(angle)
        self.dy = math.sin(angle)
        self.color = random.choice(_WORM_COLORS)
        self.alive = True
        self.life = 0
        self.max_life = random.randint(80, 200)  # how far it burrows
        # Body trail for drawing (list of recent (gx,gy) positions)
        self._trail = []
        self._trail_max = 7

    def _carve(self, grid, colors, cx, cy):
        """Carve a 3×3 area of dirt into tunnel around (cx, cy)."""
        h, w = grid.shape
        for ddx in range(-1, 2):
            for ddy in range(-1, 2):
                tx, ty = cx + ddx, cy + ddy
                if 0 <= tx < w and 0 <= ty < h and grid[ty, tx] == DIRT:
                    grid[ty, tx] = TUNNEL
                    colors[ty, tx] = _TUNNEL_COLOR

    def _can_move(self, grid, nx, ny):
        """Check if center (nx, ny) has at least some dirt in 3×3 area."""
        h, w = grid.shape
        if nx < 0 or nx >= w or ny < 0 or ny >= h:
            return False
        # Need at least 1 dirt cell in the 3×3 to keep digging
        for ddx in range(-1, 2):
            for ddy in range(-1, 2):
                tx, ty = nx + ddx, ny + ddy
                if 0 <= tx < w and 0 <= ty < h and grid[ty, tx] == DIRT:
                    return True
        return False

    def step(self, grid, colors):
        h, w = grid.shape
        self.life += 1
        if self.life > self.max_life:
            self.alive = False
            return

        # 3 moves per tick for faster burrowing
        for _ in range(3):
            # Add wobble to direction
            self.dx += random.uniform(-0.4, 0.4)
            self.dy += random.uniform(-0.4, 0.4)
            # Normalize
            mag = math.sqrt(self.dx * self.dx + self.dy * self.dy)
            if mag > 0:
                self.dx /= mag
                self.dy /= mag

            # Try primary direction
            nx = self.gx + int(round(self.dx))
            ny = self.gy + int(round(self.dy))

            if self._can_move(grid, nx, ny):
                self._trail.append((self.gx, self.gy))
                if len(self._trail) > self._trail_max:
                    self._trail.pop(0)
                self._carve(grid, colors, self.gx, self.gy)
                self.gx = nx
                self.gy = ny
            else:
                # Try random adjacent cells
                neighbors = []
                for ddx in range(-1, 2):
                    for ddy in range(-1, 2):
                        if ddx == 0 and ddy == 0:
                            continue
                        cx, cy = self.gx + ddx, self.gy + ddy
                        if self._can_move(grid, cx, cy):
                            neighbors.append((cx, cy, ddx, ddy))
                if neighbors:
                    cx, cy, ddx, ddy = random.choice(neighbors)
                    self._trail.append((self.gx, self.gy))
                    if len(self._trail) > self._trail_max:
                        self._trail.pop(0)
                    self._carve(grid, colors, self.gx, self.gy)
                    self.gx = cx
                    self.gy = cy
                    self.dx = ddx * 0.7 + self.dx * 0.3
                    self.dy = ddy * 0.7 + self.dy * 0.3
                else:
                    self.alive = False
                    return
        # Carve at final position too
        self._carve(grid, colors, self.gx, self.gy)

    def draw(self, surface):
        """Draw the worm body as a short chain of circles."""
        # Trail segments (body)
        for i, (tx, ty) in enumerate(self._trail):
            sx = tx * _CELL + _CELL // 2
            sy = ty * _CELL + _CELL // 2
            r = max(3, _CELL - 1)
            # Fade body segments
            frac = (i + 1) / (len(self._trail) + 1)
            bc = tuple(int(ch * frac * 0.7) for ch in self.color)
            pygame.draw.circle(surface, bc, (sx, sy), r)
        # Head
        sx = self.gx * _CELL + _CELL // 2
        sy = self.gy * _CELL + _CELL // 2
        r = max(4, _CELL)
        pygame.draw.circle(surface, self.color, (sx, sy), r)


# ────────────────────────────────────────────
# Bomb — pixelated TNT with 2-second fuse
# ────────────────────────────────────────────

_BOMB_RADIUS = 28   # explosion radius in grid cells
_BOMB_FUSE = 2.0    # seconds before detonation

class _Bomb:
    """A pixelated bomb that falls with gravity and explodes after 2 seconds.
    is_fire: if True, this is a firebomb that sprays napalm."""

    def __init__(self, gx, gy, is_fire=False):
        self.x = float(gx)
        self.y = float(gy)
        self.vx = 0.0
        self.vy = 0.0
        self.spawn_time = time.time()
        self.alive = True
        self.exploded = False
        self.is_fire = is_fire  # firebomb variant
        self.landed = False  # True once bomb touches ground — stays put

    def step(self, grid):
        h, w = grid.shape

        # Check if on ground right now
        ix_c = int(self.x)
        iy_c = int(self.y)
        below = iy_c + 1
        on_ground = (below >= h or
                     (0 <= ix_c < w and 0 <= below < h and grid[below, ix_c] != EMPTY))

        if self.landed:
            # Check if we should start rolling (slope beneath us)
            if on_ground and 0 <= ix_c < w and below < h:
                left_empty = (ix_c - 1 >= 0
                              and grid[below, ix_c - 1] == EMPTY
                              and (iy_c < 0 or iy_c >= h or grid[iy_c, ix_c - 1] == EMPTY))
                right_empty = (ix_c + 1 < w
                               and grid[below, ix_c + 1] == EMPTY
                               and (iy_c < 0 or iy_c >= h or grid[iy_c, ix_c + 1] == EMPTY))
                if left_empty or right_empty:
                    # Slope detected — un-land and start rolling
                    self.landed = False
                    if left_empty and not right_empty:
                        self.vx = -0.5
                    elif right_empty and not left_empty:
                        self.vx = 0.5
                    else:
                        self.vx = random.choice([-0.5, 0.5])
                    self.vy = 0.3
            elif not on_ground:
                # Ground disappeared (e.g., exploded away) — un-land
                self.landed = False
                self.vy = 0.0

            if self.landed:
                # Still landed — just check fuse
                if time.time() - self.spawn_time >= _BOMB_FUSE:
                    self.exploded = True
                    self.alive = False
                return

        # Airborne / rolling: apply gravity
        self.vy += 0.55

        if on_ground:
            self.vx *= 0.80  # ground friction
        else:
            self.vx *= 0.99  # air resistance

        # Clamp velocity — high enough for fast falls, scan row-by-row
        max_vy = 4.0
        max_vx = 2.5
        if self.vy > max_vy:
            self.vy = max_vy
        if self.vy < -max_vy:
            self.vy = -max_vy
        if self.vx > max_vx:
            self.vx = max_vx
        if self.vx < -max_vx:
            self.vx = -max_vx

        # Move X
        new_x = self.x + self.vx
        ix_new = int(new_x)
        iy_cur = int(self.y)
        if ix_new < 0 or ix_new >= w:
            self.vx = -self.vx * 0.4
            new_x = max(0.0, min(float(w - 1), self.x))
        elif 0 <= iy_cur < h and grid[iy_cur, ix_new] != EMPTY:
            if iy_cur - 1 >= 0 and grid[iy_cur - 1, ix_new] == EMPTY:
                self.y -= 1.0
            else:
                self.vx = -self.vx * 0.3
                new_x = self.x
        self.x = new_x

        # Move Y — scan each row to land properly
        new_y = self.y + self.vy
        ix2 = int(self.x)
        iy_from = int(self.y)
        if 0 <= ix2 < w:
            if self.vy > 0:
                iy_to = int(new_y)
                for check_y in range(max(0, iy_from + 1), min(h, iy_to + 1)):
                    if grid[check_y, ix2] != EMPTY:
                        new_y = float(check_y - 1)
                        self.vy = 0.0
                        self.vx = 0.0
                        self.landed = True
                        break
                else:
                    if iy_to >= h:
                        new_y = float(h - 1)
                        self.vy = 0.0
                        self.vx = 0.0
                        self.landed = True
            elif self.vy < 0:
                check_row = int(new_y)
                if check_row < 0:
                    new_y = 0.0
                    self.vy = 0.0
                elif 0 <= check_row < h and grid[check_row, ix2] != EMPTY:
                    self.vy = 0.0
                    new_y = self.y
        else:
            if new_y >= h:
                new_y = float(h - 1)
                self.vy = 0.0
                self.vx = 0.0
                self.landed = True

        # Safety: if inside a solid, push up
        fy = int(new_y)
        if 0 <= ix2 < w and 0 <= fy < h and grid[fy, ix2] != EMPTY:
            while fy > 0 and grid[fy, ix2] != EMPTY:
                fy -= 1
            new_y = float(fy)
            self.vy = 0.0
            self.vx = 0.0
            self.landed = True

        self.y = new_y

        # Clamp
        if self.x < 0:
            self.x = 0.0
        if self.x >= w:
            self.x = float(w - 1)

        # Check fuse
        if time.time() - self.spawn_time >= _BOMB_FUSE:
            self.exploded = True
            self.alive = False

    def draw(self, surface, font=None):
        """Draw a pixelated bomb sprite."""
        cx = int(self.x * _CELL + _CELL // 2)
        cy = int(self.y * _CELL + _CELL // 2)
        remaining = _BOMB_FUSE - (time.time() - self.spawn_time)
        # Body
        if self.is_fire:
            body_c = (120, 30, 0)
            highlight_c = (180, 60, 10)
        else:
            body_c = (30, 30, 30)
            highlight_c = (60, 60, 60)
        pygame.draw.circle(surface, body_c, (cx, cy), 10)
        pygame.draw.circle(surface, highlight_c, (cx - 2, cy - 2), 4)
        # Fuse line
        pygame.draw.line(surface, (140, 100, 40), (cx + 6, cy - 8), (cx + 12, cy - 16), 2)
        # Fuse spark — flash faster as time runs out
        flash_rate = max(0.1, remaining / _BOMB_FUSE) * 0.4
        if (time.time() % flash_rate) < flash_rate / 2:
            spark_c = (255, 100, 0) if self.is_fire else (255, 255, 50)
            pygame.draw.circle(surface, spark_c, (cx + 12, cy - 16), 3)
            pygame.draw.circle(surface, (255, 200, 0), (cx + 12, cy - 16), 5, 1)
        # Timer text
        if remaining > 0 and font:
            timer_c = (255, 50, 50) if remaining < 1.5 else (255, 200, 50)
            txt = font.render(f"{remaining:.1f}", True, timer_c)
            surface.blit(txt, (cx - 12, cy + 12))


def _explode_bomb(state, bx, by, gnomes, gibs, sparks, is_fire=False):
    """Explosion: destroys everything in a circle, leaves stable cavity.
    is_fire: if True, fills the blast area with napalm instead of just clearing."""
    g = state.grid
    c = state.colors
    h, w = g.shape
    cx, cy = int(bx), int(by)
    radius = _BOMB_RADIUS

    # Destroy everything inside the blast radius — leave TUNNEL so dirt
    # above the crater doesn't collapse (TUNNEL blocks dirt but looks empty)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            dist = math.hypot(dx, dy)
            if dist > radius:
                continue
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                cell = g[ny, nx]
                if cell == EMPTY or cell == TUNNEL:
                    g[ny, nx] = TUNNEL
                    c[ny, nx] = (0, 0, 0)
                    continue
                # Leave fire and napalm alone — bombs don't extinguish flames
                if cell == FIRE or cell == NAPALM:
                    continue
                # Chain-react gunpowder — just light it, fuse will burn slowly
                if cell == GUNPOWDER:
                    g[ny, nx] = FIRE
                    c[ny, nx] = random.choice(_FIRE_COLORS)
                    continue
                # Clear the cell into stable tunnel
                g[ny, nx] = TUNNEL
                c[ny, nx] = (0, 0, 0)

    # Ring of fire at the blast edge — looks like the shockwave scorched it
    for dy in range(-radius - 2, radius + 3):
        for dx in range(-radius - 2, radius + 3):
            dist = math.hypot(dx, dy)
            if radius - 2 < dist < radius + 2:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h:
                    cell = g[ny, nx]
                    if cell in (WOOD, PLANT, DIRT, HEAVY, STATIC):
                        if random.random() < 0.5:
                            g[ny, nx] = FIRE
                            c[ny, nx] = random.choice(_FIRE_COLORS)

    # Fill blast area: firebomb sprays napalm, regular bomb just clears
    if is_fire:
        # Napalm fills most of the blast
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if math.hypot(dx, dy) > radius * 0.8:
                    continue
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h and g[ny, nx] == TUNNEL:
                    g[ny, nx] = NAPALM
                    c[ny, nx] = random.choice(_NAPALM_COLORS)

    # Big shower of sparks — radial burst
    for _ in range(random.randint(120, 180)):
        sparks.append(_Spark(cx, cy))

    # Kill gnomes in blast radius — gibs fly out
    for gnome in gnomes:
        if not gnome.alive:
            continue
        dist = math.hypot(gnome.gx - cx, gnome.gy - cy)
        if dist < radius * 1.2:
            gnome.alive = False
            for _ in range(random.randint(8, 15)):
                gb = _Gib(int(gnome.gx), int(gnome.gy), gnome.color)
                angle = math.atan2(gnome.gy - cy, gnome.gx - cx)
                speed = random.uniform(3.0, 7.0)
                gb.vx = math.cos(angle) * speed + random.uniform(-1.5, 1.5)
                gb.vy = math.sin(angle) * speed + random.uniform(-4.0, -1.0)
                gibs.append(gb)


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
        # Fire age tracker — ticks since ignition (uint8 caps at 255, plenty)
        self.fire_age = np.zeros((h, w), dtype=np.uint8)

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
        self.fire_age[:] = 0

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


def _step(state, wind_active=False, wind_dir=1, reverse_gravity=False, splash_drops=None, vine_tips=None):
    """Vectorized physics step using numpy."""
    g = state.grid
    c = state.colors
    h, w = g.shape

    # Find all falling particles: sand, gasoline, water, confetti, poison, holy water, money, dirt, seed
    # (GUNPOWDER is static — painted like a fuse line, does not fall)
    falling = (g == HEAVY) | (g == GASOLINE) | (g == WATER) | (g == CONFETTI) | (g == POISON) | (g == HOLYWATER) | (g == MONEY) | (g == DIRT) | (g == SEED)
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
        if ptype not in (HEAVY, GASOLINE, WATER, CONFETTI, POISON, HOLYWATER, MONEY, DIRT, SEED):
            continue  # already moved by another particle this step
        col = c[y, x].copy()

        # Gasoline and water are more fluid — higher lateral slide chance
        # Confetti and money flutter — very high lateral drift
        if ptype in (CONFETTI, MONEY):
            slide_chance = 0.85
        elif ptype in (GASOLINE, WATER, POISON, HOLYWATER):
            slide_chance = 0.7
        else:
            slide_chance = 0.3

        ny = y + grav
        moved = False
        _fluids_for_splash = {WATER, GASOLINE, POISON, HOLYWATER}

        # Dirt cannot fall into TUNNEL cells (tunnels hold their shape);
        # everything else treats TUNNEL as open space.
        def _is_open(cy, cx):
            """Return True if cell (cy,cx) is open space this particle can move into."""
            cell = g[cy, cx]
            if cell == EMPTY:
                return True
            if cell == TUNNEL and ptype != DIRT:
                return True
            return False

        # Confetti/money flutters — 50% chance to skip falling, just drift sideways
        if ptype in (CONFETTI, MONEY) and random.random() < 0.5:
            lx = x + (1 if random.random() < 0.5 else -1)
            if 0 <= lx < w and _is_open(y, lx):
                g[y, x] = EMPTY
                g[y, lx] = ptype
                c[y, lx] = col
            continue

        # Try straight down
        if 0 <= ny < h and _is_open(ny, x):
            g[y, x] = EMPTY
            g[ny, x] = ptype
            c[ny, x] = col
            y = ny
            moved = True
        elif (0 <= ny < h and g[ny, x] in _fluids_for_splash
              and ptype not in _fluids_for_splash):
            # ── Splash! Non-fluid particle falls into fluid ──
            fluid_t = g[ny, x]
            fluid_c = c[ny, x].copy()
            # Swap: particle sinks, fluid goes up
            g[ny, x] = ptype
            c[ny, x] = col
            g[y, x] = fluid_t
            c[y, x] = fluid_c
            y = ny
            moved = True

            # Eject nearby surface fluid cells as splash drops
            if splash_drops is not None:
                n_drops = random.randint(3, 7)
                for dx in range(-3, 4):
                    if n_drops <= 0:
                        break
                    sx = x + dx
                    if sx < 0 or sx >= w:
                        continue
                    # Find topmost fluid cell in this column near impact
                    for sy in range(max(0, ny - 6), ny + 1):
                        if g[sy, sx] in _fluids_for_splash:
                            ft = g[sy, sx]
                            fc = c[sy, sx].copy()
                            g[sy, sx] = EMPTY
                            c[sy, sx] = (0, 0, 0)
                            splash_drops.append(
                                _SplashDrop(sx, sy, ft, fc))
                            n_drops -= 1
                            break
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
                if 0 <= tx < w and 0 <= ty < h and _is_open(ty, tx):
                    g[y, x] = EMPTY
                    g[ty, tx] = ptype
                    c[ty, tx] = col
                    x, y = tx, ty
                    moved = True
                    break

        is_fluid = ptype in (GASOLINE, WATER, POISON, HOLYWATER)

        # Fluids: try to slide sideways when blocked (just 1 cell, keep it simple)
        if not moved and is_fluid:
            direction = 1 if random.random() < 0.5 else -1
            lx = x + direction
            if 0 <= lx < w and _is_open(y, lx):
                g[y, x] = EMPTY
                g[y, lx] = ptype
                c[y, lx] = col
                x = lx
                moved = True
            else:
                lx = x - direction
                if 0 <= lx < w and _is_open(y, lx):
                    g[y, x] = EMPTY
                    g[y, lx] = ptype
                    c[y, lx] = col
                    x = lx
                    moved = True
        elif not moved:
            # Non-fluid: only try lateral if didn't move at all
            if random.random() < slide_chance:
                lx = x + (1 if random.random() < 0.5 else -1)
                if 0 <= lx < w and _is_open(y, lx):
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

    # ── Seed sprouting ───────────────────────────────────────────
    # Seeds touching water convert to PLANT and spawn vine tips
    # that grow gradually (1 cell per tick).
    _water_set = {WATER, HOLYWATER}
    seed_ys, seed_xs = np.where(g == SEED)
    for si in range(len(seed_ys)):
        sy, sx = int(seed_ys[si]), int(seed_xs[si])
        if g[sy, sx] != SEED:
            continue
        # Check all 8 neighbors for water
        touching_water = False
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny2, nx2 = sy + dy, sx + dx
                if 0 <= ny2 < h and 0 <= nx2 < w and g[ny2, nx2] in _water_set:
                    touching_water = True
                    break
            if touching_water:
                break
        if not touching_water:
            continue

        # Sprout! Convert seed to plant and create 6 vine tips
        g[sy, sx] = PLANT
        c[sy, sx] = random.choice(_PLANT_COLORS)
        if vine_tips is not None:
            for _ in range(6):
                angle = random.uniform(0, 2 * math.pi)
                length = random.randint(12, 25)
                vine_tips.append({
                    'x': float(sx), 'y': float(sy),
                    'dx': math.cos(angle), 'dy': math.sin(angle),
                    'remaining': length,
                })

    # ── Vine growth (gradual) ──────────────────────────────────
    # Each vine tip extends by 1 cell every ~16 ticks (slow growth).
    if vine_tips is not None:
        still_growing = []
        for tip in vine_tips:
            if random.random() < 0.9375:
                # Skip this tick — slows growth to ~1 cell per 16 ticks
                still_growing.append(tip)
                continue
            tip['x'] += tip['dx'] + random.uniform(-0.3, 0.3)
            tip['y'] += tip['dy'] + random.uniform(-0.3, 0.3)
            tip['remaining'] -= 1
            vix = int(round(tip['x']))
            viy = int(round(tip['y']))
            if vix < 0 or vix >= w or viy < 0 or viy >= h:
                continue  # out of bounds — die
            cell = g[viy, vix]
            if cell == EMPTY or cell in _water_set:
                g[viy, vix] = PLANT
                c[viy, vix] = random.choice(_PLANT_COLORS)
            elif cell == PLANT:
                pass  # already plant, keep going through
            else:
                continue  # hit solid — die
            if tip['remaining'] > 0:
                still_growing.append(tip)
        vine_tips.clear()
        vine_tips.extend(still_growing)

    # ── Fluid leveling pass ─────────────────────────────────────
    # Run several passes bottom-to-top.  For each fluid cell that
    # has a solid or fluid below it (settled), try to flow sideways
    # into any adjacent empty cell that also has support below it,
    # OR into an adjacent empty cell with nothing below (waterfall).
    # This is the "cellular automaton" approach — simple and fast.
    _fluids_set = {WATER, GASOLINE, POISON, HOLYWATER}

    _open_set = {EMPTY, TUNNEL}   # cells that fluid can flow into

    for _pass in range(4):
        for y in range(h - 1, -1, -1):
            # Alternate left-to-right vs right-to-left each pass
            if _pass % 2 == 0:
                col_range = range(w)
            else:
                col_range = range(w - 1, -1, -1)

            for x in col_range:
                if g[y, x] not in _fluids_set:
                    continue

                # Already falling? Skip — gravity handles it
                below = y + 1
                if below < h and g[below, x] in _open_set:
                    continue

                # Only flow sideways if under pressure (fluid above)
                # or if the neighbor empty cell leads to a drop.
                # This prevents surface particles from jiggling.
                has_pressure = (y > 0 and g[y - 1, x] in _fluids_set)

                d = 1 if random.random() < 0.5 else -1
                for direction in (d, -d):
                    nx = x + direction
                    if nx < 0 or nx >= w:
                        continue
                    if g[y, nx] not in _open_set:
                        continue

                    # Check if the target cell leads to a drop
                    # (empty below target = waterfall)
                    target_below = y + 1
                    drops = (target_below < h and g[target_below, nx] in _open_set)

                    if not has_pressure and not drops:
                        # Surface particle with nowhere to fall —
                        # only move if it actually levels the column.
                        # Count fluid height at current x vs neighbor.
                        cur_h = 0
                        sy = y
                        while sy >= 0 and g[sy, x] in _fluids_set:
                            cur_h += 1
                            sy -= 1
                        # Neighbor height
                        nb_h = 0
                        sy = y
                        while sy >= 0 and g[sy, nx] in _fluids_set:
                            nb_h += 1
                            sy -= 1
                        if cur_h - nb_h < 2:
                            continue  # already level, don't jiggle

                    pt = g[y, x]
                    cl = c[y, x]
                    g[y, x] = EMPTY
                    g[y, nx] = pt
                    c[y, nx] = cl
                    break


def _step_fire(state):
    """Physics step for fire particles: rise upward, spread, consume."""
    _FIRE_MAX_AGE = 54    # ~1.5 seconds at 36 fps
    _FIRE_MAX_AGE_PLANT = 144  # ~4 seconds — fire on burning plants lingers
    g = state.grid
    c = state.colors
    fa = state.fire_age
    h, w = g.shape

    fire = (g == FIRE)
    if not np.any(fire):
        return

    # Bulk-age all fire cells by 1 tick
    fa[fire] = np.minimum(fa[fire].astype(np.uint16) + 1, 255).astype(np.uint8)

    # Kill any fire that's exceeded the longest possible max age
    old_fire = fire & (fa >= _FIRE_MAX_AGE_PLANT)
    g[old_fire] = EMPTY
    fa[old_fire] = 0

    # Re-find living fire
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
                    # Fire + water = steam (both cells)
                    g[ny2, nx] = STEAM
                    c[ny2, nx] = random.choice(_STEAM_COLORS)
                    g[y, x] = STEAM
                    c[y, x] = random.choice(_STEAM_COLORS)
                    fa[y, x] = 0
                    extinguished = True
                    break
                elif cell == ICE:
                    # Fire melts ice into water
                    g[ny2, nx] = WATER
                    c[ny2, nx] = random.choice(_WATER_COLORS)
                    g[y, x] = EMPTY
                    fa[y, x] = 0
                    extinguished = True
                    break
                elif cell == WOOD:
                    if random.random() < 0.018:      # wood burns moderate
                        g[ny2, nx] = FIRE
                        c[ny2, nx] = random.choice(_FIRE_COLORS)
                elif cell == PLANT:
                    if random.random() < 0.15:       # plants burn aggressively
                        g[ny2, nx] = FIRE
                        c[ny2, nx] = random.choice(_FIRE_COLORS)
                elif cell == DIRT:
                    if random.random() < 0.025:      # dirt burns faster than wood
                        g[ny2, nx] = FIRE
                        c[ny2, nx] = random.choice(_FIRE_COLORS)
                elif cell == HEAVY:
                    if random.random() < 0.08:       # fire + sand = glass
                        g[ny2, nx] = GLASS
                        c[ny2, nx] = random.choice(_GLASS_COLORS)
                elif cell == STATIC:
                    if random.random() < 0.009:      # wall burns slow
                        g[ny2, nx] = FIRE
                        c[ny2, nx] = random.choice(_FIRE_COLORS)
                elif cell == GUNPOWDER:
                    # Fuse: slowly ignite adjacent gunpowder (burns cell by cell)
                    if random.random() < 0.12:
                        g[ny2, nx] = FIRE
                        c[ny2, nx] = random.choice(_FIRE_COLORS)
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
            fa[ny, x] = fa[y, x]
            fa[y, x] = 0
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
                    fa[ty, tx] = fa[y, x]
                    fa[y, x] = 0
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
                    fa[y, lx] = fa[y, x]
                    fa[y, x] = 0
                    g[y, x] = EMPTY
                    g[y, lx] = FIRE
                    c[y, lx] = col
                    moved = True

        # Fire has a chance to die out — ramps up aggressively with age
        # Fire adjacent to plant uses a much longer lifetime (burns slowly)
        age = fa[y, x]
        near_plant = False
        for dx2, dy2 in ((-1,0),(1,0),(0,-1),(0,1)):
            nx2, ny2 = x + dx2, y + dy2
            if 0 <= nx2 < w and 0 <= ny2 < h and g[ny2, nx2] == PLANT:
                near_plant = True
                break
        max_age = _FIRE_MAX_AGE_PLANT if near_plant else _FIRE_MAX_AGE
        die_chance = 0.08 + (age / max_age) * 0.80
        if random.random() < die_chance:
            g[y, x] = EMPTY
            fa[y, x] = 0


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
                elif cell == ICE:
                    # Napalm melts ice into water
                    g[ny2, nx] = WATER
                    c[ny2, nx] = random.choice(_WATER_COLORS)
                    g[y, x] = EMPTY
                    extinguished = True
                    break
                elif cell == WOOD:
                    if random.random() < 0.018:
                        g[ny2, nx] = FIRE
                        c[ny2, nx] = random.choice(_FIRE_COLORS)
                elif cell == PLANT:
                    if random.random() < 0.15:
                        g[ny2, nx] = FIRE
                        c[ny2, nx] = random.choice(_FIRE_COLORS)
                elif cell == DIRT:
                    if random.random() < 0.025:
                        g[ny2, nx] = FIRE
                        c[ny2, nx] = random.choice(_FIRE_COLORS)
                elif cell == HEAVY or cell == STATIC:
                    if random.random() < 0.009:
                        g[ny2, nx] = FIRE
                        c[ny2, nx] = random.choice(_FIRE_COLORS)
                elif cell == GUNPOWDER:
                    # Fuse: slowly ignite adjacent gunpowder
                    if random.random() < 0.12:
                        g[ny2, nx] = FIRE
                        c[ny2, nx] = random.choice(_FIRE_COLORS)
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

        # Napalm lasts much longer than fire (very low die-out chance)
        if random.random() < 0.001:
            g[y, x] = EMPTY


def _step_magma(state):
    """Physics step for magma: like napalm but RESISTANT to water.
    Requires 3+ adjacent water cells to be extinguished."""
    g = state.grid
    c = state.colors
    h, w = g.shape

    mag = (g == MAGMA)
    if not np.any(mag):
        return

    ys, xs = np.where(mag)
    order = np.arange(len(ys))
    np.random.shuffle(order)
    ys = ys[order]
    xs = xs[order]

    ys, xs = _throttle(ys, xs)

    _magma_open = {EMPTY, TUNNEL}
    _magma_displace = {WATER, GASOLINE, POISON, HOLYWATER}

    for i in range(len(ys)):
        y, x = int(ys[i]), int(xs[i])
        if g[y, x] != MAGMA:
            continue
        col = tuple(random.choice(_MAGMA_COLORS))

        # Count adjacent water cells
        water_count = 0
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
            nx, ny2 = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny2 < h:
                if g[ny2, nx] == WATER:
                    water_count += 1

        extinguished = False
        if water_count >= 1:
            # Any water contact — magma hardens to concrete
            # Surrounding water also solidifies into concrete (thick formation)
            # with a few cells becoming steam for visual sizzle
            g[y, x] = CONCRETE
            c[y, x] = _CONCRETE_COLOR
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
                nx, ny2 = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny2 < h and g[ny2, nx] == WATER:
                    if random.random() < 0.7:
                        # Most water hardens to concrete
                        g[ny2, nx] = CONCRETE
                        c[ny2, nx] = _CONCRETE_COLOR
                    else:
                        # Some water sizzles to steam
                        g[ny2, nx] = STEAM
                        c[ny2, nx] = random.choice(_STEAM_COLORS)
                    # Also convert the ring around each water neighbor
                    for dx2, dy2 in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nx2, ny3 = nx + dx2, ny2 + dy2
                        if 0 <= nx2 < w and 0 <= ny3 < h and g[ny3, nx2] == WATER:
                            if random.random() < 0.5:
                                g[ny3, nx2] = CONCRETE
                                c[ny3, nx2] = _CONCRETE_COLOR
                            else:
                                g[ny3, nx2] = STEAM
                                c[ny3, nx2] = random.choice(_STEAM_COLORS)
            extinguished = True
        else:
            # Spread fire to neighbors (but IGNORE water — magma resists it)
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
                nx, ny2 = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny2 < h:
                    cell = g[ny2, nx]
                    if cell == ICE:
                        g[ny2, nx] = WATER
                        c[ny2, nx] = random.choice(_WATER_COLORS)
                    elif cell == WATER:
                        # Water sizzles into steam on contact with magma
                        if random.random() < 0.15:
                            g[ny2, nx] = STEAM
                            c[ny2, nx] = random.choice(_STEAM_COLORS)
                    elif cell == WOOD:
                        if random.random() < 0.018:
                            g[ny2, nx] = FIRE
                            c[ny2, nx] = random.choice(_FIRE_COLORS)
                    elif cell == PLANT:
                        if random.random() < 0.15:
                            g[ny2, nx] = FIRE
                            c[ny2, nx] = random.choice(_FIRE_COLORS)
                    elif cell == DIRT:
                        if random.random() < 0.025:
                            g[ny2, nx] = FIRE
                            c[ny2, nx] = random.choice(_FIRE_COLORS)
                    elif cell == HEAVY:
                        if random.random() < 0.08:       # magma + sand = glass
                            g[ny2, nx] = GLASS
                            c[ny2, nx] = random.choice(_GLASS_COLORS)
                    elif cell == STATIC:
                        if random.random() < 0.009:
                            g[ny2, nx] = FIRE
                            c[ny2, nx] = random.choice(_FIRE_COLORS)
                    elif cell == GUNPOWDER:
                        # Fuse: slowly ignite adjacent gunpowder
                        if random.random() < 0.12:
                            g[ny2, nx] = FIRE
                            c[ny2, nx] = random.choice(_FIRE_COLORS)
                    elif cell == GASOLINE:
                        g[ny2, nx] = FIRE
                        c[ny2, nx] = random.choice(_FIRE_COLORS)

        if extinguished:
            continue

        # ── Magma FALLS like a thick fluid ──
        ny = y + 1
        moved = False

        if 0 <= ny < h:
            below = g[ny, x]
            if below in _magma_open:
                g[y, x] = EMPTY
                g[ny, x] = MAGMA
                c[ny, x] = col
                y = ny
                moved = True
            elif below in _magma_displace:
                # Magma sinks through lighter fluids (swap)
                fluid_t = g[ny, x]
                fluid_c = c[ny, x].copy()
                g[ny, x] = MAGMA
                c[ny, x] = col
                g[y, x] = fluid_t
                c[y, x] = fluid_c
                y = ny
                moved = True

        if not moved:
            # Try diagonal fall (random order)
            ny = y + 1
            if random.random() < 0.5:
                tries = [(x - 1, ny), (x + 1, ny)]
            else:
                tries = [(x + 1, ny), (x - 1, ny)]
            for tx, ty in tries:
                if 0 <= tx < w and 0 <= ty < h:
                    tcell = g[ty, tx]
                    if tcell in _magma_open:
                        g[y, x] = EMPTY
                        g[ty, tx] = MAGMA
                        c[ty, tx] = col
                        x, y = tx, ty
                        moved = True
                        break
                    elif tcell in _magma_displace:
                        fluid_t = g[ty, tx]
                        fluid_c = c[ty, tx].copy()
                        g[ty, tx] = MAGMA
                        c[ty, tx] = col
                        g[y, x] = fluid_t
                        c[y, x] = fluid_c
                        x, y = tx, ty
                        moved = True
                        break

        # Lateral slide — magma is a thick fluid so it spreads sideways
        if not moved:
            direction = 1 if random.random() < 0.5 else -1
            lx = x + direction
            if 0 <= lx < w and g[y, lx] in _magma_open:
                g[y, x] = EMPTY
                g[y, lx] = MAGMA
                c[y, lx] = col
                x = lx
                moved = True
            else:
                lx = x - direction
                if 0 <= lx < w and g[y, lx] in _magma_open:
                    g[y, x] = EMPTY
                    g[y, lx] = MAGMA
                    c[y, lx] = col
                    x = lx
                    moved = True

        # Magma lasts even longer than napalm (nearly permanent)
        if random.random() < 0.0003:
            g[y, x] = EMPTY

    # ── Magma leveling pass (thick fluid) ────────────────────────
    # Like water leveling but only 2 passes (viscous), so magma
    # pools and spreads outward when piled up.
    _magma_open_lev = {EMPTY, TUNNEL}
    for _pass in range(2):
        for y in range(h - 1, -1, -1):
            if _pass % 2 == 0:
                col_range = range(w)
            else:
                col_range = range(w - 1, -1, -1)

            for x in col_range:
                if g[y, x] != MAGMA:
                    continue

                # Skip if still falling (gravity handles it)
                below = y + 1
                if below < h and g[below, x] in _magma_open_lev:
                    continue

                # Only flow sideways if under pressure (magma above)
                has_pressure = (y > 0 and g[y - 1, x] == MAGMA)

                d = 1 if random.random() < 0.5 else -1
                for direction in (d, -d):
                    nx = x + direction
                    if nx < 0 or nx >= w:
                        continue
                    if g[y, nx] not in _magma_open_lev:
                        continue

                    target_below = y + 1
                    drops = (target_below < h and g[target_below, nx] in _magma_open_lev)

                    if not has_pressure and not drops:
                        # Surface magma — only move to level columns
                        cur_h = 0
                        sy = y
                        while sy >= 0 and g[sy, x] == MAGMA:
                            cur_h += 1
                            sy -= 1
                        nb_h = 0
                        sy = y
                        while sy >= 0 and g[sy, nx] == MAGMA:
                            nb_h += 1
                            sy -= 1
                        if cur_h - nb_h < 2:
                            continue

                    cl = c[y, x]
                    g[y, x] = EMPTY
                    g[y, nx] = MAGMA
                    c[y, nx] = cl
                    break


def _step_steam(state):
    """Physics step for steam: rises upward, drifts sideways, fades out."""
    g = state.grid
    c = state.colors
    h, w = g.shape

    stm = (g == STEAM)
    if not np.any(stm):
        return

    ys, xs = np.where(stm)
    order = np.arange(len(ys))
    np.random.shuffle(order)
    ys = ys[order]
    xs = xs[order]

    for i in range(len(ys)):
        y, x = int(ys[i]), int(xs[i])
        if g[y, x] != STEAM:
            continue
        col = tuple(random.choice(_STEAM_COLORS))

        # Rise upward
        ny = y - 1
        moved = False
        if 0 <= ny < h and g[ny, x] == EMPTY:
            g[y, x] = EMPTY
            g[ny, x] = STEAM
            c[ny, x] = col
            y = ny
            moved = True
        else:
            # Try diagonal up-left / up-right
            if random.random() < 0.5:
                tries = [(x - 1, ny), (x + 1, ny)]
            else:
                tries = [(x + 1, ny), (x - 1, ny)]
            for tx, ty in tries:
                if 0 <= tx < w and 0 <= ty < h and g[ty, tx] == EMPTY:
                    g[y, x] = EMPTY
                    g[ty, tx] = STEAM
                    c[ty, tx] = col
                    x, y = tx, ty
                    moved = True
                    break

        # Random lateral drift
        if not moved and random.random() < 0.4:
            lx = x + (1 if random.random() < 0.5 else -1)
            if 0 <= lx < w and g[y, lx] == EMPTY:
                g[y, x] = EMPTY
                g[y, lx] = STEAM
                c[y, lx] = col

        # Steam dissipates quickly
        if random.random() < 0.04:
            g[y, x] = EMPTY

        # Reached top of screen — disappear
        if y <= 0:
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
    MODE_ICE = 16
    MODE_BOMB = 17
    MODE_MONEY = 18
    MODE_FIREBOMB = 19
    MODE_DIRT = 20
    MODE_MATCH = 21
    MODE_MAGMA = 22
    MODE_SEED = 23
    MODE_WORM = 24
    MODE_GLASS = 25

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
        self._sim_speed = 2              # modulo for sim stepping: 1=fast, 2=normal, 4=slow
        self._last_tick = 0.0
        self._last_wall_gx = None
        self._last_wall_gy = None
        self._gnomes = []
        self._gibs = []
        self._sparks = []
        self._splash_drops = []
        self._vine_tips = []
        self._worms = []
        self._bombs = []
        self._bomb_font = pygame.font.Font(None, 20)
        self._poison_settle = {}        # (x,y) -> time when poison settled
        self._gnome_spawned_this_pinch = False
        self._fill_done_this_pinch = False
        self._held_gnome = None
        self._line_start_gx = None
        self._line_start_gy = None
        self._pixel_surf = pygame.Surface((self._gw, self._gh))
        self._scaled_surf = pygame.Surface((window_width, window_height))
        self._rgb_buf = np.zeros((self._gh, self._gw, 3), dtype=np.uint8)
        self._font_small = pygame.font.Font(None, 24)
        self._font_title = pygame.font.Font(None, 36)
        self._sim_tick = 0               # frame counter for sim stepping
        self._menu_open = False          # collapsible tool menu
        self._buttons = []
        self._menu_buttons = []          # buttons only visible when menu is open
        self._build_buttons()

    def _build_buttons(self):
        bw = 82
        bh = 40
        margin = 4

        # ── Menu toggle button — always visible, top-left ──
        self._btn_menu = _Button(margin, margin, 82, 40, "☰ SND", font_size=22,
                                 color=(60, 60, 80), active_color=(100, 200, 150))

        # ── Grid of tool buttons — shown only when menu is open ──
        # Layout: columns flowing left to right, rows top to bottom
        # Starting below the menu button
        panel_x = margin
        panel_y = margin + 44

        def _place(row, col):
            return (panel_x + col * (bw + margin),
                    panel_y + row * (bh + margin))

        # Row 0 — Materials
        r, c = 0, 0
        x, y = _place(r, c)
        self._btn_pour = _Button(x, y, bw, bh, "SAND", font_size=22); c += 1
        x, y = _place(r, c)
        self._btn_dirt = _Button(x, y, bw, bh, "DIRT", font_size=22,
                                 color=(60, 40, 20), active_color=(140, 90, 45)); c += 1
        x, y = _place(r, c)
        self._btn_water = _Button(x, y, bw, bh, "WATER", font_size=22,
                                  color=(15, 50, 120), active_color=(40, 130, 255)); c += 1
        x, y = _place(r, c)
        self._btn_wood = _Button(x, y, bw, bh, "WOOD", font_size=22,
                                 color=(70, 45, 20), active_color=(180, 120, 60)); c += 1
        x, y = _place(r, c)
        self._btn_concrete = _Button(x, y, bw, bh, "CONCRT", font_size=20,
                                     color=(60, 60, 65), active_color=(160, 160, 170)); c += 1
        x, y = _place(r, c)
        self._btn_ice = _Button(x, y, bw, bh, "ICE", font_size=22,
                                color=(60, 90, 120), active_color=(180, 220, 255)); c += 1

        # Row 1 — Fire / explosives
        r, c = 1, 0
        x, y = _place(r, c)
        self._btn_fire = _Button(x, y, bw, bh, "FIRE", font_size=22,
                                 color=(80, 30, 0), active_color=(255, 120, 0)); c += 1
        x, y = _place(r, c)
        self._btn_napalm = _Button(x, y, bw, bh, "NAPLM", font_size=20,
                                   color=(120, 30, 0), active_color=(255, 60, 0)); c += 1
        x, y = _place(r, c)
        self._btn_magma = _Button(x, y, bw, bh, "MAGMA", font_size=20,
                                  color=(120, 40, 0), active_color=(255, 100, 0)); c += 1
        x, y = _place(r, c)
        self._btn_gasoline = _Button(x, y, bw, bh, "GAS", font_size=22,
                                     color=(70, 80, 20), active_color=(200, 220, 60)); c += 1
        x, y = _place(r, c)
        self._btn_gunpowder = _Button(x, y, bw, bh, "GUNPW", font_size=20,
                                      color=(50, 50, 50), active_color=(120, 120, 120)); c += 1
        x, y = _place(r, c)
        self._btn_match = _Button(x, y, bw, bh, "MATCH", font_size=20,
                                  color=(100, 50, 10), active_color=(255, 140, 30)); c += 1

        # Row 2 — Special / creatures
        r, c = 2, 0
        x, y = _place(r, c)
        self._btn_gnome = _Button(x, y, bw, bh, "GNOME", font_size=22); c += 1
        x, y = _place(r, c)
        self._btn_confetti = _Button(x, y, bw, bh, "CONFTI", font_size=20,
                                     color=(100, 40, 100), active_color=(255, 100, 255)); c += 1
        x, y = _place(r, c)
        self._btn_poison = _Button(x, y, bw, bh, "ZOMBI", font_size=20,
                                   color=(20, 80, 10), active_color=(50, 200, 30)); c += 1
        x, y = _place(r, c)
        self._btn_holywater = _Button(x, y, bw, bh, "HOLY", font_size=22,
                                      color=(80, 80, 130), active_color=(200, 200, 255)); c += 1
        x, y = _place(r, c)
        self._btn_money = _Button(x, y, bw, bh, "MONEY", font_size=20,
                                  color=(20, 80, 20), active_color=(60, 200, 60)); c += 1
        x, y = _place(r, c)
        self._btn_bomb = _Button(x, y, bw, bh, "BOMB", font_size=22,
                                 color=(50, 50, 50), active_color=(255, 80, 0)); c += 1

        # Row 3 — Tools / actions
        r, c = 3, 0
        x, y = _place(r, c)
        self._btn_hand = _Button(x, y, bw, bh, "HAND", font_size=22,
                                 color=(80, 60, 40), active_color=(220, 180, 120)); c += 1
        x, y = _place(r, c)
        self._btn_erase = _Button(x, y, bw, bh, "ERASE", font_size=22); c += 1
        x, y = _place(r, c)
        self._btn_fill = _Button(x, y, bw, bh, "FILL", font_size=22,
                                 color=(50, 50, 80), active_color=(120, 180, 255)); c += 1
        x, y = _place(r, c)
        self._btn_firebomb = _Button(x, y, bw, bh, "FBOMB", font_size=20,
                                     color=(120, 30, 0), active_color=(255, 80, 0)); c += 1
        x, y = _place(r, c)
        self._btn_color = _Button(x, y, bw, bh, "COLOR", font_size=22); c += 1
        x, y = _place(r, c)
        self._btn_clear = _Button(x, y, bw, bh, "CLEAR", font_size=22); c += 1

        # Row 4 — Settings
        r, c = 4, 0
        x, y = _place(r, c)
        self._btn_wind = _Button(x, y, bw, bh, "WIND", font_size=22); c += 1
        x, y = _place(r, c)
        self._btn_wind_dir = _Button(x, y, bw, bh, "WIND>", font_size=20); c += 1
        x, y = _place(r, c)
        self._btn_gravity = _Button(x, y, bw, bh, "GRAV", font_size=22); c += 1
        x, y = _place(r, c)
        self._btn_slow = _Button(x, y, bw, bh, "SLOW", font_size=22,
                                 color=(30, 60, 100), active_color=(80, 160, 255)); c += 1
        x, y = _place(r, c)
        self._btn_fast = _Button(x, y, bw, bh, "FAST", font_size=22,
                                 color=(100, 60, 30), active_color=(255, 160, 80)); c += 1
        x, y = _place(r, c)
        self._btn_quit = _Button(x, y, bw, bh, "QUIT", font_size=22,
                                 color=(120, 30, 30), active_color=(255, 60, 60)); c += 1

        # Row 5 — Nature
        r, c = 5, 0
        x, y = _place(r, c)
        self._btn_seed = _Button(x, y, bw, bh, "SEED", font_size=22,
                                 color=(60, 40, 10), active_color=(140, 95, 30)); c += 1
        x, y = _place(r, c)
        self._btn_worm = _Button(x, y, bw, bh, "WORM", font_size=22,
                                 color=(120, 70, 90), active_color=(220, 140, 160)); c += 1
        x, y = _place(r, c)
        self._btn_glass = _Button(x, y, bw, bh, "GLASS", font_size=20,
                                  color=(80, 110, 130), active_color=(180, 220, 240)); c += 1

        # Menu buttons — only visible when menu is open
        self._menu_buttons = [
            self._btn_pour, self._btn_dirt, self._btn_water, self._btn_wood,
            self._btn_concrete, self._btn_ice,
            self._btn_fire, self._btn_napalm, self._btn_magma, self._btn_gasoline,
            self._btn_gunpowder, self._btn_match,
            self._btn_gnome, self._btn_confetti, self._btn_poison, self._btn_holywater,
            self._btn_money, self._btn_bomb,
            self._btn_hand, self._btn_erase, self._btn_fill, self._btn_firebomb,
            self._btn_color, self._btn_clear,
            self._btn_wind, self._btn_wind_dir, self._btn_gravity,
            self._btn_slow, self._btn_fast, self._btn_quit,
            self._btn_seed, self._btn_worm,
            self._btn_glass,
        ]

        # All buttons = menu toggle + menu items
        self._buttons = [self._btn_menu] + self._menu_buttons

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
        self._sim_speed = 2
        self._last_tick = time.time()
        self._last_wall_gx = None
        self._last_wall_gy = None
        self._gnomes = []
        self._gibs = []
        self._sparks = []
        self._splash_drops = []
        self._vine_tips = []
        self._worms = []
        self._bombs = []
        self._poison_settle = {}
        self._gnome_spawned_this_pinch = False
        self._fill_done_this_pinch = False
        self._held_gnome = None
        self._line_start_gx = None
        self._line_start_gy = None
        self._menu_open = False
        self._update_button_states()

    def close(self):
        self.visible = False

    def random_color(self):
        self._color_idx = (self._color_idx + 1) % len(_FUN_COLORS)
        self._color = _FUN_COLORS[self._color_idx]

    def _update_button_states(self):
        # Clear line-start marker when switching modes
        self._line_start_gx = None
        self._line_start_gy = None
        # Update menu button label to show current tool
        _mode_labels = {
            self.MODE_POUR: "☰ SND", self.MODE_HAND: "☰ HND", self.MODE_WOOD: "☰ WOD",
            self.MODE_CONCRETE: "☰ CON", self.MODE_ERASE: "☰ ERS", self.MODE_GNOME: "☰ GNM",
            self.MODE_FIRE: "☰ FIR", self.MODE_GUNPOWDER: "☰ GUN", self.MODE_NAPALM: "☰ NAP",
            self.MODE_GASOLINE: "☰ GAS", self.MODE_WATER: "☰ WTR", self.MODE_CONFETTI: "☰ CNF",
            self.MODE_POISON: "☰ ZMB", self.MODE_HOLYWATER: "☰ HLY", self.MODE_ICE: "☰ ICE",
            self.MODE_BOMB: "☰ BMB", self.MODE_MONEY: "☰ $$$", self.MODE_FIREBOMB: "☰ FBM",
            self.MODE_DIRT: "☰ DRT", self.MODE_MATCH: "☰ MCH", self.MODE_MAGMA: "☰ MAG",
            self.MODE_FILL: "☰ FIL", self.MODE_SEED: "☰ SED",
            self.MODE_WORM: "☰ WRM", self.MODE_GLASS: "☰ GLS",
        }
        self._btn_menu.label = _mode_labels.get(self._mode, "☰")
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
        self._btn_ice.active = (self._mode == self.MODE_ICE)
        self._btn_bomb.active = (self._mode == self.MODE_BOMB)
        self._btn_money.active = (self._mode == self.MODE_MONEY)
        self._btn_firebomb.active = (self._mode == self.MODE_FIREBOMB)
        self._btn_dirt.active = (self._mode == self.MODE_DIRT)
        self._btn_match.active = (self._mode == self.MODE_MATCH)
        self._btn_magma.active = (self._mode == self.MODE_MAGMA)
        self._btn_fill.active = (self._mode == self.MODE_FILL)
        self._btn_seed.active = (self._mode == self.MODE_SEED)
        self._btn_worm.active = (self._mode == self.MODE_WORM)
        self._btn_glass.active = (self._mode == self.MODE_GLASS)
        # Show what material fill will use
        _fill_names = {
            self.MODE_POUR: "FILL:S",
            self.MODE_WOOD: "FILL:Wd", self.MODE_CONCRETE: "FILL:C",
            self.MODE_FIRE: "FILL:F", self.MODE_GUNPOWDER: "FILL:GP",
            self.MODE_NAPALM: "FILL:N", self.MODE_GASOLINE: "FILL:G",
            self.MODE_WATER: "FILL:Wt", self.MODE_DIRT: "FILL:D",
            self.MODE_GLASS: "FILL:Gl",
        }
        self._btn_fill.label = _fill_names.get(self._fill_material, "FILL")
        self._btn_wind.active = self._wind_active
        self._btn_gravity.active = self._reverse_gravity
        self._btn_wind.label = "WIND ON" if self._wind_active else "WIND"
        self._btn_wind_dir.label = "< WIND" if self._wind_dir == -1 else "WIND >"
        self._btn_gravity.label = "GRV UP" if self._reverse_gravity else "GRAV"
        self._btn_color.swatch_color = self._color
        # Speed buttons — highlight when not at normal speed
        _speed_labels = {1: "2x", 2: "1x", 3: ".6x", 4: ".5x", 6: ".3x"}
        spd = _speed_labels.get(self._sim_speed, f"{2/self._sim_speed:.1f}x")
        self._btn_slow.active = (self._sim_speed > 2)
        self._btn_slow.label = f"SLO {spd}" if self._sim_speed > 2 else "SLOW"
        self._btn_fast.active = (self._sim_speed < 2)
        self._btn_fast.label = f"FST {spd}" if self._sim_speed < 2 else "FAST"

    def _in_ui_zone(self, px, py):
        if self._btn_menu.hit(px, py):
            return True
        if self._menu_open:
            for btn in self._menu_buttons:
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
        elif mat == self.MODE_DIRT:
            ptype, color_fn = DIRT, lambda: random.choice(_DIRT_COLORS)
        elif mat == self.MODE_GLASS:
            ptype, color_fn = GLASS, lambda: random.choice(_GLASS_COLORS)
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

    def _try_destroy_parachute(self, px, py):
        """If (px, py) is near a gnome's open parachute, destroy it. Returns True if destroyed."""
        for gnome in self._gnomes:
            if not gnome.alive or not gnome.parachute_open:
                continue
            sx = int(gnome.gx * _CELL + _CELL // 2)
            sy = int(gnome.gy * _CELL + _CELL) - 22
            # Parachute canopy center is at roughly (sx, sy - 50)
            chute_cx, chute_cy = sx, sy - 50
            if math.hypot(px - chute_cx, py - chute_cy) < 30:
                gnome.has_parachute = False
                gnome.parachute_open = False
                gnome.fall_start = time.time()  # reset fall timer for 1.4s death check
                return True
        return False

    def handle_tap(self, px, py):
        # Menu toggle — always active
        if self._btn_menu.hit(px, py):
            self._menu_open = not self._menu_open
            self._btn_menu.active = self._menu_open
            return
        # If menu is open, check menu buttons
        if self._menu_open:
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
            if self._btn_ice.hit(px, py):
                self._mode = self.MODE_ICE
                self._update_button_states(); return
            if self._btn_bomb.hit(px, py):
                self._mode = self.MODE_BOMB
                self._update_button_states(); return
            if self._btn_money.hit(px, py):
                self._mode = self.MODE_MONEY
                self._update_button_states(); return
            if self._btn_firebomb.hit(px, py):
                self._mode = self.MODE_FIREBOMB
                self._update_button_states(); return
            if self._btn_dirt.hit(px, py):
                self._mode = self.MODE_DIRT
                self._fill_material = self.MODE_DIRT
                self._update_button_states(); return
            if self._btn_match.hit(px, py):
                self._mode = self.MODE_MATCH
                self._update_button_states(); return
            if self._btn_magma.hit(px, py):
                self._mode = self.MODE_MAGMA
                self._update_button_states(); return
            if self._btn_fill.hit(px, py):
                self._mode = self.MODE_FILL
                self._update_button_states(); return
            if self._btn_seed.hit(px, py):
                self._mode = self.MODE_SEED
                self._update_button_states(); return
            if self._btn_worm.hit(px, py):
                self._mode = self.MODE_WORM
                self._update_button_states(); return
            if self._btn_glass.hit(px, py):
                self._mode = self.MODE_GLASS
                self._fill_material = self.MODE_GLASS
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
            if self._btn_slow.hit(px, py):
                self._sim_speed = min(6, self._sim_speed + 1)
                self._update_button_states(); return
            if self._btn_fast.hit(px, py):
                self._sim_speed = max(1, self._sim_speed - 1)
                self._update_button_states(); return
            if self._btn_clear.hit(px, py):
                self._state.clear_all()
                self._gnomes = []
                self._gibs = []
                self._sparks = []
                self._splash_drops = []
                self._vine_tips = []
                self._worms = []
                self._bombs = []
                self._poison_settle = {}
                self._menu_open = False; self._btn_menu.active = False
                return
            # Click outside menu panel closes it
            self._menu_open = False
            self._btn_menu.active = False
            return
        # Menu is closed — canvas interaction
        if not self._in_ui_zone(px, py):
            # Check if clicking on a parachute — destroy it regardless of mode
            if self._try_destroy_parachute(px, py):
                return
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
            elif self._mode == self.MODE_GLASS:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        self._state.add(GLASS, gx + dx, gy + dy, random.choice(_GLASS_COLORS))
            elif self._mode == self.MODE_GNOME:
                self._gnomes.append(_Gnome(gx, gy))
            elif self._mode == self.MODE_FIRE:
                for _ in range(15):
                    rx = gx + random.randint(-3, 3)
                    ry = gy + random.randint(-2, 2)
                    self._state.add(FIRE, rx, ry, random.choice(_FIRE_COLORS))
            elif self._mode == self.MODE_GUNPOWDER:
                # Paint gunpowder as a static fuse line (like wood)
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        self._state.add(GUNPOWDER, gx + dx, gy + dy, random.choice(_GUNPOWDER_COLORS))
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
            elif self._mode == self.MODE_ICE:
                for dx in range(-2, 3):
                    for dy in range(-2, 3):
                        self._state.add(ICE, gx + dx, gy + dy, random.choice(_ICE_COLORS))
            elif self._mode == self.MODE_BOMB:
                self._state.erase_circle(gx, gy, 3)
                self._bombs.append(_Bomb(gx, gy))
            elif self._mode == self.MODE_FIREBOMB:
                self._state.erase_circle(gx, gy, 3)
                self._bombs.append(_Bomb(gx, gy, is_fire=True))
            elif self._mode == self.MODE_MONEY:
                for _ in range(20):
                    rx = gx + random.randint(-4, 4)
                    ry = gy + random.randint(-4, 1)
                    self._state.add(MONEY, rx, ry, random.choice(_MONEY_COLORS))
            elif self._mode == self.MODE_DIRT:
                for _ in range(25):
                    rx = gx + random.randint(-5, 5)
                    ry = gy + random.randint(-5, 2)
                    self._state.add(DIRT, rx, ry, random.choice(_DIRT_COLORS))
            elif self._mode == self.MODE_MATCH:
                for _ in range(3):
                    rx = gx + random.randint(-1, 1)
                    ry = gy + random.randint(-1, 0)
                    self._state.add(MAGMA, rx, ry, random.choice(_MAGMA_COLORS))
            elif self._mode == self.MODE_MAGMA:
                for _ in range(15):
                    rx = gx + random.randint(-3, 3)
                    ry = gy + random.randint(-2, 2)
                    self._state.add(MAGMA, rx, ry, random.choice(_MAGMA_COLORS))
            elif self._mode == self.MODE_SEED:
                for _ in range(5):
                    rx = gx + random.randint(-2, 2)
                    ry = gy + random.randint(-2, 1)
                    self._state.add(SEED, rx, ry, random.choice(_SEED_COLORS))
            elif self._mode == self.MODE_FILL:
                self._flood_fill(gx, gy)

    def handle_pinch(self, px, py):
        if self._in_ui_zone(px, py):
            self._last_wall_gx = None
            self._last_wall_gy = None
            return
        gx, gy = int(px) // _CELL, int(py) // _CELL
        # Check if pinching on a parachute — destroy it regardless of mode
        self._try_destroy_parachute(px, py)
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
        elif self._mode == self.MODE_GLASS:
            if (self._last_wall_gx is not None and self._last_wall_gy is not None
                    and abs(gx - self._last_wall_gx) <= 8
                    and abs(gy - self._last_wall_gy) <= 8):
                line_pts = _bresenham(self._last_wall_gx, self._last_wall_gy, gx, gy)
                for lx, ly in line_pts:
                    for dx in range(-1, 2):
                        for dy in range(-1, 2):
                            self._state.add(GLASS, lx + dx, ly + dy, random.choice(_GLASS_COLORS))
            else:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        self._state.add(GLASS, gx + dx, gy + dy, random.choice(_GLASS_COLORS))
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
            # Paint gunpowder as a static fuse line (like wood, with interpolation)
            if (self._last_wall_gx is not None and self._last_wall_gy is not None
                    and abs(gx - self._last_wall_gx) <= 8
                    and abs(gy - self._last_wall_gy) <= 8):
                line_pts = _bresenham(self._last_wall_gx, self._last_wall_gy, gx, gy)
                for lx, ly in line_pts:
                    for dx in range(-1, 2):
                        for dy in range(-1, 2):
                            self._state.add(GUNPOWDER, lx + dx, ly + dy, random.choice(_GUNPOWDER_COLORS))
            else:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        self._state.add(GUNPOWDER, gx + dx, gy + dy, random.choice(_GUNPOWDER_COLORS))
            self._last_wall_gx = gx
            self._last_wall_gy = gy
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
        elif self._mode == self.MODE_ICE:
            # Ice is placed like concrete — solid blocks, connected via bresenham
            if (self._last_wall_gx is not None and self._last_wall_gy is not None
                    and abs(gx - self._last_wall_gx) <= 8
                    and abs(gy - self._last_wall_gy) <= 8):
                line_pts = _bresenham(self._last_wall_gx, self._last_wall_gy, gx, gy)
                for lx, ly in line_pts:
                    for dx in range(-1, 2):
                        for dy in range(-1, 2):
                            self._state.add(ICE, lx + dx, ly + dy, random.choice(_ICE_COLORS))
            else:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        self._state.add(ICE, gx + dx, gy + dy, random.choice(_ICE_COLORS))
            self._last_wall_gx = gx
            self._last_wall_gy = gy
        elif self._mode == self.MODE_BOMB:
            # One bomb per pinch — don't spawn continuously
            if not getattr(self, '_gnome_spawned_this_pinch', False):
                self._state.erase_circle(gx, gy, 3)
                self._bombs.append(_Bomb(gx, gy))
                self._gnome_spawned_this_pinch = True
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_FIREBOMB:
            # One firebomb per pinch
            if not getattr(self, '_gnome_spawned_this_pinch', False):
                self._state.erase_circle(gx, gy, 3)
                self._bombs.append(_Bomb(gx, gy, is_fire=True))
                self._gnome_spawned_this_pinch = True
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_MONEY:
            for _ in range(8):
                rx = gx + random.randint(-3, 3)
                ry = gy + random.randint(-2, 1)
                self._state.add(MONEY, rx, ry, random.choice(_MONEY_COLORS))
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_DIRT:
            for _ in range(10):
                rx = gx + random.randint(-3, 3)
                ry = gy + random.randint(-2, 1)
                self._state.add(DIRT, rx, ry, random.choice(_DIRT_COLORS))
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_MATCH:
            for _ in range(2):
                rx = gx + random.randint(-1, 1)
                ry = gy + random.randint(-1, 0)
                self._state.add(MAGMA, rx, ry, random.choice(_MAGMA_COLORS))
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_MAGMA:
            for _ in range(8):
                rx = gx + random.randint(-2, 2)
                ry = gy + random.randint(-2, 2)
                self._state.add(MAGMA, rx, ry, random.choice(_MAGMA_COLORS))
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_FILL:
            # One-shot fill per pinch, same as gnome
            if not getattr(self, '_fill_done_this_pinch', False):
                self._flood_fill(gx, gy)
                self._fill_done_this_pinch = True
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_SEED:
            # Drop a few seeds each frame while dragging
            for _ in range(5):
                rx = gx + random.randint(-2, 2)
                ry = gy + random.randint(-2, 1)
                self._state.add(SEED, rx, ry, random.choice(_SEED_COLORS))
            self._last_wall_gx = None
            self._last_wall_gy = None
        elif self._mode == self.MODE_WORM:
            # Spawn 3 worms at click location — one-shot per pinch
            if not getattr(self, '_gnome_spawned_this_pinch', False):
                g = self._state.grid
                h, w = g.shape
                # Only spawn in dirt
                if 0 <= gx < w and 0 <= gy < h and g[gy, gx] == DIRT:
                    for _ in range(3):
                        self._worms.append(_Worm(gx, gy))
                self._gnome_spawned_this_pinch = True
            self._last_wall_gx = None
            self._last_wall_gy = None

    def handle_double_click(self, px, py):
        """Double-click line tool: first click sets start, second draws line."""
        if self._in_ui_zone(px, py):
            return
        # Only works for solid painting modes
        if self._mode not in (self.MODE_WOOD, self.MODE_CONCRETE, self.MODE_ICE, self.MODE_GUNPOWDER, self.MODE_GLASS):
            return
        gx, gy = int(px) // _CELL, int(py) // _CELL
        if self._line_start_gx is None:
            # First double-click — store start point
            self._line_start_gx = gx
            self._line_start_gy = gy
        else:
            # Second double-click — draw line from start to here
            line_pts = _bresenham(self._line_start_gx, self._line_start_gy, gx, gy)
            if self._mode == self.MODE_WOOD:
                for lx, ly in line_pts:
                    for dx in range(-1, 2):
                        for dy in range(-1, 2):
                            self._state.add(WOOD, lx + dx, ly + dy, random.choice(_WOOD_COLORS))
            elif self._mode == self.MODE_CONCRETE:
                for lx, ly in line_pts:
                    for dx in range(-1, 2):
                        for dy in range(-1, 2):
                            self._state.add(CONCRETE, lx + dx, ly + dy, _CONCRETE_COLOR)
            elif self._mode == self.MODE_ICE:
                for lx, ly in line_pts:
                    for dx in range(-1, 2):
                        for dy in range(-1, 2):
                            self._state.add(ICE, lx + dx, ly + dy, random.choice(_ICE_COLORS))
            elif self._mode == self.MODE_GUNPOWDER:
                for lx, ly in line_pts:
                    for dx in range(-1, 2):
                        for dy in range(-1, 2):
                            self._state.add(GUNPOWDER, lx + dx, ly + dy, random.choice(_GUNPOWDER_COLORS))
            elif self._mode == self.MODE_GLASS:
                for lx, ly in line_pts:
                    for dx in range(-1, 2):
                        for dy in range(-1, 2):
                            self._state.add(GLASS, lx + dx, ly + dy, random.choice(_GLASS_COLORS))
            self._line_start_gx = None
            self._line_start_gy = None

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
        MODE_WATER, MODE_CONFETTI, MODE_POISON, MODE_HOLYWATER, MODE_ICE, MODE_BOMB, MODE_FIREBOMB, MODE_MONEY, MODE_DIRT, MODE_MATCH, MODE_MAGMA, MODE_FILL, MODE_SEED, MODE_WORM, MODE_GLASS,
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
        if self._mode not in (self.MODE_ERASE, self.MODE_GNOME, self.MODE_HAND, self.MODE_FILL, self.MODE_CONFETTI, self.MODE_POISON, self.MODE_HOLYWATER, self.MODE_ICE, self.MODE_BOMB, self.MODE_FIREBOMB, self.MODE_MONEY, self.MODE_MATCH, self.MODE_MAGMA, self.MODE_SEED, self.MODE_WORM):
            self._fill_material = self._mode
        self._update_button_states()

    def draw(self, surface, gui_scale):
        now = time.time()
        dt = now - self._last_tick if self._last_tick else 0.016
        self._last_tick = now

        # Fixed 1 sim step per frame — no accumulator, no catch-up, no jitter.
        # Main loop runs at 60fps; we step the sim every Nth frame based on speed setting.
        self._sim_tick += 1
        if self._sim_tick % self._sim_speed == 0:
            _step(self._state, self._wind_active, self._wind_dir, self._reverse_gravity, self._splash_drops, self._vine_tips)
            _step_fire(self._state)
            _step_napalm(self._state)
            _step_magma(self._state)
            _step_steam(self._state)

            # Poison decay — settled poison disappears after 2 seconds
            g = self._state.grid
            h, w = g.shape
            poison_ys, poison_xs = np.where(g == POISON)
            new_settle = {}
            cur_time = now
            for i in range(len(poison_ys)):
                py, px = int(poison_ys[i]), int(poison_xs[i])
                # Check if settled (can't fall further)
                below = py + 1
                settled = (below >= h or g[below, px] != EMPTY)
                if settled:
                    key = (px, py)
                    if key in self._poison_settle:
                        if cur_time - self._poison_settle[key] >= 2.0:
                            g[py, px] = EMPTY
                            self._state.colors[py, px] = (0, 0, 0)
                        else:
                            new_settle[key] = self._poison_settle[key]
                    else:
                        new_settle[key] = cur_time
            self._poison_settle = new_settle

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

            # Zombie bite — zombie touches living gnome: both freeze 2s, then living turns zombie
            zombies = [g for g in self._gnomes if g.alive and g.is_zombie and not g.frozen]
            alive_live = [g for g in self._gnomes if g.alive and not g.is_zombie and not g.frozen]
            for zg in zombies:
                for lg in alive_live:
                    if abs(zg.gx - lg.gx) < 3 and abs(zg.gy - lg.gy) < 3:
                        # Freeze both for 2 seconds
                        zg.frozen = True
                        zg.freeze_start = time.time()
                        lg.frozen = True
                        lg.freeze_start = time.time()
                        # Mark victim — will turn zombie when freeze ends
                        lg.zombie_pending = True
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

            # Step sparks
            for spark in self._sparks:
                spark.step(self._state.grid)
            self._sparks = [s for s in self._sparks if s.alive]

            # Step splash drops
            for drop in self._splash_drops:
                drop.step(self._state.grid, self._state.colors)
            self._splash_drops = [d for d in self._splash_drops if d.alive]

            # Step worms
            for worm in self._worms:
                worm.step(self._state.grid, self._state.colors)
            self._worms = [w for w in self._worms if w.alive]

            # Step bombs — physics + fuse check
            for bomb in self._bombs:
                bomb.step(self._state.grid)
            # Explode any bombs that went off
            new_bombs = []
            for bomb in self._bombs:
                if bomb.exploded:
                    _explode_bomb(self._state, bomb.x, bomb.y,
                                  self._gnomes, self._gibs, self._sparks, bomb.is_fire)
                elif bomb.alive:
                    new_bombs.append(bomb)
            self._bombs = new_bombs

        surface.fill(_BLACK)

        # Fast pixel rendering — reuse buffer to avoid per-frame allocation
        st = self._state
        # Copy colors into pre-allocated buffer, zero out empty/tunnel cells in-place
        np.copyto(self._rgb_buf, st.colors)
        self._rgb_buf[st.grid == EMPTY] = 0
        self._rgb_buf[st.grid == TUNNEL] = 0

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
            # (frozen indicator removed — no circle on zombie touch)
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

        # Draw sparks (explosion shower)
        for spark in self._sparks:
            sx_px = int(spark.x * _CELL + _CELL // 2)
            sy_px = int(spark.y * _CELL + _CELL // 2)
            pygame.draw.circle(surface, spark.color, (sx_px, sy_px), 2)

        # Draw splash drops
        for drop in self._splash_drops:
            dx_px = int(drop.x * _CELL + _CELL // 2)
            dy_px = int(drop.y * _CELL + _CELL // 2)
            pygame.draw.circle(surface, drop.color, (dx_px, dy_px), 2)

        # Draw worms
        for worm in self._worms:
            worm.draw(surface)

        # Draw bombs
        for bomb in self._bombs:
            bomb.draw(surface, self._bomb_font)

        # Draw line-start marker (double-click line tool)
        if self._line_start_gx is not None and self._line_start_gy is not None:
            mx = self._line_start_gx * _CELL + _CELL // 2
            my = self._line_start_gy * _CELL + _CELL // 2
            pygame.draw.circle(surface, (255, 255, 0), (mx, my), 6, 2)
            pygame.draw.circle(surface, (255, 255, 0), (mx, my), 2)

        # Draw menu button (always visible)
        self._btn_menu.draw(surface)

        # Draw menu panel when open
        if self._menu_open:
            # Semi-transparent backdrop behind buttons
            panel_w = 6 * (82 + 4) + 4
            panel_h = 5 * (40 + 4) + 4
            backdrop = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            backdrop.fill((20, 20, 30, 200))
            surface.blit(backdrop, (4, 48))
            for btn in self._menu_buttons:
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
