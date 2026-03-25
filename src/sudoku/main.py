"""Sudoku offline app - FastAPI server with puzzle generation."""

from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dokusan import generators, solvers

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Sudoku Offline", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def index() -> FileResponse:
    """Serve the main page."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/puzzle")
async def get_puzzle(rank: int = Query(default=150, ge=50, le=500)) -> dict[str, str | int]:
    """Generate a new Sudoku puzzle with solution.

    rank controls difficulty: ~150 is medium, ~300 is hard.
    """
    grid = generators.random_sudoku(avg_rank=rank)
    solution = solvers.backtrack(grid)

    return {
        "initial_grid": str(grid),
        "solution_key": str(solution),
        "difficulty": rank,
    }


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
