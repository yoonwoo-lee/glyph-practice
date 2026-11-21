"""Start Glyph.

    python run.py                  watch the camera that sees a sheet of paper (--camera auto)
    python run.py --camera 1       watch one particular camera
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
    ap.add_argument("--camera", default="auto", help="camera number, or auto (default): the one that sees a sheet of paper")
    ap.add_argument("--list-cameras", action="store_true", help="save a photo from each camera and exit")
    ap.add_argument("--demo", action="store_true", help="simulated paper instead of a camera")
    ap.add_argument("--source", help="video file, image, or folder of images to replay")
    ap.add_argument("--hold", type=float, default=7.0, help="seconds per image for --demo / image folders")
    ap.add_argument("--mock", action="store_true", help="fake answers instead of the vision model")
    ap.add_argument("--rotate", type=int, default=None, choices=[0, 90, 180, 270], help="turn the page view (default: as it was last turned with the Rotate button)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="[glyph] %(message)s")

    from glyph import config
    from glyph.camera import WIDE_HELP, CameraSource, FrameListSource, list_cameras, pick_camera, source_from_path

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
            from glyph.camera import DemoSource
            from glyph.demo import demo_frames

            # One sheet per mode; the button on the web page swaps them.
            modes = [m["id"] for m in config.modes_of(config.load_legend())] or ["student"]
            start = config.START_MODE if config.START_MODE in modes else modes[0]
            source = DemoSource({m: demo_frames(m) for m in modes}, start, hold=args.hold)
        elif args.source:
            source = source_from_path(args.source, hold=args.hold)
        else:
            if str(args.camera).strip().lower() == "auto":
                number = pick_camera(say=lambda text: print(f"[glyph] {text}", flush=True))
            else:
                number = int(args.camera)
            source = CameraSource(number)
            print(f"[glyph] {WIDE_HELP}")
        source.open()  # main thread, so macOS can ask for camera permission
    except (RuntimeError, ValueError) as e:
        print(f"\n[glyph] {e}\n")
        return 1
    except KeyboardInterrupt:
        print("\n[glyph] stopped")
        return 1

    legend = config.load_legend()
    brain = None
    if not args.mock:
        try:
            brain = Brain(legend)
        except BrainError as e:
            print(f"[glyph] {e}. Running with practice answers instead.")
    if brain is None:
        brain = MockBrain(legend, demo=args.demo)

    session = Session(config.ROOT / "sessions")
    turn = args.rotate
    if turn is None:
        turn = 0 if (args.demo or args.source) else config.saved_rotation()
        if turn:
            print(f"[glyph] page view turned {turn} degrees, as last time (the Rotate button changes it)")
    engine = Engine(source, brain, session, legend, rotate=turn // 90)
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
