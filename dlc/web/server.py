"""
FastAPI app for the Digital Lab Coach local web UI.

Run with: `uv run python -m dlc.web.server`.

Endpoints:
  GET  /                       index.html
  GET  /static/...             JS, CSS, images
  POST /api/circuit            multipart .dig upload; returns
                               {"graph": ..., "summary": ...}
  GET  /api/health             readiness probe
"""
from pathlib import Path
import tempfile

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dlc.parser.dig_parser import parse_dig_file
from dlc.parser.graph import build_signal_graph
from dlc.parser.netlist import build_netlist
from dlc.web.graph_export import circuit_summary, to_cytoscape


STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Digital Lab Coach", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/circuit")
async def circuit(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.endswith(".dig"):
        raise HTTPException(status_code=400, detail="Please upload a .dig file.")

    with tempfile.NamedTemporaryFile(
        suffix=".dig", delete=False, mode="wb"
    ) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        c = parse_dig_file(tmp_path)
        nl = build_netlist(c)
        g = build_signal_graph(c, nl)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse circuit: {type(exc).__name__}: {exc}",
        )

    return {
        "filename": file.filename,
        "graph": to_cytoscape(c, nl, g),
        "summary": circuit_summary(c, nl),
    }


def main() -> None:
    import uvicorn
    uvicorn.run(
        "dlc.web.server:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()