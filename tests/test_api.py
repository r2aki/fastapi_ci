import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
import time
import multiprocessing as mp
import urllib.request

import aiohttp
import pytest
import uvicorn
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from models import Base
from main import app
from database import get_session


def _run_server(host: str, port: int) -> None:
    """Стартуем uvicorn в отдельном процессе без lifespan."""
    os.environ["TESTING"] = "1"
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        loop="asyncio",
        lifespan="off",
    )
    uvicorn.Server(config).run()


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
async def test_engine_and_sessionmaker(tmp_path_factory):
    # Отдельная временная БД для тестов
    db_dir = tmp_path_factory.mktemp("db")
    db_path = db_dir / "recipes_test.db"
    url = f"sqlite+aiosqlite:///{db_path}"

    engine = create_async_engine(
        url,
        echo=False,
        future=True,
        poolclass=NullPool,
        connect_args={"timeout": 30},
    )
    session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Создаём таблицы заранее
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield str(db_path), engine, session_maker

    # Дропаем и закрываем коннекты
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="session")
async def app_with_overrides(test_engine_and_sessionmaker):
    _, _, session_maker = test_engine_and_sessionmaker

    async def override_get_session():
        async with session_maker() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def live_server(app_with_overrides):
    """Поднимаем uvicorn в отдельном процессе, чтобы не конфликтовать с event loop тестов."""
    host, port = "127.0.0.1", 8001
    base = f"http://{host}:{port}"

    proc = mp.Process(target=_run_server, args=(host, port), daemon=True)
    proc.start()

    ok = False
    for _ in range(120):
        try:
            with urllib.request.urlopen(f"{base}/docs", timeout=2) as r:
                if r.status in (200, 404):
                    ok = True
                    break
        except Exception:
            pass
        time.sleep(0.1)

    if not ok:
        try:
            proc.terminate()
        finally:
            proc.join(timeout=3)
        pytest.fail("Uvicorn server failed to start")

    try:
        yield base
    finally:
        try:
            proc.terminate()
        finally:
            proc.join(timeout=5)


@pytest.mark.asyncio
async def test_create_list_detail_with_aiohttp(live_server: str):
    base = live_server
    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(timeout=timeout) as client:
        # POST /recipes
        payload = {
            "name": "Окрошка",
            "cook_time_minutes": 25,
            "description": "Нарезать и смешать.",
            "ingredients": [{"name": "Квас"}, {"name": "Огурец"}],
        }
        async with client.post(f"{base}/recipes", json=payload) as resp:
            assert resp.status == 201, f"POST failed: {resp.status}"
            created = await resp.json()
            rid = created["id"]

        # GET /recipes
        async with client.get(f"{base}/recipes") as resp:
            assert resp.status == 200
            items = await resp.json()
            assert any(x["id"] == rid for x in items)

        # GET /recipes/{id} (+1 просмотр)
        async with client.get(f"{base}/recipes/{rid}") as resp:
            assert resp.status == 200
            detail = await resp.json()
            assert detail["views"] == 1

        async with client.get(f"{base}/recipes/{rid}") as resp:
            assert resp.status == 200
            detail2 = await resp.json()
            assert detail2["views"] == 2


