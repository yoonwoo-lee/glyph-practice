"""The local web page: live view of the paper, the feed, and the study guide."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

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

    @app.get("/api/state")
    def state(since: int = 0):
        events = engine.session.events_since(since)
        return JSONResponse(
            {
                "status": engine.status(),
                "events": events,
                "last_id": events[-1]["id"] if events else since,
                "legend": engine.legend,
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

    @app.get("/api/highlight/{highlight_id}.jpg")
    def highlight(highlight_id: int):
        for r in engine.store.all():
            if r["id"] == highlight_id:
                try:
                    return Response(r["path"].read_bytes(), media_type="image/jpeg")
                except OSError:
                    break
        raise HTTPException(404)

    return app
