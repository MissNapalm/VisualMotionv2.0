"""
Face tracking — MediaPipe FaceLandmarker for head-movement cursor control.

Tracks the nose tip (landmark 1) to drive a screen cursor.
Runs in a background daemon thread, sharing the camera frame
from the HandTracker (to avoid opening a second camera).
"""
import os
import threading
import time
import math
import cv2
import numpy as np

import mediapipe as mp
from mediapipe.tasks.python.vision import face_landmarker as fl
from mediapipe.tasks.python.vision.core import image as mp_image
from mediapipe.tasks.python.core import base_options as mp_base_options


def _find_model():
    proj = os.path.dirname(os.path.abspath(__file__))
    c = os.path.join(proj, "face_landmarker.task")
    if os.path.isfile(c):
        return c
    raise FileNotFoundError("Could not find face_landmarker.task")


class _FLandmark:
    __slots__ = ("x", "y", "z")
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z


class FaceTracker:
    """Lightweight face tracker — extracts nose-tip position from shared camera frames."""

    def __init__(self):
        model_path = _find_model()
        options = fl.FaceLandmarkerOptions(
            base_options=mp_base_options.BaseOptions(model_asset_path=model_path),
            num_faces=1,
            min_face_detection_confidence=0.4,
            min_face_presence_confidence=0.4,
            min_tracking_confidence=0.4,
        )
        self._detector = fl.FaceLandmarker.create_from_options(options)
        self._lock = threading.Lock()

        # Smoothed nose position (normalised 0..1)
        self._nose_x: float | None = None
        self._nose_y: float | None = None
        self._raw_nose_x: float | None = None
        self._raw_nose_y: float | None = None
        self._face_detected: bool = False

        # Rolling average for stability
        self._history: list[tuple[float, float]] = []
        self._avg_window = 5  # more averaging than hand (head moves slower)

        # Background thread state
        self._running = False
        self._thread: threading.Thread | None = None
        self._hand_tracker = None  # reference to HandTracker for shared frames

    def start(self, hand_tracker):
        """Start background detection loop, sharing camera frames from hand_tracker."""
        self._hand_tracker = hand_tracker
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def detected(self) -> bool:
        with self._lock:
            return self._face_detected

    def nose_position(self) -> tuple[float, float] | None:
        """Return smoothed (x, y) normalised nose position, or None."""
        with self._lock:
            if self._nose_x is None:
                return None
            return (self._nose_x, self._nose_y)

    def raw_nose_position(self) -> tuple[float, float] | None:
        """Unaveraged nose position for immediate response."""
        with self._lock:
            if self._raw_nose_x is None:
                return None
            return (self._raw_nose_x, self._raw_nose_y)

    def _loop(self):
        while self._running:
            frame = None
            if self._hand_tracker:
                frame = self._hand_tracker.latest_frame()
            if frame is None:
                time.sleep(0.03)
                continue

            try:
                mp_img = mp_image.Image(
                    image_format=mp_image.ImageFormat.SRGB, data=frame
                )
                result = self._detector.detect(mp_img)
            except Exception:
                time.sleep(0.03)
                continue

            if result.face_landmarks and len(result.face_landmarks) > 0:
                face = result.face_landmarks[0]
                # Nose tip = landmark index 1
                nose = face[1]
                rx, ry = nose.x, nose.y

                self._history.append((rx, ry))
                if len(self._history) > self._avg_window:
                    self._history.pop(0)
                n = len(self._history)
                ax = sum(h[0] for h in self._history) / n
                ay = sum(h[1] for h in self._history) / n

                with self._lock:
                    self._nose_x = ax
                    self._nose_y = ay
                    self._raw_nose_x = rx
                    self._raw_nose_y = ry
                    self._face_detected = True
            else:
                self._history.clear()
                with self._lock:
                    self._nose_x = None
                    self._nose_y = None
                    self._raw_nose_x = None
                    self._raw_nose_y = None
                    self._face_detected = False

            # Run at ~20 Hz (face doesn't need 60 Hz)
            time.sleep(0.05)
