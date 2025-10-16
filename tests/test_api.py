import asyncio
import os
import tempfile

import aiohttp
import pytest
import uvicorn
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database import get_session
from main import app
from models import Base


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine_and_sessionmaker():
    # временная база
    fd, db_path = tempfile.mkstemp(prefix="recipes_test_", suffix=".db")
    os.close(fd)
    url = f"sqlite+aiosqlite:///{db_path}"

    engine = create_async_engine(url, echo=False, future=True)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine, session_maker

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    os.remove(db_path)


@pytest.fixture(scope="session")
async def app_with_overrides(test_engine_and_sessionmaker):
    _, session_maker = test_engine_and_sessionmaker

    async def override_get_session():
        async with session_maker() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
async def live_server(app_with_overrides):
    host, port = "127.0.0.1", 8001
    config = uvicorn.Config(
        app_with_overrides, host=host, port=port, log_level="warning", loop="asyncio", lifespan="on"
    )
    server = uvicorn.Server(config)

    async def _run():
        await server.serve()

    task = asyncio.create_task(_run())

    # ждём старт
    async with aiohttp.ClientSession() as sess:
        for _ in range(50):
            try:
                async with sess.get(f"http://{host}:{port}/docs") as resp:
                    if resp.status in (200, 404):
                        break
            except Exception:
                pass
            await asyncio.sleep(0.1)

    base_url = f"http://{host}:{port}"
    try:
        yield base_url
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=5)
        except TimeoutError:
            task.cancel()


@pytest.mark.asyncio
async def test_create_list_detail_with_aiohttp(live_server: str):
    base = live_server
    async with aiohttp.ClientSession() as client:
        payload = {
            "name": "Окрошка",
            "cook_time_minutes": 25,
            "description": "Нарезать и смешать.",
            "ingredients": [{"name": "Квас"}, {"name": "Огурец"}],
        }
        async with client.post(f"{base}/recipes", json=payload) as resp:
            assert resp.status == 201
            created = await resp.json()
            rid = created["id"]
            assert created["name"] == "Окрошка"
            assert created["views"] == 0
            assert created["ingredients"] == ["Квас", "Огурец"]

        async with client.get(f"{base}/recipes") as resp:
            assert resp.status == 200
            items = await resp.json()
            assert isinstance(items, list) and len(items) == 1
            assert items[0]["name"] == "Окрошка"
            assert items[0]["views"] == 0
            assert items[0]["cook_time_minutes"] == 25

        async with client.get(f"{base}/recipes/{rid}") as resp:
            assert resp.status == 200
            detail = await resp.json()
            assert detail["views"] == 1
            assert detail["ingredients"] == ["Квас", "Огурец"]

        async with client.get(f"{base}/recipes/{rid}") as resp:
            assert resp.status == 200
            detail2 = await resp.json()
            assert detail2["views"] == 2


import asyncio
import os
import tempfile

import aiohttp
import pytest
import uvicorn
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database import get_session
from main import app
from models import Base


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine_and_sessionmaker():
    # временная база
    fd, db_path = tempfile.mkstemp(prefix="recipes_test_", suffix=".db")
    os.close(fd)
    url = f"sqlite+aiosqlite:///{db_path}"

    engine = create_async_engine(url, echo=False, future=True)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine, session_maker

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    os.remove(db_path)


@pytest.fixture(scope="session")
async def app_with_overrides(test_engine_and_sessionmaker):
    _, session_maker = test_engine_and_sessionmaker

    async def override_get_session():
        async with session_maker() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
async def live_server(app_with_overrides):
    host, port = "127.0.0.1", 8001
    config = uvicorn.Config(
        app_with_overrides, host=host, port=port, log_level="warning", loop="asyncio", lifespan="on"
    )
    server = uvicorn.Server(config)

    async def _run():
        await server.serve()

    task = asyncio.create_task(_run())

    # ждём старт
    async with aiohttp.ClientSession() as sess:
        for _ in range(50):
            try:
                async with sess.get(f"http://{host}:{port}/docs") as resp:
                    if resp.status in (200, 404):
                        break
            except Exception:
                pass
            await asyncio.sleep(0.1)

    base_url = f"http://{host}:{port}"
    try:
        yield base_url
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=5)
        except TimeoutError:
            task.cancel()


@pytest.mark.asyncio
async def test_create_list_detail_with_aiohttp(live_server: str):
    base = live_server
    async with aiohttp.ClientSession() as client:
        payload = {
            "name": "Окрошка",
            "cook_time_minutes": 25,
            "description": "Нарезать и смешать.",
            "ingredients": [{"name": "Квас"}, {"name": "Огурец"}],
        }
        async with client.post(f"{base}/recipes", json=payload) as resp:
            assert resp.status == 201
            created = await resp.json()
            rid = created["id"]
            assert created["name"] == "Окрошка"
            assert created["views"] == 0
            assert created["ingredients"] == ["Квас", "Огурец"]

        async with client.get(f"{base}/recipes") as resp:
            assert resp.status == 200
            items = await resp.json()
            assert isinstance(items, list) and len(items) == 1
            assert items[0]["name"] == "Окрошка"
            assert items[0]["views"] == 0
            assert items[0]["cook_time_minutes"] == 25

        async with client.get(f"{base}/recipes/{rid}") as resp:
            assert resp.status == 200
            detail = await resp.json()
            assert detail["views"] == 1
            assert detail["ingredients"] == ["Квас", "Огурец"]

        async with client.get(f"{base}/recipes/{rid}") as resp:
            assert resp.status == 200
            detail2 = await resp.json()
            assert detail2["views"] == 2
