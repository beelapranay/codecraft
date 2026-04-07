from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from craftcode import analyze_target

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Craftcode",
    description="Web application for repository code quality reviews.",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class AnalyzeRequest(BaseModel):
    target: str


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "home.html", {"page_name": "home"})


@app.get("/analyze", response_class=HTMLResponse)
def analyze_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "analyze.html", {"page_name": "analyze"})


@app.get("/report", response_class=HTMLResponse)
def report_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "report.html", {"page_name": "report"})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze")
def analyze(payload: AnalyzeRequest) -> JSONResponse:
    target = payload.target.strip()
    if not target:
        raise HTTPException(status_code=400, detail="A GitHub URL or local path is required.")

    try:
        report = analyze_target(target)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotADirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive HTTP wrapper
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc

    return JSONResponse(report)
