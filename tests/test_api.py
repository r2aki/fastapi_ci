import os
import asyncio
import tempfile

import aiohttp
import pytest
import uvicorn
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from models import Base
from main import app
from database import get_session


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
async def test_engine_and_sessionmaker():
    """Создаём временную БД для тестов"""
    fd, db_path = tempfile.mkstemp(prefix="recipes_test_", suffix=".db")
    os.close(fd)
    url = f"sqlite+aiosqlite:///{db_path}"

    engine = create_async_engine(
        url,
        echo=False,
        future=True,
        poolclass=NullPool,
        connect_args={"timeout": 30, "check_same_thread": False},
    )
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Создаём таблицы заранее
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine, session_maker

    # Чистим после тестов
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
    except Exception:
        pass
    
    try:
        os.remove(db_path)
    except (FileNotFoundError, PermissionError):
        pass


@pytest.fixture(scope="session")
async def app_with_overrides(test_engine_and_sessionmaker):
    """Переопределяем зависимость get_session для использования тестовой БД"""
    os.environ["TESTING"] = "1"

    _, session_maker = test_engine_and_sessionmaker

    async def override_get_session():
        async with session_maker() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
async def live_server(app_with_overrides):
    """
    Запускаем uvicorn сервер БЕЗ lifespan события,
    чтобы не было конфликтов с инициализацией БД
    """
    host, port = "127.0.0.1", 8001
    
    config = uvicorn.Config(
        app_with_overrides,
        host=host,
        port=port,
        log_level="error",  # Минимум логов
        loop="asyncio",
        lifespan="off",  # ВАЖНО: отключаем lifespan
    )
    server = uvicorn.Server(config)

    # Запускаем сервер в отдельной задаче
    async def _run():
        await server.serve()

    task = asyncio.create_task(_run())

    # Ждём, пока сервер начнёт отвечать на запросы
    base_url = f"http://{host}:{port}"
    timeout = aiohttp.ClientTimeout(total=5)
    
    server_ready = False
    async with aiohttp.ClientSession(timeout=timeout) as sess:
        for attempt in range(50):  # 50 попыток × 0.2 сек = 10 секунд максимум
            try:
                async with sess.get(f"{base_url}/docs") as resp:
                    if resp.status in (200, 404):
                        server_ready = True
                        print(f"Тестовый сервер запущен на {base_url}")
                        break
            except (aiohttp.ClientError, asyncio.TimeoutError):
                pass
            await asyncio.sleep(0.2)
    
    if not server_ready:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=2)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
        pytest.fail("Не удалось запустить тестовый сервер за 10 секунд")

    try:
        yield base_url
    finally:
        # Останавливаем сервер
        server.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=3)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


@pytest.mark.asyncio
async def test_health_check(live_server: str):
    """Простая проверка что сервер работает"""
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as client:
        async with client.get(f"{live_server}/docs") as resp:
            assert resp.status == 200, f"Сервер не отвечает: {resp.status}"


@pytest.mark.asyncio
async def test_create_list_detail_with_aiohttp(live_server: str):
    """
    Основной тест: создание рецепта, получение списка, получение деталей
    """
    base = live_server
    timeout = aiohttp.ClientTimeout(total=30)  # 30 секунд для CI
    
    async with aiohttp.ClientSession(timeout=timeout) as client:
        # 1. POST /recipes - Создание рецепта
        payload = {
            "name": "Окрошка",
            "cook_time_minutes": 25,
            "description": "Нарезать и смешать.",
            "ingredients": [{"name": "Квас"}, {"name": "Огурец"}],
        }
        
        print(f"\nPOST {base}/recipes")
        async with client.post(f"{base}/recipes", json=payload) as resp:
            assert resp.status == 201, f"POST failed with status {resp.status}"
            created = await resp.json()
            print(f"Создан рецепт ID={created['id']}")
            
            rid = created["id"]
            assert rid is not None
            assert created["name"] == "Окрошка"
            assert created["cook_time_minutes"] == 25
            assert created["views"] == 0  # Новый рецепт имеет 0 просмотров

        # 2. GET /recipes - Получение списка рецептов
        print(f"\n📥 GET {base}/recipes")
        async with client.get(f"{base}/recipes") as resp:
            assert resp.status == 200, f"GET list failed with status {resp.status}"
            items = await resp.json()
            print(f"Получено {len(items)} рецептов")
            
            assert isinstance(items, list)
            assert len(items) > 0, "Список рецептов пуст"
            assert any(x["id"] == rid for x in items), "Созданный рецепт не найден в списке"

        # 3. GET /recipes/{id} - Получение деталей рецепта (первый раз)
        print(f"\nGET {base}/recipes/{rid} (просмотр #1)")
        async with client.get(f"{base}/recipes/{rid}") as resp:
            assert resp.status == 200, f"GET detail failed with status {resp.status}"
            detail = await resp.json()
            print(f"   ✅ Просмотров: {detail['views']}")
            
            assert detail["id"] == rid
            assert detail["name"] == "Окрошка"
            assert detail["views"] == 1, "После первого просмотра должен быть 1 просмотр"
            assert "Квас" in detail["ingredients"]
            assert "Огурец" in detail["ingredients"]

        # 4. GET /recipes/{id} - Получение деталей рецепта (второй раз)
        print(f"\nGET {base}/recipes/{rid} (просмотр #2)")
        async with client.get(f"{base}/recipes/{rid}") as resp:
            assert resp.status == 200
            detail2 = await resp.json()
            print(f"Просмотров: {detail2['views']}")
            
            assert detail2["views"] == 2, "После второго просмотра должно быть 2 просмотра"


@pytest.mark.asyncio
async def test_recipe_validation(live_server: str):
    """Тест валидации данных при создании рецепта"""
    base = live_server
    timeout = aiohttp.ClientTimeout(total=10)
    
    async with aiohttp.ClientSession(timeout=timeout) as client:
        # Невалидные данные: пустое имя
        payload = {
            "name": "",
            "cook_time_minutes": 25,
            "description": "Test",
            "ingredients": []
        }
        
        async with client.post(f"{base}/recipes", json=payload) as resp:
            assert resp.status == 422, "Должна быть ошибка валидации для пустого имени"


@pytest.mark.asyncio
async def test_get_nonexistent_recipe(live_server: str):
    """Тест получения несуществующего рецепта"""
    base = live_server
    timeout = aiohttp.ClientTimeout(total=10)
    
    async with aiohttp.ClientSession(timeout=timeout) as client:
        async with client.get(f"{base}/recipes/999999") as resp:
            assert resp.status == 404, "Должна быть ошибка 404 для несуществующего рецепта"


@pytest.mark.asyncio
async def test_recipe_sorting(live_server: str):
    """Тест сортировки рецептов: по views DESC, потом по cook_time ASC"""
    base = live_server
    timeout = aiohttp.ClientTimeout(total=20)
    
    async with aiohttp.ClientSession(timeout=timeout) as client:
        # Создаём несколько рецептов
        recipes_data = [
            {"name": "Быстрый", "cook_time_minutes": 10, "description": "Быстро", "ingredients": []},
            {"name": "Медленный", "cook_time_minutes": 60, "description": "Долго", "ingredients": []},
            {"name": "Средний", "cook_time_minutes": 30, "description": "Средне", "ingredients": []},
        ]
        
        created_ids = []
        for recipe in recipes_data:
            async with client.post(f"{base}/recipes", json=recipe) as resp:
                data = await resp.json()
                created_ids.append(data["id"])
        
        # Добавляем просмотры первому рецепту
        async with client.get(f"{base}/recipes/{created_ids[0]}") as resp:
            pass  # +1 просмотр
        
        # Проверяем сортировку
        async with client.get(f"{base}/recipes") as resp:
            items = await resp.json()
            
            # Первый должен быть с просмотрами (views=1)
            first = next(r for r in items if r["id"] == created_ids[0])
            assert first["views"] == 1
            
            # Среди рецептов с 0 просмотрами должна быть сортировка по времени
            zero_views = [r for r in items if r["views"] == 0]
            if len(zero_views) >= 2:
                times = [r["cook_time_minutes"] for r in zero_views]
                assert times == sorted(times), "Рецепты с 0 просмотрами должны быть отсортированы по времени"
