from typing import List

from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session, init_models
from schemas import RecipeCreate, RecipeListItem, RecipeDetail
from crud import create_recipe, list_recipes_sorted, increment_views_and_get

tags = [{"name": "Recipes", "description": "Список, детали и создание рецептов."}]

app = FastAPI(
    title="Кулинарная книга — API",
    version="1.0.0",
    description=(
        "Асинхронный сервис рецептов.\n\n"
        "- `GET /recipes` — список (сортировка: просмотры ↓, время ↑)\n"
        "- `GET /recipes/{id}` — детали (увеличивает просмотры)\n"
        "- `POST /recipes` — создание рецепта\n"
    ),
    openapi_tags=tags,
)


@app.on_event("startup")
async def on_startup():
    await init_models()


@app.get("/recipes", response_model=List[RecipeListItem], tags=["Recipes"])
async def get_recipes(session: AsyncSession = Depends(get_session)):
    return await list_recipes_sorted(session)


@app.get("/recipes/{recipe_id}", response_model=RecipeDetail, tags=["Recipes"])
async def get_recipe(recipe_id: int, session: AsyncSession = Depends(get_session)):
    recipe = await increment_views_and_get(session, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Рецепт не найден")
    return RecipeDetail(
        id=recipe.id,
        name=recipe.name,
        cook_time_minutes=recipe.cook_time_minutes,
        views=recipe.views,
        ingredients=[i.name for i in recipe.ingredients],
        description=recipe.description,
    )


@app.post(
    "/recipes", response_model=RecipeDetail, status_code=status.HTTP_201_CREATED, tags=["Recipes"]
)
async def post_recipe(payload: RecipeCreate, session: AsyncSession = Depends(get_session)):
    new_recipe = await create_recipe(
        session=session,
        name=payload.name,
        cook_time_minutes=payload.cook_time_minutes,
        description=payload.description,
        ingredients=[i.name for i in payload.ingredients],
    )
    return RecipeDetail(
        id=new_recipe.id,
        name=new_recipe.name,
        cook_time_minutes=new_recipe.cook_time_minutes,
        views=new_recipe.views,
        ingredients=[i.name for i in new_recipe.ingredients],
        description=new_recipe.description,
    )
