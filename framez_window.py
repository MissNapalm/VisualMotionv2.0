"""
Framez — fullscreen face wireframe app.
Black background with a neon wireframe of your face.
Pinch-hold 1s to exit.
"""
import pygame


# MediaPipe face mesh tessellation — key contour connections
# Full mesh has 468 points. We draw the main contours for a clean wireframe look.
_FACE_OVAL = [
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
    397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
    172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109, 10,
]

_LEFT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246, 33]
_RIGHT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398, 362]
_LEFT_EYEBROW = [70, 63, 105, 66, 107, 55, 65, 52, 53, 46]
_RIGHT_EYEBROW = [300, 293, 334, 296, 336, 285, 295, 282, 283, 276]
_NOSE_BRIDGE = [168, 6, 197, 195, 5, 4, 1, 19, 94, 2]
_NOSE_BOTTOM = [98, 240, 235, 219, 218, 237, 44, 1, 274, 457, 438, 439, 455, 460, 328]
_OUTER_LIPS = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185, 61]
_INNER_LIPS = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191, 78]

_FACE_COLOR = (0, 255, 180)       # neon green
_EYE_COLOR = (0, 200, 255)        # cyan
_BROW_COLOR = (180, 120, 255)     # purple
_NOSE_COLOR = (255, 200, 80)      # warm yellow
_LIP_COLOR = (255, 80, 120)       # pink
_LIP_INNER_COLOR = (255, 50, 80)


class FramezWindow:
    def __init__(self, window_width, window_height):
        self.visible = False
        self._ww = window_width
        self._wh = window_height

    def open(self):
        self.visible = True

    def close(self):
        self.visible = False

    def _draw_contour(self, surface, landmarks, indices, color, width=1, closed=False):
        if landmarks is None or len(landmarks) < 468:
            return
        points = []
        for idx in indices:
            if idx < len(landmarks):
                lm = landmarks[idx]
                px = int(lm.x * self._ww)
                py = int(lm.y * self._wh)
                points.append((px, py))
        if len(points) >= 2:
            pygame.draw.lines(surface, color, closed, points, width)

    def draw(self, surface, gui_scale, face_landmarks=None):
        surface.fill((0, 0, 0))

        if face_landmarks is None or len(face_landmarks) < 468:
            font = pygame.font.Font(None, max(24, int(48 * gui_scale)))
            msg = font.render("Looking for face...", True, (60, 60, 60))
            surface.blit(msg, msg.get_rect(center=(self._ww // 2, self._wh // 2)))

            title = font.render("FRAMEZ", True, (0, 255, 180))
            surface.blit(title, title.get_rect(center=(self._ww // 2, int(60 * gui_scale))))
            return

        lw = max(1, int(2 * gui_scale))

        # Face oval
        self._draw_contour(surface, face_landmarks, _FACE_OVAL, _FACE_COLOR, lw)

        # Eyes
        self._draw_contour(surface, face_landmarks, _LEFT_EYE, _EYE_COLOR, lw)
        self._draw_contour(surface, face_landmarks, _RIGHT_EYE, _EYE_COLOR, lw)

        # Eyebrows
        self._draw_contour(surface, face_landmarks, _LEFT_EYEBROW, _BROW_COLOR, lw)
        self._draw_contour(surface, face_landmarks, _RIGHT_EYEBROW, _BROW_COLOR, lw)

        # Nose
        self._draw_contour(surface, face_landmarks, _NOSE_BRIDGE, _NOSE_COLOR, lw)
        self._draw_contour(surface, face_landmarks, _NOSE_BOTTOM, _NOSE_COLOR, lw)

        # Lips
        self._draw_contour(surface, face_landmarks, _OUTER_LIPS, _LIP_COLOR, lw)
        self._draw_contour(surface, face_landmarks, _INNER_LIPS, _LIP_INNER_COLOR, lw)

        # Draw landmark dots on key features for glow effect
        dot_indices = set(_FACE_OVAL + _LEFT_EYE + _RIGHT_EYE)
        for idx in dot_indices:
            if idx < len(face_landmarks):
                lm = face_landmarks[idx]
                px = int(lm.x * self._ww)
                py = int(lm.y * self._wh)
                pygame.draw.circle(surface, _FACE_COLOR, (px, py), 1)

        # Title
        font = pygame.font.Font(None, max(20, int(32 * gui_scale)))
        title = font.render("FRAMEZ", True, (0, 255, 180))
        surface.blit(title, (int(20 * gui_scale), int(20 * gui_scale)))

        hint = pygame.font.Font(None, max(16, int(24 * gui_scale))).render(
            "pinch hold 1s to exit", True, (50, 50, 50))
        surface.blit(hint, (int(20 * gui_scale), self._wh - int(40 * gui_scale)))
