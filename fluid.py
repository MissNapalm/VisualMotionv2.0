import os
import random
import pygame
import sys
import math

# Initialize Pygame
pygame.init()

# Screen settings
SCREEN_WIDTH = 750
SCREEN_HEIGHT = 650
os.environ['SDL_VIDEO_WINDOW_POS'] = '%d, %d' % (150, 50)

screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption('Fluid Simulation')

# FPS settings
FPS = 40
clock = pygame.time.Clock()

# Define colors
black = (0, 0, 0)
pale_yellow = (255, 255, 153)  # Pale yellow for particles
grey = (160, 32, 240)          # Gray color for walls
button_color = grey            # Set button color to match walls
white = (255, 255, 255)

# Bright, fun colors for particles
fun_colors = [
    (255, 69, 0),   # Red-Orange
    (255, 105, 180), # Hot Pink
    (255, 255, 0),  # Yellow
    (0, 255, 255),  # Cyan
    (124, 252, 0),  # Lime Green
    (255, 165, 0),  # Orange
    (0, 128, 255),  # Dodger Blue
]

# Function to swap dictionary keys and values
def swap_kv(dc):
    outval = {}
    for k, v in dc.items():
        outval[v] = k
    return outval

class FluxState:
    EMPTY_PARTICLE = 0
    STATIC_PARTICLE = 1
    HEAVY_PARTICLE = 2

    particle_colors = {
        EMPTY_PARTICLE: black,
        STATIC_PARTICLE: grey,  # Gray color for static walls
        HEAVY_PARTICLE: pale_yellow,  # Initial pale yellow color for particles
    }

    particle_colors_by_color = swap_kv(particle_colors)

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.particle_map = {}

    def from_surface(surf):
        (surf_w, surf_h) = surf.get_size()
        state = FluxState(surf_w, surf_h)
        for x in range(0, surf_w):
            for y in range(0, surf_h):
                # Get (r, g, b) at this x, y location
                pixel_color = tuple(surf.get_at((x, y)))[0:3]
                if pixel_color in FluxState.particle_colors_by_color:
                    type = FluxState.particle_colors_by_color[pixel_color]
                    state.add_particle(type, (x, y))
        return state

    # loc is an x, y tuple
    def add_particle(self, type, loc, color=None):
        self.assert_loc(loc)
        if type == self.EMPTY_PARTICLE:
            if loc in self.particle_map:
                self.particle_map.pop(loc)
        else:
            self.particle_map[loc] = (type, color or self.particle_colors[type])

    def add_particle_rect(self, ptype, corner, width, height, color=None):
        for x in range(corner[0], corner[0] + width):
            for y in range(corner[1], corner[1] + height):
                if self.check_loc((x, y)):
                    self.add_particle(ptype, (x, y), color)

    def remove_particle(self, loc):
        self.assert_loc(loc)
        old = self.particle_map.get(loc, self.EMPTY_PARTICLE)
        self.add_particle(self.EMPTY_PARTICLE, loc)
        return old

    def move_particle(self, src, dst):
        self.assert_loc(src)
        self.assert_loc(dst)
        ptype, color = self.particle_map[src]
        self.add_particle(self.remove_particle(src), dst, color)

    def check_loc(self, loc):
        return loc[0] >= 0 and loc[0] < self.width and loc[1] >= 0 and loc[1] < self.height

    def assert_loc(self, loc):
        assert self.check_loc(loc), "loc {} out of bounds".format(loc)

    def destroy_particles_circle(self, center, radius):
        cx, cy = center
        for x in range(cx - radius, cx + radius + 1):
            for y in range(cy - radius, cy + radius + 1):
                if self.check_loc((x, y)):
                    if math.sqrt((x - cx) ** 2 + (y - cy) ** 2) <= radius:
                        self.remove_particle((x, y))

def update_world(state, wind_active=False, wind_direction=1, reverse_gravity=False, gravity_zone=(0, 0, 0, 0), gravity_shape='rectangle'):
    new_particles = {}

    def loc_empty(loc):
        return state.check_loc(loc) and not ((loc in state.particle_map) or (loc in new_particles))

    klist = list(state.particle_map.keys())

    for ogloc in klist:
        ptype, color = state.particle_map[ogloc]
        new_loc = ogloc

        # Check if the particle is within the reverse gravity zone
        in_reverse_zone = False

        if gravity_shape == 'rectangle':
            in_reverse_zone = gravity_zone[0] <= ogloc[0] <= gravity_zone[0] + gravity_zone[2] and \
                              gravity_zone[1] <= ogloc[1] <= gravity_zone[1] + gravity_zone[3]

        elif gravity_shape == 'circle':
            gx, gy = gravity_zone[0] + gravity_zone[2] // 2, gravity_zone[1] + gravity_zone[3] // 2
            dist = math.sqrt((ogloc[0] - gx)**2 + (ogloc[1] - gy)**2)
            in_reverse_zone = dist <= gravity_zone[2] // 2

        elif gravity_shape == 'triangle':
            # Triangle attraction logic
            top = (gravity_zone[0] + gravity_zone[2] // 2, gravity_zone[1])
            bottom_left = (gravity_zone[0], gravity_zone[1] + gravity_zone[3])
            bottom_right = (gravity_zone[0] + gravity_zone[2], gravity_zone[1] + gravity_zone[3])

            def sign(p1, p2, p3):
                return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])

            b1 = sign(ogloc, top, bottom_left) < 0.0
            b2 = sign(ogloc, bottom_left, bottom_right) < 0.0
            b3 = sign(ogloc, bottom_right, top) < 0.0

            in_reverse_zone = ((b1 == b2) and (b2 == b3))

        if ptype != FluxState.STATIC_PARTICLE:
            # Determine the gravity direction based on the reverse gravity zone
            gravity_direction = -1 if reverse_gravity and in_reverse_zone else 1

            # Attempt to move the particle based on gravity
            below_loc = (ogloc[0], ogloc[1] + gravity_direction)
            left_below_loc = (ogloc[0] - 1, ogloc[1] + gravity_direction)
            right_below_loc = (ogloc[0] + 1, ogloc[1] + gravity_direction)

            if loc_empty(below_loc):
                new_loc = below_loc
            elif loc_empty(left_below_loc):
                new_loc = left_below_loc
            elif loc_empty(right_below_loc):
                new_loc = right_below_loc
            else:
                # Randomly move left or right if blocked
                if random.random() < 0.5:
                    left_loc = (ogloc[0] - 1, ogloc[1])
                    if loc_empty(left_loc):
                        new_loc = left_loc
                else:
                    right_loc = (ogloc[0] + 1, ogloc[1])
                    if loc_empty(right_loc):
                        new_loc = right_loc

            # Apply wind effect
            if wind_active:
                wind_loc = (new_loc[0] + wind_direction, new_loc[1])
                if loc_empty(wind_loc):
                    new_loc = wind_loc

        new_particles[new_loc] = (state.particle_map[ogloc][0], color)
        state.particle_map.pop(ogloc)

    state.particle_map = new_particles

def check_events(button_rect, is_fullscreen):
    keys = pygame.key.get_pressed()
    event_result = []

    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            return False
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_y:
                event_result.append('y_pressed')
            elif e.key == pygame.K_f:
                event_result.append('f_pressed')
            elif e.key == pygame.K_w:
                event_result.append('w_pressed')  # Toggle wind
            elif e.key == pygame.K_a:
                event_result.append('a_pressed')  # Wind left
            elif e.key == pygame.K_d:
                event_result.append('d_pressed')  # Wind right
            elif e.key == pygame.K_r:
                event_result.append('r_pressed')  # Toggle reverse gravity
            elif e.key == pygame.K_t:
                event_result.append('t_pressed')  # Toggle shape
        if e.type == pygame.MOUSEBUTTONDOWN:
            if button_rect.collidepoint(e.pos):
                event_result.append('button_pressed')

    # Handle continuous movement with arrow keys
    if keys[pygame.K_UP]:
        event_result.append('up_pressed')
    if keys[pygame.K_DOWN]:
        event_result.append('down_pressed')
    if keys[pygame.K_LEFT]:
        event_result.append('left_pressed')
    if keys[pygame.K_RIGHT]:
        event_result.append('right_pressed')

    return event_result

def toggle_fullscreen(is_fullscreen):
    if is_fullscreen:
        pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    else:
        pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
    return not is_fullscreen

def get_random_fun_color():
    return random.choice(fun_colors)

def render(state, flux_display, fps, st_font, st_font_small, button_rect, current_mode, wind_active, wind_direction, reverse_gravity, gravity_zone, gravity_shape):
    flux_display.fill(black)

    for loc, (ptype, color) in state.particle_map.items():
        if ptype == FluxState.HEAVY_PARTICLE:
            # Draw particles as 5x5 squares
            rect = pygame.Rect(loc[0] * 5, loc[1] * 5, 5, 5)
            pygame.draw.rect(flux_display, color, rect)
        elif ptype == FluxState.STATIC_PARTICLE:
            # Draw walls as 7x7 squares (30% larger than particles)
            rect = pygame.Rect(loc[0] * 5, loc[1] * 5, 7, 7)
            pygame.draw.rect(flux_display, color, rect)

    # Draw gravity zone
    if reverse_gravity:
        if gravity_shape == 'rectangle':
            zone_rect = pygame.Rect(gravity_zone[0] * 5, gravity_zone[1] * 5, gravity_zone[2] * 5, gravity_zone[3] * 5)
            pygame.draw.rect(flux_display, (100, 100, 255), zone_rect, 1)
        elif gravity_shape == 'circle':
            gx, gy = gravity_zone[0] + gravity_zone[2] // 2, gravity_zone[1] + gravity_zone[3] // 2
            pygame.draw.circle(flux_display, (100, 100, 255), (gx * 5, gy * 5), gravity_zone[2] * 5 // 2, 1)
        elif gravity_shape == 'triangle':
            top = (gravity_zone[0] * 5 + gravity_zone[2] * 5 // 2, gravity_zone[1] * 5)
            bottom_left = (gravity_zone[0] * 5, (gravity_zone[1] + gravity_zone[3]) * 5)
            bottom_right = ((gravity_zone[0] + gravity_zone[2]) * 5, (gravity_zone[1] + gravity_zone[3]) * 5)
            pygame.draw.polygon(flux_display, (100, 100, 255), [top, bottom_left, bottom_right], 1)

    # Draw button
    pygame.draw.circle(flux_display, button_color, button_rect.center, button_rect.width // 2)
    mode_text = ["Particles", "Walls", "Eraser"][current_mode]
    button_text = st_font.render(mode_text, True, white)
    button_text_rect = button_text.get_rect(center=button_rect.center)
    flux_display.blit(button_text, button_text_rect)

    # Render instruction text
    instruction_text = st_font_small.render("Press Y to change particle color", True, (180, 180, 180))
    instruction_rect = instruction_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 20))
    flux_display.blit(instruction_text, instruction_rect)

    # Render wind status
    wind_status = "Off"
    if wind_active:
        wind_status = "Left" if wind_direction == -1 else "Right"
    wind_text = st_font_small.render(f"Wind: {wind_status} (Toggle: W, A/D to change direction)", True, (180, 180, 180))
    wind_rect = wind_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 40))
    flux_display.blit(wind_text, wind_rect)

    # Render reverse gravity status
    gravity_text = st_font_small.render(f"Reverse Gravity: {'On' if reverse_gravity else 'Off'} (Toggle: R)", True, (180, 180, 180))
    gravity_rect = gravity_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 60))
    flux_display.blit(gravity_text, gravity_rect)

    # Render gravity shape
    gravity_shape_text = st_font_small.render(f"Gravity Shape: {gravity_shape.title()} (Toggle: T)", True, (180, 180, 180))
    gravity_shape_rect = gravity_shape_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 80))
    flux_display.blit(gravity_shape_text, gravity_shape_rect)

    fps_str = "%.1f" % fps
    fps_surface = st_font_small.render(fps_str, True, grey)
    fps_rect = fps_surface.get_rect()
    fps_rect.bottom = state.height * 5 - 10
    fps_rect.left = 10

    flux_display.blit(fps_surface, fps_rect)

def main_window():
    # Initialize FluxState with no default particles
    state = FluxState(SCREEN_WIDTH // 5, SCREEN_HEIGHT // 5)  # Adjusted for 5x5 pixel grid
    current_particle_color = pale_yellow  # Default initial color for particles

    # Initialize font (using a pixelated font for the retro look)
    pygame.font.init()
    st_font = pygame.font.Font(pygame.font.get_default_font(), 24)  # Pixelated font size for button text
    st_font_small = pygame.font.Font(pygame.font.get_default_font(), 18)  # Smaller font for less obvious text

    # Button for switching modes
    button_radius = 90  # Diameter of 90px
    button_rect = pygame.Rect(SCREEN_WIDTH - button_radius - 116, 10, button_radius * 2, button_radius * 2)

    mode_names = ["Particles", "Walls", "Eraser"]
    current_mode = 0  # Start in particle mode

    is_fullscreen = False  # Track fullscreen state

    # Wind settings
    wind_active = False
    wind_direction = 1  # 1 for right, -1 for left

    # Reverse gravity settings
    reverse_gravity = False
    gravity_zone = (10, 10, int(50 * 1.3), int(60 * 1.3))  # Define a zone (x, y, width, height), double height
    gravity_shape = 'rectangle'  # Start with rectangle shape

    running = True
    while running:
        # Handle events
        event_results = check_events(button_rect, is_fullscreen)
        for event_result in event_results:
            if event_result == 'y_pressed':
                # Change the color of new particles to a fun color
                current_particle_color = get_random_fun_color()
            elif event_result == 'button_pressed':
                # Toggle mode
                current_mode = (current_mode + 1) % 3
            elif event_result == 'f_pressed':
                # Toggle fullscreen
                is_fullscreen = toggle_fullscreen(is_fullscreen)
            elif event_result == 'w_pressed':
                # Toggle wind
                wind_active = not wind_active
            elif event_result == 'a_pressed':
                # Wind left
                wind_direction = -1
            elif event_result == 'd_pressed':
                # Wind right
                wind_direction = 1
            elif event_result == 'r_pressed':
                # Toggle reverse gravity
                reverse_gravity = not reverse_gravity
            elif event_result == 't_pressed':
                # Toggle gravity shape
                shapes = ['rectangle', 'circle', 'triangle']
                gravity_shape = shapes[(shapes.index(gravity_shape) + 1) % len(shapes)]
            elif event_result == 'up_pressed':
                # Move gravity zone up
                gravity_zone = (gravity_zone[0], max(gravity_zone[1] - 1, 0), gravity_zone[2], gravity_zone[3])
            elif event_result == 'down_pressed':
                # Move gravity zone down
                gravity_zone = (gravity_zone[0], min(gravity_zone[1] + 1, state.height - gravity_zone[3]), gravity_zone[2], gravity_zone[3])
            elif event_result == 'left_pressed':
                # Move gravity zone left
                gravity_zone = (max(gravity_zone[0] - 1, 0), gravity_zone[1], gravity_zone[2], gravity_zone[3])
            elif event_result == 'right_pressed':
                # Move gravity zone right
                gravity_zone = (min(gravity_zone[0] + 1, state.width - gravity_zone[2]), gravity_zone[1], gravity_zone[2], gravity_zone[3])
            elif not event_result:
                running = False

        screen.fill((0, 0, 0))  # Clear screen

        # Check for mouse input
        mouse_pressed = pygame.mouse.get_pressed()
        mx, my = pygame.mouse.get_pos()
        grid_x, grid_y = mx // 5, my // 5

        if mouse_pressed[0]:  # Left mouse button
            if current_mode == 0:  # Particles mode
                # Spawn 10 particles at the mouse location
                for _ in range(10):
                    state.add_particle(FluxState.HEAVY_PARTICLE, (random.randint(grid_x-2, grid_x+2), grid_y), current_particle_color)
            elif current_mode == 1:  # Walls mode
                # Draw 2x2 square walls (with 30% larger dimensions)
                for dx in range(2):
                    for dy in range(2):
                        state.add_particle(FluxState.STATIC_PARTICLE, (grid_x + dx, grid_y + dy), grey)
            elif current_mode == 2:  # Eraser mode
                # Erase particles in a small area
                state.destroy_particles_circle((grid_x, grid_y), 6)

        if mouse_pressed[2]:  # Right mouse button
            # Draw 2x2 square walls
            state.add_particle_rect(FluxState.STATIC_PARTICLE, (grid_x, grid_y), 2, 2)

        if pygame.key.get_pressed()[pygame.K_f]:  # Destroy particles with 'F' key
            state.destroy_particles_circle((grid_x, grid_y), 5)

        update_world(state, wind_active, wind_direction, reverse_gravity, gravity_zone, gravity_shape)
        render(state, screen, clock.get_fps(), st_font, st_font_small, button_rect, current_mode, wind_active, wind_direction, reverse_gravity, gravity_zone, gravity_shape)
        pygame.display.update()
        clock.tick(FPS)

    pygame.quit()

main_window()