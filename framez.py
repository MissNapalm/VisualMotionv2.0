"""
Framez — standalone face wireframe viewer.

Black screen with a real-time face mesh topology drawn as a neon wireframe.
Uses MediaPipe Face Landmarker (468 points, full tessellation).

Run:  python framez.py
Press ESC or close the window to quit.
"""

import os
import sys
import threading
import time

import cv2
import pygame
import mediapipe as mp
from mediapipe.tasks.python.vision import face_landmarker
from mediapipe.tasks.python.vision.face_landmarker import (
    FaceLandmarker,
    FaceLandmarkerOptions,
    FaceLandmarksConnections,
)
from mediapipe.tasks.python.vision.core import image as mp_image
from mediapipe.tasks.python.core import base_options as mp_base_options

# ──────────────────────────────────────────
# Config
# ──────────────────────────────────────────
WIDTH, HEIGHT = 1400, 800
FPS = 60
CAM_W, CAM_H = 640, 480

# ──────────────────────────────────────────
# Mesh topology — MediaPipe's full tessellation (2556 edges)
# ──────────────────────────────────────────
_TESS = [(c.start, c.end) for c in FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION]

# Feature contours for colour-coding
_FACE_OVAL_SET = {c.start for c in FaceLandmarksConnections.FACE_LANDMARKS_FACE_OVAL} | \
                 {c.end   for c in FaceLandmarksConnections.FACE_LANDMARKS_FACE_OVAL}
_LEFT_EYE_SET  = {c.start for c in FaceLandmarksConnections.FACE_LANDMARKS_LEFT_EYE} | \
                 {c.end   for c in FaceLandmarksConnections.FACE_LANDMARKS_LEFT_EYE}
_RIGHT_EYE_SET = {c.start for c in FaceLandmarksConnections.FACE_LANDMARKS_RIGHT_EYE} | \
                 {c.end   for c in FaceLandmarksConnections.FACE_LANDMARKS_RIGHT_EYE}
_LIPS_SET      = {c.start for c in FaceLandmarksConnections.FACE_LANDMARKS_LIPS} | \
                 {c.end   for c in FaceLandmarksConnections.FACE_LANDMARKS_LIPS}
_NOSE_SET      = {c.start for c in FaceLandmarksConnections.FACE_LANDMARKS_NOSE} | \
                 {c.end   for c in FaceLandmarksConnections.FACE_LANDMARKS_NOSE}
_L_BROW_SET    = {c.start for c in FaceLandmarksConnections.FACE_LANDMARKS_LEFT_EYEBROW} | \
                 {c.end   for c in FaceLandmarksConnections.FACE_LANDMARKS_LEFT_EYEBROW}
_R_BROW_SET    = {c.start for c in FaceLandmarksConnections.FACE_LANDMARKS_RIGHT_EYEBROW} | \
                 {c.end   for c in FaceLandmarksConnections.FACE_LANDMARKS_RIGHT_EYEBROW}
_L_IRIS_SET    = {c.start for c in FaceLandmarksConnections.FACE_LANDMARKS_LEFT_IRIS} | \
                 {c.end   for c in FaceLandmarksConnections.FACE_LANDMARKS_LEFT_IRIS}
_R_IRIS_SET    = {c.start for c in FaceLandmarksConnections.FACE_LANDMARKS_RIGHT_IRIS} | \
                 {c.end   for c in FaceLandmarksConnections.FACE_LANDMARKS_RIGHT_IRIS}

# Colours
COL_MESH   = (0, 255, 180, 40)    # neon green (faint for tess)
COL_OVAL   = (0, 255, 180)        # green
COL_EYE    = (0, 200, 255)        # cyan
COL_IRIS   = (120, 220, 255)      # bright cyan
COL_BROW   = (180, 120, 255)      # purple
COL_NOSE   = (255, 200, 80)       # yellow
COL_LIPS   = (255, 80, 120)       # pink
COL_DEFAULT = (0, 180, 120)       # dim green


def _edge_color(a, b):
    """Pick a colour for an edge based on which facial feature it belongs to."""
    if a in _L_IRIS_SET and b in _L_IRIS_SET:
        return COL_IRIS
    if a in _R_IRIS_SET and b in _R_IRIS_SET:
        return COL_IRIS
    if a in _LEFT_EYE_SET and b in _LEFT_EYE_SET:
        return COL_EYE
    if a in _RIGHT_EYE_SET and b in _RIGHT_EYE_SET:
        return COL_EYE
    if a in _L_BROW_SET and b in _L_BROW_SET:
        return COL_BROW
    if a in _R_BROW_SET and b in _R_BROW_SET:
        return COL_BROW
    if a in _LIPS_SET and b in _LIPS_SET:
        return COL_LIPS
    if a in _NOSE_SET and b in _NOSE_SET:
        return COL_NOSE
    if a in _FACE_OVAL_SET and b in _FACE_OVAL_SET:
        return COL_OVAL
    return COL_DEFAULT


def _vertex_color(i):
    """Pick dot colour for a vertex."""
    if i in _L_IRIS_SET or i in _R_IRIS_SET:
        return COL_IRIS
    if i in _LEFT_EYE_SET or i in _RIGHT_EYE_SET:
        return COL_EYE
    if i in _LIPS_SET:
        return COL_LIPS
    if i in _NOSE_SET:
        return COL_NOSE
    if i in _L_BROW_SET or i in _R_BROW_SET:
        return COL_BROW
    return None  # don't draw dots for generic mesh verts


# Pre-compute edge colours so we don't recalculate every frame
_EDGE_COLORS = [_edge_color(a, b) for a, b in _TESS]


# ──────────────────────────────────────────
# Find model file
# ──────────────────────────────────────────
def _find_face_model():
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(here, "face_landmarker.task")
    if os.path.isfile(candidate):
        return candidate
    raise FileNotFoundError(
        "face_landmarker.task not found.\n"
        "Download from: https://storage.googleapis.com/mediapipe-models/"
        "face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
    )


# ──────────────────────────────────────────
# Threaded camera + face detection
# ──────────────────────────────────────────
class _FaceTracker:
    def __init__(self):
        model_path = _find_face_model()
        options = FaceLandmarkerOptions(
            base_options=mp_base_options.BaseOptions(model_asset_path=model_path),
            num_faces=1,
            min_face_detection_confidence=0.4,
            min_face_presence_confidence=0.4,
            min_tracking_confidence=0.4,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        self._detector = FaceLandmarker.create_from_options(options)
        self._lock = threading.Lock()
        self._landmarks = None
        self._running = False
        self._thread = None
        self._cap = None

    def start(self):
        self._cap = cv2.VideoCapture(0)
        if not self._cap.isOpened():
            raise RuntimeError("Could not open camera")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_W)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._cap:
            self._cap.release()

    def latest(self):
        with self._lock:
            return self._landmarks

    def _loop(self):
        while self._running:
            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.005)
                continue
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = mp_image.Image(image_format=mp_image.ImageFormat.SRGB, data=rgb)
            result = self._detector.detect(img)
            landmarks = None
            if result.face_landmarks:
                landmarks = result.face_landmarks[0]
            with self._lock:
                self._landmarks = landmarks
            time.sleep(0.001)


# ──────────────────────────────────────────
# Main app
# ──────────────────────────────────────────
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Framez — Face Wireframe")
    clock = pygame.time.Clock()
    font_title = pygame.font.Font(None, 52)
    font_hint = pygame.font.Font(None, 28)
    font_waiting = pygame.font.Font(None, 40)

    tracker = _FaceTracker()
    tracker.start()

    print("=" * 44)
    print("  FRAMEZ — face wireframe viewer")
    print("  Press ESC or close window to quit")
    print("=" * 44)

    # Pre-build a surface for the faint mesh lines (semi-transparent)
    mesh_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        screen.fill((0, 0, 0))
        landmarks = tracker.latest()

        if landmarks is None or len(landmarks) < 468:
            # Waiting screen
            msg = font_waiting.render("Looking for face...", True, (50, 50, 50))
            screen.blit(msg, msg.get_rect(center=(WIDTH // 2, HEIGHT // 2)))
        else:
            # Map normalised landmarks → screen coordinates
            # Camera is 4:3 — fit into window preserving aspect ratio
            cam_aspect = CAM_W / CAM_H    # 4:3 = 1.333
            win_aspect = WIDTH / HEIGHT    # 1400/800 = 1.75
            if win_aspect > cam_aspect:
                # Window is wider than camera — fit to height, center horizontally
                fit_h = HEIGHT
                fit_w = int(HEIGHT * cam_aspect)
            else:
                # Window is taller than camera — fit to width, center vertically
                fit_w = WIDTH
                fit_h = int(WIDTH / cam_aspect)
            ox = (WIDTH - fit_w) // 2
            oy = (HEIGHT - fit_h) // 2
            pts = [(int(ox + lm.x * fit_w), int(oy + lm.y * fit_h)) for lm in landmarks]

            WHITE = (255, 255, 255)
            WIRE  = (180, 180, 180)

            # Draw all tessellation edges as white wireframe
            for a, b in _TESS:
                pygame.draw.line(screen, WIRE, pts[a], pts[b], 1)

            # Draw a dot on every single vertex (all 468)
            for pt in pts:
                pygame.draw.circle(screen, WHITE, pt, 2)

        # Title
        title = font_title.render("FRAMEZ", True, (255, 255, 255))
        screen.blit(title, (24, 18))

        # Hint
        hint = font_hint.render("ESC to quit", True, (40, 40, 40))
        screen.blit(hint, (24, HEIGHT - 38))

        pygame.display.flip()
        clock.tick(FPS)

    tracker.stop()
    pygame.quit()


if __name__ == "__main__":
    main()
