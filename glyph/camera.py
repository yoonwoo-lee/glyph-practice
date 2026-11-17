"""Where frames come from: a camera, a video file, or a list of still images."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


class CameraSource:
    """A live camera. On a Mac, an iPhone shows up here through Continuity Camera."""

    def __init__(self, index: int = 0, width: int = 1920, height: int = 1080) -> None:
        self.index = index
        self.width, self.height = width, height
        self.label = f"camera {index}"
        self.error: Optional[str] = None
        self._cap = None
        self._frame = None
        self._lock = threading.Lock()
        self._running = False

    def open(self) -> None:
        """Call this from the main thread: macOS asks for camera permission here."""
        cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            raise RuntimeError(
                f"Camera {self.index} did not open. Run `python run.py --list-cameras` to see which "
                "numbers work. On a Mac, also allow Terminal under System Settings > Privacy & "
                "Security > Camera, then run this again."
            )
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        frame = None
        for _ in range(40):
            ok, f = cap.read()
            if ok and f is not None:
                frame = f
                break
            time.sleep(0.1)
        if frame is None:
            cap.release()
            raise RuntimeError(
                f"Camera {self.index} opened but sent no picture. If macOS just asked for camera "
                "permission, allow it and run this again."
            )
        self._cap, self._frame = cap, frame
        print(f"[glyph] camera {self.index}: {frame.shape[1]}x{frame.shape[0]}")

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        fails = 0
        while self._running:
            ok, frame = self._cap.read()
            if not ok or frame is None:
                fails += 1
                if fails > 100:
                    self.error = "The camera stopped sending pictures."
                time.sleep(0.05)
                continue
            fails, self.error = 0, None
            with self._lock:
                self._frame = frame

    def read(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._frame

    def stop(self) -> None:
        self._running = False
        thread = getattr(self, "_thread", None)
        if thread is not None:
            thread.join(timeout=2)
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class FrameListSource:
    """Still images shown one after another, as if a camera were watching them.

    Used for the built-in demo, for tests, and for replaying a folder of photos.
    """

    def __init__(self, frames: List[np.ndarray], hold: float = 7.0, label: str = "images") -> None:
        if not frames:
            raise RuntimeError("No images to show.")
        self.frames = frames
        self.hold = hold
        self.label = label
        self.error: Optional[str] = None
        self._t0 = time.time()

    def open(self) -> None:
        pass

    def start(self) -> None:
        self._t0 = time.time()

    def read(self) -> Optional[np.ndarray]:
        i = int((time.time() - self._t0) / self.hold)
        return self.frames[min(i, len(self.frames) - 1)]

    def stop(self) -> None:
        pass


class VideoFileSource(CameraSource):
    """A recorded video played at normal speed, holding on the last frame."""

    def __init__(self, path: Path) -> None:
        super().__init__(0)
        self.path = Path(path)
        self.label = self.path.name

    def open(self) -> None:
        cap = cv2.VideoCapture(str(self.path))
        ok, frame = cap.read()
        if not ok or frame is None:
            raise RuntimeError(f"Could not read video {self.path}")
        self._cap, self._frame = cap, frame
        fps = cap.get(cv2.CAP_PROP_FPS)
        self._delay = 1.0 / fps if fps and fps > 1 else 1.0 / 30

    def _run(self) -> None:
        while self._running:
            ok, frame = self._cap.read()
            if not ok or frame is None:
                time.sleep(0.2)
                continue
            with self._lock:
                self._frame = frame
            time.sleep(self._delay)


def source_from_path(path: str, hold: float = 7.0):
    """A folder of images, one image, or a video file."""
    p = Path(path).expanduser()
    if p.is_dir():
        files = sorted(f for f in p.iterdir() if f.suffix.lower() in IMAGE_EXTS)
        frames = [img for img in (cv2.imread(str(f)) for f in files) if img is not None]
        return FrameListSource(frames, hold=hold, label=p.name)
    if p.suffix.lower() in IMAGE_EXTS:
        img = cv2.imread(str(p))
        if img is None:
            raise RuntimeError(f"Could not read image {p}")
        return FrameListSource([img], hold=hold, label=p.name)
    if p.exists():
        return VideoFileSource(p)
    raise RuntimeError(f"Nothing found at {p}")


def list_cameras(out_dir: Path, max_index: int = 5) -> None:
    """Save one photo from every camera so you can see which number is the phone."""
    out_dir.mkdir(parents=True, exist_ok=True)
    found = 0
    for i in range(max_index + 1):
        cap = cv2.VideoCapture(i)
        if not cap.isOpened():
            cap.release()
            continue
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        frame = None
        for _ in range(25):
            ok, f = cap.read()
            if ok and f is not None:
                frame = f
            time.sleep(0.05)
        cap.release()
        if frame is None:
            print(f"camera {i}: opened, but no picture (check camera permission)")
            continue
        path = out_dir / f"camera_{i}.jpg"
        cv2.imwrite(str(path), frame)
        print(f"camera {i}: {frame.shape[1]}x{frame.shape[0]}  ->  {path}")
        found += 1
    if not found:
        print(
            "No camera gave a picture. On a Mac: System Settings > Privacy & Security > Camera, "
            "allow Terminal, then run this again."
        )
    else:
        print(f"\nOpen the photos in {out_dir} and start Glyph with the number that shows your desk:")
        print("    bash start.sh --camera <number>")
