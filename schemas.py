from typing import List
from pydantic import BaseModel, Field, conint, constr


class IngredientIn(BaseModel):
    name: constr(min_length=1, max_length=200) = Field(..., description="Название ингредиента")

    model_config = {"json_schema_extra": {"example": {"name": "Соль"}}}


class RecipeCreate(BaseModel):
    name: constr(min_length=1, max_length=200) = Field(
        ..., description="Название рецепта", example="Окрошка"
    )
    cook_time_minutes: conint(ge=1, le=24 * 60) = Field(
        ..., description="Время готовки в минутах", example=25
    )
    description: constr(min_length=1) = Field(
        ..., description="Описание", example="Нарезать. Смешать."
    )
    ingredients: List[IngredientIn] = Field(
        ...,
        description="Список ингредиентов",
        example=[{"name": "Огурец"}, {"name": "Квас"}, {"name": "Соль"}],
    )


class RecipeListItem(BaseModel):
    id: int
    name: str
    views: int
    cook_time_minutes: int

    model_config = {"from_attributes": True}


class RecipeDetail(BaseModel):
    id: int
    name: str
    cook_time_minutes: int
    views: int
    ingredients: List[str]
    description: str

    model_config = {"from_attributes": True}
