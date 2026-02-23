"""
Gesture Carousel - main application loop.
"""

import math
import time

import pygame

from hand_tracker import HandTracker
from gestures import (
    is_pinching, pinch_position, is_three_finger,
    hand_center, finger_angle, lm_to_screen, pinch_distance,
)
from state import (
    HandState, CARD_COUNT, CARD_WIDTH, CARD_HEIGHT, CARD_SPACING,
    ROW_BASE_SPACING, CATEGORIES, NUM_CATEGORIES, WINDOW_WIDTH, WINDOW_HEIGHT,
)
from renderer import clamp, draw_cards, draw_wheel, draw_camera_thumbnail
from weather_window import WeatherWindow
from todo_window import TodoWindow
from sand_window import SandWindow


class App:
    """Top-level gesture carousel application."""

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Gesture Carousel")
        self.clock = pygame.time.Clock()
        self._last_frame_time = time.time()
        pygame.mixer.init()
        try:
            self._snd_select = pygame.mixer.Sound("select.mp3")
            self._snd_select.set_volume(0.5)
        except Exception:
            self._snd_select = None
            print("Warning: select.mp3 not found")
        try:
            self._snd_doublepinch = pygame.mixer.Sound("doublepinch.mp3")
            self._snd_doublepinch.set_volume(0.5)
        except Exception:
            self._snd_doublepinch = None
            print("Warning: doublepinch.mp3 not found")
        self.state = HandState()
        self.tracker = HandTracker()
        self._font_status = pygame.font.Font(None, 48)
        self._tap = None
        self._double_tap = None
        self._hand_lost_time = 0          # timestamp when hand was last lost
        self._hand_grace_period = 0.30    # seconds to keep state alive after losing tracking
        self._last_hand = None            # last valid hand landmarks
        self._weather = WeatherWindow(WINDOW_WIDTH, WINDOW_HEIGHT)
        self._todo = TodoWindow(WINDOW_WIDTH, WINDOW_HEIGHT)
        self._sand = SandWindow(WINDOW_WIDTH, WINDOW_HEIGHT)
        self._cur_thumb = (0, 0)
        self._cur_index = (0, 0)
        # Mouse input state (alternative to hand tracking)
        self._mouse_down = False
        self._mouse_down_pos = None
        self._mouse_down_time = 0.0
        self._mouse_last_click_time = 0.0

    @property
    def _any_app_visible(self):
        return self._weather.visible or self._todo.visible or self._sand.visible

    def _process_wheel(self, hand):
        st = self.state
        if not is_three_finger(hand):
            st.wheel_active = False
            st.last_finger_angle = None
            return
        if not st.wheel_active:
            hc = hand_center(hand)
            st.wheel_active = True
            st.wheel_center_x = int(hc.x * WINDOW_WIDTH)
            st.wheel_center_y = int(hc.y * WINDOW_HEIGHT)
            st.last_finger_angle = None
        ang = finger_angle(hand)
        if st.last_finger_angle is not None:
            diff = ang - st.last_finger_angle
            if diff > math.pi:
                diff -= 2 * math.pi
            elif diff < -math.pi:
                diff += 2 * math.pi
            st.wheel_angle = (st.wheel_angle + diff * 2) % (2 * math.pi)
            st.gui_scale = clamp(
                st.gui_scale + diff * st.gui_scale_sensitivity,
                st.gui_scale_min, st.gui_scale_max,
            )
        st.last_finger_angle = ang

    def _process_pinch(self, hand, pinch_now):
        st = self.state
        if st.wheel_active:
            st.reset_pinch()
            return
        pos = pinch_position(hand)
        if pinch_now and not st.pinch_prev:
            if pos:
                px, py = pos[0] * WINDOW_WIDTH, pos[1] * WINDOW_HEIGHT
                st.pinch_start_pos = (px, py)
                st.last_pinch_x, st.last_pinch_y = px, py
                st.is_pinching = True
                st.pinch_hold_start = time.time()
                st.scroll_unlocked = False
                # Immediate button tap for Sand on pinch-down
                if self._sand.visible and self._sand._in_ui_zone(px, py):
                    self._sand.handle_tap(px, py)
                    st._sand_btn_consumed = True
                else:
                    st._sand_btn_consumed = False
        elif pinch_now and st.pinch_prev and pos:
            px, py = pos[0] * WINDOW_WIDTH, pos[1] * WINDOW_HEIGHT
            px, py = st.pinch_smoother.update(px, py)
            if st.last_pinch_x is not None:
                dx, dy = px - st.last_pinch_x, py - st.last_pinch_y

                # Soft dead zone — scale down small movements instead of killing them
                if st.pinch_start_pos:
                    total_drift = math.hypot(px - st.pinch_start_pos[0], py - st.pinch_start_pos[1])
                    jitter_thresh = 6 if total_drift < st.movement_threshold else 3
                else:
                    jitter_thresh = 6
                adx, ady = abs(dx), abs(dy)
                if adx < jitter_thresh:
                    dx *= (adx / jitter_thresh) ** 2
                if ady < jitter_thresh:
                    dy *= (ady / jitter_thresh) ** 2

                if not st.scroll_unlocked:
                    if time.time() - st.pinch_hold_start >= st.pinch_hold_delay:
                        st.scroll_unlocked = True

                # Pinch-hold 1s to close app windows (generous drift allowance)
                # Skip if todo keyboard is open (user is typing)
                # Skip if Sand is open (Sand uses quit button only)
                if self._any_app_visible and not self._sand.visible and st.pinch_start_pos:
                    if not (self._todo.visible and self._todo._keyboard_open):
                        total = math.hypot(px - st.pinch_start_pos[0], py - st.pinch_start_pos[1])
                        if total <= 80 and time.time() - st.pinch_hold_start >= 1.0:
                            if self._weather.visible:
                                self._weather.close()
                                print("Closed weather window (pinch hold)")
                            elif self._todo.visible:
                                self._todo.close()
                                print("Closed todo window (pinch hold)")
                            st.reset_pinch()
                            return

                # Feed pinch to Sand app (pour/draw/erase)
                if self._sand.visible and st.pinch_start_pos:
                    total = math.hypot(px - st.pinch_start_pos[0], py - st.pinch_start_pos[1])
                    if total > 8:  # small dead zone
                        self._sand.handle_pinch(px, py)

                # Only scroll when no app window is open
                if not self._any_app_visible and st.scroll_unlocked and st.pinch_start_pos:
                    total = math.hypot(px - st.pinch_start_pos[0], py - st.pinch_start_pos[1])
                    if total > st.movement_threshold:
                        st.card_offset += dx * st.scroll_gain
                        st.category_offset += dy * st.scroll_gain
                        stride_x = int((CARD_WIDTH + CARD_SPACING) * st.gui_scale)
                        st.card_offset = clamp(st.card_offset, -(CARD_COUNT - 1) * stride_x, 0)
                        row_stride = int(ROW_BASE_SPACING * st.gui_scale)
                        st.category_offset = clamp(st.category_offset, -(NUM_CATEGORIES - 1) * row_stride, 0)
            st.last_pinch_x, st.last_pinch_y = px, py
        elif not pinch_now and st.pinch_prev:
            if st.pinch_start_pos and st.last_pinch_x is not None:
                total = math.hypot(
                    st.last_pinch_x - st.pinch_start_pos[0],
                    st.last_pinch_y - st.pinch_start_pos[1],
                )
                now = time.time()
                dt = now - st.last_pinch_time
                if total <= st.movement_threshold and not st.scroll_unlocked:
                    # Sand buttons were already handled on pinch-down
                    if self._sand.visible and getattr(st, '_sand_btn_consumed', False):
                        pass  # don't double-fire
                    else:
                        self._tap = st.pinch_start_pos
                    # Double-pinch detection (disabled in Sand)
                    if not self._sand.visible:
                        if 0.05 < dt < st.double_pinch_window:
                            self._double_tap = st.pinch_start_pos
                st.last_pinch_time = now
            st.reset_pinch()
            # Also end sand pinch tracking
            if self._sand.visible:
                self._sand.handle_pinch_end()

    def _resolve_taps(self, all_rects):
        st = self.state
        if self._tap:
            tx, ty = self._tap
            if self._todo.visible:
                self._todo.handle_tap(tx, ty, st.gui_scale)
            elif self._weather.visible:
                if not self._weather.hit_test(tx, ty, st.gui_scale):
                    self._weather.close()
                    print("Closed weather window")
            elif self._sand.visible:
                self._sand.handle_tap(tx, ty)
            else:
                for rect, ci, ca in all_rects:
                    if rect.collidepoint(tx, ty):
                        name = CATEGORIES[ca][ci]
                        if ci != st.selected_card or ca != st.selected_category:
                            if self._snd_select:
                                self._snd_select.play()
                        st.selected_card, st.selected_category = ci, ca
                        st.zoom_target = 1.0
                        print(f"Selected: {name} (card {ci}, category {ca})")
                        # Single tap opens apps directly
                        if name == "Weather":
                            self._weather.open()
                            if self._snd_doublepinch:
                                self._snd_doublepinch.play()
                            print("Opened weather window")
                        elif name == "Reminders":
                            self._todo.open()
                            if self._snd_doublepinch:
                                self._snd_doublepinch.play()
                            print("Opened todo window")
                        elif name == "Sand":
                            self._sand.open()
                            if self._snd_doublepinch:
                                self._snd_doublepinch.play()
                            print("Opened Sand")
                        break
            self._tap = None
        if self._double_tap:
            dx, dy = self._double_tap
            if self._todo.visible:
                if not self._todo._keyboard_open:
                    self._todo.close()
                    print("Closed todo window (double pinch)")
            elif self._weather.visible:
                self._weather.close()
                print("Closed weather window (double pinch)")
            self._double_tap = None

    def _draw(self, hand, pinch_now):
        st = self.state
        screen = self.screen
        screen.fill((20, 20, 30))

        # Delta-time for frame-rate independent smoothing
        now = time.time()
        dt = min(now - self._last_frame_time, 0.05)  # cap at 50ms to avoid jumps
        self._last_frame_time = now
        # Convert fixed alpha to dt-based: sm = 1 - (1 - base_alpha)^(dt * 60)
        sm = 1.0 - (1.0 - st.scroll_smoothing) ** (dt * 60.0)

        all_rects = []
        if self._sand.visible:
            self._sand.draw(screen, st.gui_scale)
        elif self._todo.visible:
            self._todo.draw(screen, st.gui_scale)
        elif self._weather.visible:
            self._weather.draw(screen, st.gui_scale)
        else:
            st.smooth_card_offset += (st.card_offset - st.smooth_card_offset) * sm
            st.smooth_category_offset += (st.category_offset - st.smooth_category_offset) * sm
            cx, cy = WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2
            row_stride = int(ROW_BASE_SPACING * st.gui_scale)
            first = max(0, int(-st.smooth_category_offset / row_stride) - 1)
            last = min(NUM_CATEGORIES, int((-st.smooth_category_offset + WINDOW_HEIGHT) / row_stride) + 2)
            for cat in range(first, last):
                y = cy + cat * row_stride + st.smooth_category_offset
                all_rects += draw_cards(
                    screen, cx, int(y), st.smooth_card_offset, cat,
                    st.selected_card, st.selected_category, st.zoom_progress,
                    WINDOW_WIDTH, st.gui_scale, CARD_WIDTH, CARD_HEIGHT, CARD_SPACING,
                )

        self._resolve_taps(all_rects)
        draw_wheel(screen, st, WINDOW_WIDTH, WINDOW_HEIGHT)

        # Camera thumbnail top-right
        frame = self.tracker.latest_frame()
        draw_camera_thumbnail(screen, frame, WINDOW_WIDTH, hand)

        if hand:
            tx, ty = self._cur_thumb
            ix, iy = self._cur_index
            if not st.wheel_active and pinch_now:
                pygame.draw.line(screen, (255, 255, 255), (int(tx), int(ty)), (int(ix), int(iy)), 2)
            pygame.draw.circle(screen, (255, 255, 255), (int(tx), int(ty)), 10)
            pygame.draw.circle(screen, (150, 150, 150), (int(ix), int(iy)), 5)
        else:
            st.finger_smoother.reset()
        pygame.display.flip()

    def run(self):
        print("=" * 50)
        print("GESTURE CAROUSEL STARTED")
        print("Pinch to select | Hold pinch to scroll | Three-finger wheel to zoom")
        print("=" * 50)
        self.tracker.start()
        st = self.state
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._shutdown()
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self._shutdown()
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_s:
                    if not self._sand.visible:
                        self._sand.open()
                        if self._snd_doublepinch:
                            self._snd_doublepinch.play()
                        print("Opened Sand (hotkey)")
                if event.type == pygame.MOUSEWHEEL and self._sand.visible:
                    self._sand.handle_scroll(-event.y)  # scroll up = prev, down = next
                # --- Mouse input (alternative to hand gestures) ---
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    now = time.time()
                    self._mouse_down = True
                    self._mouse_down_pos = (mx, my)
                    self._mouse_down_time = now
                    self._mouse_btn_consumed = False
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if self._mouse_down:
                        mx, my = event.pos
                        now = time.time()
                        # Release — check if it was a tap (small movement)
                        if self._mouse_down_pos:
                            total = math.hypot(mx - self._mouse_down_pos[0],
                                               my - self._mouse_down_pos[1])
                            if total <= 15:
                                if self._sand.visible:
                                    # Double-click only = line tool (no single-click action)
                                    if now - self._mouse_last_click_time < 0.4:
                                        self._sand.handle_double_click(mx, my)
                                self._mouse_last_click_time = now
                        if self._sand.visible:
                            self._sand.handle_pinch_end()
                        self._mouse_down = False
                        self._mouse_down_pos = None
                elif event.type == pygame.MOUSEMOTION and self._mouse_down:
                    mx, my = event.pos
                    if self._sand.visible and self._mouse_down_pos:
                        total = math.hypot(mx - self._mouse_down_pos[0],
                                           my - self._mouse_down_pos[1])
                        if total > 8:
                            self._sand.handle_pinch(mx, my)
            hand = self.tracker.latest()
            if hand is not None:
                self._last_hand = hand
                self._hand_lost_time = 0
                # Compute smoothed finger positions for visual rendering (dots)
                (tx, ty), (ix, iy) = st.finger_smoother.update(
                    lm_to_screen(hand[4], WINDOW_WIDTH, WINDOW_HEIGHT),
                    lm_to_screen(hand[8], WINDOW_WIDTH, WINDOW_HEIGHT),
                )
                self._cur_thumb = (tx, ty)
                self._cur_index = (ix, iy)
                # Pinch detection uses RAW (unaveraged) landmarks — zero lag
                # Hysteresis: easy to start (0.065), sticky to hold (release at 0.09)
                raw = self.tracker.latest_raw() or hand
                pdist = pinch_distance(raw)
                if st.pinch_prev:
                    pinch_now = pdist < st.pinch_release   # stay pinched until far apart
                else:
                    pinch_now = pdist < st.pinch_threshold  # start pinch when close
                self._process_wheel(hand)
                # Three-finger gesture in Sand = change color
                if self._sand.visible and is_three_finger(hand):
                    self._sand.random_color()
                self._process_pinch(hand, pinch_now)
            elif self._last_hand is not None:
                # Hand briefly lost — use grace period before resetting
                if self._hand_lost_time == 0:
                    self._hand_lost_time = time.time()
                elapsed = time.time() - self._hand_lost_time
                if elapsed < self._hand_grace_period:
                    # Keep last hand state alive; freeze pinch (don't move)
                    hand = self._last_hand
                    pinch_now = st.pinch_prev   # hold whatever state we had
                else:
                    # Grace period expired — truly lost
                    self._last_hand = None
                    self._hand_lost_time = 0
                    st.finger_smoother.reset()
                    st.wheel_active = False
                    st.last_finger_angle = None
                    if st.is_pinching:
                        st.reset_pinch()
                    pinch_now = False
                    hand = None
            else:
                st.finger_smoother.reset()
                st.wheel_active = False
                st.last_finger_angle = None
                pinch_now = False
            st.pinch_prev = pinch_now
            self._draw(hand, pinch_now)
            self.clock.tick(60)

    def _shutdown(self):
        self.tracker.stop()
        pygame.quit()


if __name__ == "__main__":
    App().run()