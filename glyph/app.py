"""The local web page: live view of the paper, the feed, and the study guide."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from . import tune
from .engine import Engine

STATIC = Path(__file__).resolve().parent / "static"


def create_app(engine: Engine) -> FastAPI:
    app = FastAPI(title="Glyph", docs_url=None, redoc_url=None)

    @app.on_event("shutdown")
    def _shutdown() -> None:
        engine.stop()

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})

    def _stream(which: str):
        last = b""
        while engine.running:
            jpg = engine.jpg(which)
            if jpg and jpg is not last:
                last = jpg
                yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"
            time.sleep(0.1)

    @app.get("/stream/{which}")
    def stream(which: str):
        if which not in ("page", "raw"):
            raise HTTPException(404)
        return StreamingResponse(_stream(which), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.get("/api/frame/{which}.jpg")
    def frame(which: str):
        """One picture at a time. The web page asks for these in a loop: unlike a never-ending
        MJPEG stream, this cannot freeze when the views are swapped, and it works in Safari."""
        if which not in ("page", "raw"):
            raise HTTPException(404)
        jpg = engine.live_raw_jpg() if which == "raw" else engine.jpg("page")
        if not jpg:
            raise HTTPException(503)
        return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/state")
    def state(since: int = 0):
        events = engine.session.events_since(since)
        return JSONResponse(
            {
                "status": engine.status(),
                "events": events,
                "last_id": events[-1]["id"] if events else since,
                "legend": engine.legend,
                "timings": engine.session.timings()[-1:],
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/look")
    def look():
        engine.look_now()
        return {"ok": True}

    @app.post("/api/rotate")
    def rotate():
        return {"ok": True, "degrees": engine.rotate()}

    @app.post("/api/study-guide")
    def study_guide():
        try:
            return {"ok": True, "markdown": engine.study_guide()}
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)[:300]}, status_code=502)

    @app.get("/api/snip/{n}.jpg")
    def snip(n: int):
        path = engine.session.snip_path(n)
        if not path.exists():
            raise HTTPException(404)
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/api/highlight/{highlight_id}.jpg")
    def highlight(highlight_id: int):
        for r in engine.store.all():
            if r["id"] == highlight_id:
                try:
                    return Response(r["path"].read_bytes(), media_type="image/jpeg")
                except OSError:
                    break
        raise HTTPException(404)

    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

    # ---- tuning page -----------------------------------------------------------

    @app.get("/tune")
    def tune_page():
        return FileResponse(STATIC / "tune.html", headers={"Cache-Control": "no-store"})

    @app.get("/api/tune")
    def tune_get():
        return {"values": tune.values(engine), "sliders": tune.SLIDERS, "status": engine.status()}

    @app.post("/api/tune")
    def tune_set(body: dict = Body(...)):
        return {"values": tune.apply(engine, body)}

    @app.get("/api/tune/view/{which}.jpg")
    def tune_view(which: str):
        if which not in ("page", "ink", "highlights", "cover"):
            raise HTTPException(404)
        return Response(tune.render(engine, which), media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.post("/api/tune/probe")
    def tune_probe(body: dict = Body(...)):
        page = engine.last_page()
        if page is None:
            raise HTTPException(409, "no picture yet")
        hsv = tune.probe(page, float(body.get("x", 0.5)), float(body.get("y", 0.5)))
        return {"hsv": hsv, "fit": tune.fit(str(body.get("color", "")), hsv)}

    @app.post("/api/tune/save")
    def tune_save():
        try:
            return {"ok": True, "saved": tune.save_env(engine)}
        except OSError as e:
            return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=500)

    return app
