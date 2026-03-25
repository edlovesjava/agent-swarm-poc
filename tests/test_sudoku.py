"""Tests for the Sudoku app."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.sudoku.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_get_puzzle(client: AsyncClient) -> None:
    async with client:
        resp = await client.get("/puzzle?rank=150")
    assert resp.status_code == 200
    data = resp.json()
    assert "initial_grid" in data
    assert "solution_key" in data
    assert len(data["initial_grid"]) == 81
    assert len(data["solution_key"]) == 81
    assert "0" not in data["solution_key"]


@pytest.mark.asyncio
async def test_puzzle_solution_matches(client: AsyncClient) -> None:
    async with client:
        resp = await client.get("/puzzle?rank=100")
    data = resp.json()
    puzzle = data["initial_grid"]
    solution = data["solution_key"]
    # Every non-zero digit in the puzzle must match the solution
    for i in range(81):
        if puzzle[i] != "0":
            assert puzzle[i] == solution[i], f"Mismatch at position {i}"


@pytest.mark.asyncio
async def test_index_returns_html(client: AsyncClient) -> None:
    async with client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_invalid_rank_rejected(client: AsyncClient) -> None:
    async with client:
        resp = await client.get("/puzzle?rank=10")
    assert resp.status_code == 422
