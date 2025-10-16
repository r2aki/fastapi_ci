from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Recipe, Ingredient


async def create_recipe(
    session: AsyncSession,
    name: str,
    cook_time_minutes: int,
    description: str,
    ingredients: List[str],
) -> Recipe:
    recipe = Recipe(
        name=name, cook_time_minutes=cook_time_minutes, description=description, views=0
    )
    for ing in ingredients:
        recipe.ingredients.append(Ingredient(name=ing))
    session.add(recipe)
    await session.commit()
    await session.refresh(recipe)
    return recipe


async def list_recipes_sorted(session: AsyncSession) -> List[Recipe]:
    stmt = select(Recipe).order_by(
        Recipe.views.desc(), Recipe.cook_time_minutes.asc(), Recipe.id.asc()
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_recipe_by_id(session: AsyncSession, recipe_id: int) -> Optional[Recipe]:
    stmt = select(Recipe).where(Recipe.id == recipe_id)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def increment_views_and_get(session: AsyncSession, recipe_id: int) -> Optional[Recipe]:
    recipe = await get_recipe_by_id(session, recipe_id)
    if recipe is None:
        return None
    recipe.views += 1
    await session.commit()
    await session.refresh(recipe)
    return recipe
