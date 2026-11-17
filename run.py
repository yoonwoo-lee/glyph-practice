"""Start Glyph.

    python run.py                  watch camera 0
    python run.py --camera 1       watch another camera (your iPhone is often 1)
    python run.py --list-cameras   save a photo from every camera to camera_check/
    python run.py --demo           no camera: play a simulated sheet of paper
    python run.py --source PATH    replay a video, a photo, or a folder of photos
    python run.py --mock           fake answers, no vision-model calls
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import warnings
import webbrowser

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*OpenSSL.*")


def main() -> int:
    ap = argparse.ArgumentParser(description="Glyph practice build")
    ap.add_argument("--camera", type=int, default=0, help="camera number (default 0)")
    ap.add_argument("--list-cameras", action="store_true", help="save a photo from each camera and exit")
    ap.add_argument("--demo", action="store_true", help="simulated paper instead of a camera")
    ap.add_argument("--source", help="video file, image, or folder of images to replay")
    ap.add_argument("--hold", type=float, default=7.0, help="seconds per image for --demo / image folders")
    ap.add_argument("--mock", action="store_true", help="fake answers instead of the vision model")
    ap.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270], help="turn the page view")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="[glyph] %(message)s")

    from glyph import config
    from glyph.camera import CameraSource, FrameListSource, list_cameras, source_from_path

    if args.list_cameras:
        list_cameras(config.ROOT / "camera_check")
        return 0

    import uvicorn

    from glyph.app import create_app
    from glyph.brain import Brain, BrainError, MockBrain
    from glyph.engine import Engine
    from glyph.session import Session

    try:
        if args.demo:
            from glyph.demo import demo_frames

            source = FrameListSource(demo_frames(), hold=args.hold, label="demo")
        elif args.source:
            source = source_from_path(args.source, hold=args.hold)
        else:
            source = CameraSource(args.camera)
        source.open()  # main thread, so macOS can ask for camera permission
    except RuntimeError as e:
        print(f"\n[glyph] {e}\n")
        return 1

    legend = config.load_legend()
    brain = None
    if not args.mock:
        try:
            brain = Brain(legend)
        except BrainError as e:
            print(f"[glyph] {e}. Running with fake answers instead.")
    if brain is None:
        brain = MockBrain(legend)

    session = Session(config.ROOT / "sessions")
    engine = Engine(source, brain, session, legend, rotate=args.rotate // 90)
    source.start()
    engine.start()

    url = f"http://127.0.0.1:{args.port}"
    print(f"[glyph] answers: {brain.name}   session files: {session.dir}")
    print(f"[glyph] open {url}   (Ctrl+C to stop)")
    if not args.no_browser and not os.getenv("GLYPH_NO_BROWSER"):
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        uvicorn.run(create_app(engine), host="127.0.0.1", port=args.port, log_level="warning", timeout_graceful_shutdown=1)
    finally:
        engine.stop()
        source.stop()
    print("[glyph] stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
