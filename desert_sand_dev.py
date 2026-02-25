#!/usr/bin/env python3
"""
Desert Sand — standalone dev/testing harness.
Mouse-only: no camera, no gestures, no hand tracking.

Controls:
  Left-click drag  — pour / draw / erase (whatever tool is selected)
  Right-click drag — erase
  Double-click     — line tool (wall/wood/concrete)
  Scroll wheel     — cycle through tools
  ESC              — quit
"""

import math
import time
import sys
import pygame

from sand_window import SandWindow

WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 800
FPS = 60


def main():
    pygame.init()
    try:
        screen = pygame.display.set_mode(
            (WINDOW_WIDTH, WINDOW_HEIGHT),
            pygame.DOUBLEBUF | pygame.SCALED,
            vsync=1,
        )
    except Exception:
        screen = pygame.display.set_mode(
            (WINDOW_WIDTH, WINDOW_HEIGHT), pygame.DOUBLEBUF
        )
    pygame.display.set_caption("Desert Sand — Dev Mode")
    clock = pygame.time.Clock()

    sand = SandWindow(WINDOW_WIDTH, WINDOW_HEIGHT)
    sand.open()

    mouse_down = False
    mouse_down_pos = None
    pouring = False       # True once we start pouring (past drag threshold or held long enough)
    mouse_down_time = 0.0
    last_click_time = 0.0
    right_down = False
    saved_mode = None  # to restore after right-click erase

    print("=" * 50)
    print("DESERT SAND — DEV MODE")
    print("Left-click: use tool | Right-click: erase")
    print("Scroll: cycle tools | ESC: quit")
    print("=" * 50)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                pygame.quit()
                sys.exit()

            # Scroll wheel — cycle tools
            if event.type == pygame.MOUSEWHEEL:
                sand.handle_scroll(-event.y)

            # Left mouse button
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                now = time.time()
                mouse_down = True
                pouring = False
                mouse_down_pos = (mx, my)
                mouse_down_time = now
                # Tap for buttons
                sand.handle_tap(mx, my)
                # Check for quit button (only when menu is open)
                if sand._menu_open and sand._btn_quit.hit(mx, my):
                    # Re-open instead of closing (standalone mode)
                    sand.open()
                last_click_time = now

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if mouse_down:
                    mx, my = event.pos
                    now = time.time()
                    # Double-click detection
                    if mouse_down_pos:
                        total = math.hypot(mx - mouse_down_pos[0],
                                           my - mouse_down_pos[1])
                        if total <= 15 and now - last_click_time < 0.4:
                            sand.handle_double_click(mx, my)
                    sand.handle_pinch_end()
                    mouse_down = False
                    mouse_down_pos = None
                    pouring = False

            elif event.type == pygame.MOUSEMOTION and mouse_down:
                mx, my = event.pos
                if not pouring and mouse_down_pos:
                    total = math.hypot(mx - mouse_down_pos[0],
                                       my - mouse_down_pos[1])
                    if total > 8:
                        pouring = True
                if pouring:
                    sand.handle_pinch(mx, my)

            # Right mouse button — quick erase
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                right_down = True
                saved_mode = sand._mode
                sand._mode = SandWindow.MODE_ERASE
                sand._update_button_states()
                mx, my = event.pos
                sand.handle_tap(mx, my)

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
                if right_down:
                    sand.handle_pinch_end()
                    right_down = False
                    if saved_mode is not None:
                        sand._mode = saved_mode
                        sand._update_button_states()
                        saved_mode = None

            elif event.type == pygame.MOUSEMOTION and right_down:
                mx, my = event.pos
                sand.handle_pinch(mx, my)

        # Continuous pour: keep calling handle_pinch while button is held,
        # even if the mouse isn't moving.
        # After 150ms hold, start pouring at current position (no drag needed).
        if mouse_down:
            mx, my = pygame.mouse.get_pos()
            if not pouring and time.time() - mouse_down_time > 0.15:
                pouring = True
            if pouring:
                sand.handle_pinch(mx, my)
        elif right_down:
            mx, my = pygame.mouse.get_pos()
            sand.handle_pinch(mx, my)

        # Draw
        screen.fill((20, 20, 30))
        sand.draw(screen, 1.0)

        # FPS counter
        fps = clock.get_fps()
        fps_surf = pygame.font.Font(None, 24).render(f"FPS: {fps:.0f}", True, (100, 100, 100))
        screen.blit(fps_surf, (5, 5))

        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()
