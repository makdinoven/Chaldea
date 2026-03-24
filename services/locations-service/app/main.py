import os
import math
import logging
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, APIRouter, Request, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from config import settings

import models
import httpx
import schemas
import crud
from database import get_db
from fastapi.middleware.cors import CORSMiddleware
from auth_http import get_admin_user, get_current_user_via_http, require_permission, UserRead, OAUTH2_SCHEME
from rabbitmq_publisher import publish_notification_sync
from sqlalchemy import text

logger = logging.getLogger(__name__)

OAUTH2_SCHEME_OPTIONAL = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


async def _try_spawn_mob(location_id: int, character_id: int):
    """
    Fire-and-forget: call character-service to try spawning a mob at the location.
    Errors are caught and logged — never blocks or fails the calling endpoint.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.CHARACTER_SERVICE_URL}/characters/internal/try-spawn",
                json={"location_id": location_id, "character_id": character_id},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("spawned"):
                    logger.info(
                        f"Моб заспавнен на локации {location_id}: {data.get('mob', {}).get('name', '?')}"
                    )
            else:
                logger.warning(f"try-spawn вернул статус {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.warning(f"Ошибка при вызове try-spawn для локации {location_id}: {e}")

app = FastAPI()

cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/locations")


async def verify_character_ownership(db: AsyncSession, character_id: int, user_id: int):
    """Check that the character belongs to the authenticated user."""
    result = await db.execute(
        text("SELECT user_id FROM characters WHERE id = :cid"),
        {"cid": character_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Персонаж не найден")
    if row[0] != user_id:
        raise HTTPException(status_code=403, detail="Вы можете управлять только своими персонажами")


async def check_not_in_battle(db: AsyncSession, character_id: int, message: str = "Действие заблокировано во время боя"):
    """Raise 400 if character is in an active battle (shared DB query)."""
    result = await db.execute(
        text(
            "SELECT b.id FROM battles b "
            "JOIN battle_participants bp ON b.id = bp.battle_id "
            "WHERE bp.character_id = :cid AND b.status IN ('pending', 'in_progress') "
            "LIMIT 1"
        ),
        {"cid": character_id},
    )
    if result.fetchone():
        raise HTTPException(status_code=400, detail=message)


def get_optional_user(token: Optional[str] = Depends(OAUTH2_SCHEME_OPTIONAL)) -> Optional[UserRead]:
    """Try to authenticate user, return None if no token or invalid token."""
    if not token:
        return None
    import requests as sync_requests
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{os.environ.get('AUTH_SERVICE_URL', 'http://user-service:8000')}/users/me"
    try:
        resp = sync_requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            return UserRead(**resp.json())
    except Exception:
        pass
    return None


# --------------------------------------------------------------------
# LOOKUP (короткие списки)
# --------------------------------------------------------------------
@router.get("/locations/lookup", response_model=List[schemas.LocationLookup])
async def locations_lookup(session: AsyncSession = Depends(get_db)):
    data = await crud.get_locations_lookup(session)
    return data

@router.get("/districts/lookup", response_model=List[schemas.DistrictLookup])
async def districts_lookup(session: AsyncSession = Depends(get_db)):
    data = await crud.get_districts_lookup(session)
    return data

@router.get("/countries/lookup", response_model=List[schemas.CountryLookup])
async def countries_lookup(session: AsyncSession = Depends(get_db)):
    """
    Возвращает список всех стран (id, name).
    """
    data = await crud.get_countries_lookup(session)
    return data



# --------------------------------------------------------------------
# COUNTRY
# --------------------------------------------------------------------
@router.post("/countries/create", response_model=schemas.CountryRead)
async def create_country_route(body: schemas.CountryCreate, session: AsyncSession = Depends(get_db), current_user = Depends(require_permission("locations:create"))):
    new_c = await crud.create_new_country(
        session,
        name=body.name,
        description=body.description,
        leader_id=body.leader_id,
        map_image_url=body.map_image_url,
        area_id=body.area_id,
        x=body.x,
        y=body.y,
        emblem_url=body.emblem_url,
    )
    return new_c

@router.put("/countries/{country_id}/update", response_model=schemas.CountryRead)
async def update_country_route(country_id: int, body: schemas.CountryUpdate, session: AsyncSession = Depends(get_db), current_user = Depends(require_permission("locations:update"))):
    db_obj = await crud.update_country(session, country_id, body)
    return db_obj

@router.delete("/countries/{country_id}/delete", response_model=dict)
async def delete_country_route(country_id: int, session: AsyncSession = Depends(get_db), current_user=Depends(require_permission("locations:delete"))):
    await crud.delete_country(session, country_id)
    return {"message": "Country deleted"}

@router.get("/countries/list")
async def get_countries_list_route(session: AsyncSession = Depends(get_db)):
    """Возвращает список стран"""
    return await crud.get_countries_list(session)

@router.get("/countries/{country_id}/details")
async def get_country_details_route(country_id: int, session: AsyncSession = Depends(get_db)):
    """Возвращает детали страны с регионами"""
    data = await crud.get_country_details(session, country_id)
    if not data:
        raise HTTPException(status_code=404, detail="Country not found")
    return data


# --------------------------------------------------------------------
# REGION
# --------------------------------------------------------------------
@router.post("/regions/create", response_model=schemas.RegionCreateResponse)
async def create_region_route(body: schemas.RegionCreate, session: AsyncSession = Depends(get_db), current_user = Depends(require_permission("locations:create"))):
    new_r = await crud.create_new_region(session, body)
    return new_r

@router.put("/regions/{region_id}/update", response_model=schemas.RegionUpdateResponse)
async def update_region_route(region_id: int, body: schemas.RegionUpdate, session: AsyncSession = Depends(get_db), current_user = Depends(require_permission("locations:update"))):
    return await crud.update_region(session, region_id, body)

@router.get("/regions/{region_id}/details")
async def get_region_details_route(region_id: int, session: AsyncSession = Depends(get_db)):
    """Возвращает детали региона с районами и локациями"""
    data = await crud.get_region_full_details(session, region_id)
    if not data:
        raise HTTPException(status_code=404, detail="Region not found")
    return data

@router.put("/regions/{region_id}/sort-order")
async def update_region_sort_order(
    region_id: int,
    body: schemas.SortOrderUpdate,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("locations:update")),
):
    """Batch-update sort_order for districts and locations within a region."""
    await crud.update_items_sort_order(session, body.items)
    return {"status": "success"}


@router.delete("/regions/{region_id}/delete", response_model=dict)
async def delete_region_route(
    region_id: int,
    session: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("locations:delete"))
):
    """
    Удаляет регион вместе со всеми его районами и локациями.
    """
    try:
        await crud.delete_region(session, region_id)
        await session.commit()
        return {"status": "success", "message": f"Region {region_id} has been deleted."}
    except HTTPException as e:
        raise e
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
# --------------------------------------------------------------------
# DISTRICT
# --------------------------------------------------------------------
@router.post("/districts", response_model=schemas.DistrictRead)
async def create_district(
    district: schemas.DistrictCreate,
    session: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("locations:create"))
):
    try:
        return await crud.create_district(session, district)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Не удалось создать район: {str(e)}"
        )

@router.put("/districts/{district_id}/update", response_model=schemas.DistrictRead)
async def update_district_route(district_id: int, body: schemas.DistrictUpdate, session: AsyncSession = Depends(get_db), current_user = Depends(require_permission("locations:update"))):
    return await crud.update_district(session, district_id, body)

@router.get("/districts/{district_id}/details", response_model=schemas.DistrictRead)
async def get_district_details(
    district_id: int,
    session: AsyncSession = Depends(get_db)
):
    """Получение детальной информации о районе"""
    try:
        stmt = select(models.District).where(models.District.id == district_id).options(
            selectinload(models.District.locations),
            selectinload(models.District.entrance_location_detail)
        )
        result = await session.execute(stmt)
        district = result.scalar_one_or_none()
        
        if not district:
            raise HTTPException(status_code=404, detail="District not found")
            
        return district
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/districts/{district_id}/locations", response_model=List[schemas.LocationRead])
async def get_district_locations(
    district_id: int,
    session: AsyncSession = Depends(get_db)
):
    """Получение всех локаций района"""
    try:
        stmt = select(models.Location).where(
            models.Location.district_id == district_id
        ).order_by(models.Location.name)
        
        result = await session.execute(stmt)
        locations = result.scalars().all()
        
        return locations
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/districts/{district_id}/delete", response_model=dict)
async def delete_district_route(
    district_id: int,
    session: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("locations:delete"))
):
    """
    Удаляет район вместе со всеми его локациями.
    """
    try:
        await crud.delete_district(session, district_id)
        await session.commit()
        return {"status": "success", "message": f"District {district_id} has been deleted."}
    except HTTPException as e:
        raise e
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
# --------------------------------------------------------------------
# LOCATION
# --------------------------------------------------------------------
@router.post("/", response_model=schemas.LocationCreateResponse)
async def create_location(location: schemas.LocationCreate, db: AsyncSession = Depends(get_db), current_user = Depends(require_permission("locations:create"))):
    try:
        db_location = await crud.create_location(db, location)
        # Возвращаем только базовые поля без связанных данных
        return {
            "id": db_location.id,
            "name": db_location.name,
            "district_id": db_location.district_id,
            "region_id": db_location.region_id,
            "type": db_location.type,
            "image_url": db_location.image_url,
            "recommended_level": db_location.recommended_level,
            "quick_travel_marker": db_location.quick_travel_marker,
            "parent_id": db_location.parent_id,
            "description": db_location.description,
            "marker_type": db_location.marker_type,
            "map_icon_url": db_location.map_icon_url,
            "map_x": db_location.map_x,
            "map_y": db_location.map_y,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{location_id}/update", response_model=schemas.LocationRead)
async def update_location_route(location_id: int, body: schemas.LocationUpdate, session: AsyncSession = Depends(get_db), current_user = Depends(require_permission("locations:update"))):
    try:
        db_location = await crud.update_location(session, location_id, body)
        # Возвращаем только базовые поля без связанных данных
        return {
            "id": db_location.id,
            "name": db_location.name,
            "district_id": db_location.district_id,
            "type": db_location.type,
            "image_url": db_location.image_url or "",  # Преобразуем None в пустую строку
            "recommended_level": db_location.recommended_level,
            "quick_travel_marker": db_location.quick_travel_marker,
            "parent_id": db_location.parent_id,
            "description": db_location.description or "",
            "marker_type": db_location.marker_type,
            "map_icon_url": db_location.map_icon_url,
            "map_x": db_location.map_x,
            "map_y": db_location.map_y,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{location_id}/details")
async def get_location_details_route(location_id: int, session: AsyncSession = Depends(get_db)):
    data = await crud.get_location_details(session, location_id)
    if not data:
        raise HTTPException(status_code=404, detail="Location not found")
    return data

@router.get("/{location_id}/children", response_model=List[schemas.LocationBase])
async def get_location_children(location_id: int, db: AsyncSession = Depends(get_db)):
    """Получить список дочерних локаций"""
    try:
        children = await crud.get_location_children(db, location_id)
        return [
            {
                "id": child.id,
                "name": child.name,
                "type": child.type,
                "image_url": child.image_url
            }
            for child in children
        ]
    except Exception as e:
        print(f"Ошибка при получении дочерних локаций: {e}")
        return []

@router.delete("/{location_id}/delete", response_model=dict)
async def delete_location_route(
    location_id: int,
    session: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("locations:delete"))
):
    """
    Удаляет локацию вместе со всеми её дочерними локациями (рекурсивно)
    и со всеми соседними связями.
    """
    try:
        await crud.delete_location_recursively(session, location_id)
        await session.commit()
        return {"status": "success", "message": f"Location {location_id} and its children have been deleted."}
    except HTTPException as e:
        raise e
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
# --------------------------------------------------------------------
# NEIGHBORS
# --------------------------------------------------------------------
@router.post("/{location_id}/neighbors/", response_model=schemas.LocationNeighborResponse)
async def create_neighbor(location_id: int, neighbor_data: schemas.LocationNeighborCreate, session: AsyncSession = Depends(get_db), current_user = Depends(require_permission("locations:update"))):
    loc = await crud.get_location_by_id(session, location_id)
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")

    neighbor = await crud.get_location_by_id(session, neighbor_data.neighbor_id)
    if not neighbor:
        raise HTTPException(status_code=404, detail="Neighbor location not found")

    result = await crud.add_neighbor(session, location_id, neighbor_data.neighbor_id, neighbor_data.energy_cost)
    return {
        "neighbor_id": result["neighbor_id"],
        "energy_cost": result["energy_cost"]
    }

@router.get("/{location_id}/neighbors/", response_model=List[schemas.LocationNeighborResponse])
async def get_location_neighbors(location_id: int, session: AsyncSession = Depends(get_db)):
    """Получить список соседей для локации"""
    loc = await crud.get_location_by_id(session, location_id)
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    
    result = await session.execute(
        select(models.LocationNeighbor).where(models.LocationNeighbor.location_id == location_id)
    )
    neighbors = result.scalars().all()
    
    return [
        {
            "neighbor_id": n.neighbor_id,
            "energy_cost": n.energy_cost
        }
        for n in neighbors
    ]

@router.delete("/{location_id}/neighbors/{neighbor_id}", response_model=dict)
async def delete_neighbor(location_id: int, neighbor_id: int, session: AsyncSession = Depends(get_db), current_user = Depends(require_permission("locations:delete"))):
    """Удаляет связь между локациями"""
    loc = await crud.get_location_by_id(session, location_id)
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")

    neighbor = await crud.get_location_by_id(session, neighbor_id)
    if not neighbor:
        raise HTTPException(status_code=404, detail="Neighbor location not found")

    # Проверяем, существует ли связь
    result = await session.execute(
        select(models.LocationNeighbor).where(
            models.LocationNeighbor.location_id == location_id,
            models.LocationNeighbor.neighbor_id == neighbor_id
        )
    )
    neighbor_relation = result.scalars().first()
    if not neighbor_relation:
        raise HTTPException(status_code=404, detail="Neighbor relation not found")

    # Удаляем прямую связь
    await session.execute(
        delete(models.LocationNeighbor).where(
            models.LocationNeighbor.location_id == location_id,
            models.LocationNeighbor.neighbor_id == neighbor_id
        )
    )

    # Удаляем обратную связь
    await session.execute(
        delete(models.LocationNeighbor).where(
            models.LocationNeighbor.location_id == neighbor_id,
            models.LocationNeighbor.neighbor_id == location_id
        )
    )

    await session.commit()
    return {"status": "success", "message": "Neighbor relation deleted"}

@router.post("/{location_id}/neighbors/update", response_model=List[schemas.LocationNeighborResponse])
async def update_location_neighbors(
    location_id: int,
    neighbors_data: schemas.LocationNeighborsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_permission("locations:update"))
):
    """Обновляет список соседей локации"""
    # Проверяем существование локации
    try:
        location = await crud.get_location_by_id(db, location_id)
        if not location:
            raise HTTPException(status_code=404, detail="Location not found")
        
        # Обновляем соседей
        updated_neighbors = await crud.update_location_neighbors(
            db, location_id, neighbors_data.neighbors
        )
        return updated_neighbors
    except Exception as e:
        print(f"Ошибка при обновлении соседей для локации {location_id}: {e}")
        # Возвращаем пустой список вместо ошибки
        return []

# --------------------------------------------------------------------
# POSTS
# --------------------------------------------------------------------
@router.post("/posts/", response_model=schemas.PostResponse)
async def create_new_post(
    post_data: schemas.PostCreate,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    await verify_character_ownership(session, post_data.character_id, current_user.id)
    await check_not_in_battle(session, post_data.character_id, "Вы не можете писать посты во время боя")
    result = await crud.create_post(session, post_data)

    # Fire-and-forget: trigger mob spawn check
    background_tasks.add_task(
        _try_spawn_mob, post_data.location_id, post_data.character_id
    )

    return result

@router.get("/{location_id}/posts/", response_model=List[schemas.PostResponse])
async def get_posts_in_location(location_id: int, session: AsyncSession = Depends(get_db)):
    return await crud.get_posts_by_location(session, location_id)


@router.post("/posts/{post_id}/like", status_code=201)
async def like_post(
    post_id: int,
    body: schemas.PostLikeRequest,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Add a like to a post. Requires character ownership."""
    await verify_character_ownership(session, body.character_id, current_user.id)
    like = await crud.like_post(session, post_id, body.character_id)
    return {"status": "liked", "post_id": post_id, "character_id": body.character_id}


@router.delete("/posts/{post_id}/like", status_code=200)
async def unlike_post(
    post_id: int,
    character_id: int,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """Remove a like from a post. Requires character ownership."""
    await verify_character_ownership(session, character_id, current_user.id)
    await crud.unlike_post(session, post_id, character_id)
    return {"status": "unliked", "post_id": post_id, "character_id": character_id}


@router.get("/admin/data", response_model=schemas.AdminPanelData)
async def get_admin_panel_data_route(session: AsyncSession = Depends(get_db), current_user=Depends(require_permission("locations:read"))):
    """
    Возвращает все данные для админ панели одним запросом
    """
    return await crud.get_admin_panel_data(session)


@router.get("/{location_id}/client/details", response_model=schemas.LocationClientDetails)
async def get_location_client_details(
    location_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: Optional[UserRead] = Depends(get_optional_user),
):
    """
    Возвращает детальную информацию о локации для клиента.
    Помимо базовых данных локации, включает:
      - Список соседей
      - Список персонажей (игроков) в локации
      - Посты пользователей, обогащенные информацией о профиле автора, полученной из Character‑service
      - is_favorited (если пользователь авторизован)
    """
    user_id = current_user.id if current_user else None
    data = await crud.get_client_location_details(session, location_id, user_id=user_id)
    if not data:
        raise HTTPException(status_code=404, detail="Location not found")
    return data


# --------------------------------------------------------------------
# FAVORITES
# --------------------------------------------------------------------
@router.post("/{location_id}/favorite")
async def add_favorite(
    location_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """Добавить локацию в избранное."""
    await crud.add_favorite(session, current_user.id, location_id)
    return {"detail": "Локация добавлена в избранное"}


@router.delete("/{location_id}/favorite")
async def remove_favorite(
    location_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """Удалить локацию из избранного."""
    await crud.remove_favorite(session, current_user.id, location_id)
    return {"detail": "Локация удалена из избранного"}


# --------------------------------------------------------------------
# PLAYER TAGGING
# --------------------------------------------------------------------
@router.post("/{location_id}/tag-player")
async def tag_player(
    location_id: int,
    body: schemas.TagPlayerRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """
    Отправить уведомление другому игроку с приглашением на локацию.
    Отправитель должен владеть персонажем sender_character_id.
    """
    # Prevent self-tagging
    if current_user.id == body.target_user_id:
        raise HTTPException(status_code=400, detail="Нельзя отметить самого себя")

    # Verify character ownership
    await verify_character_ownership(session, body.sender_character_id, current_user.id)

    # Get sender character name from character-service
    async with httpx.AsyncClient(timeout=5.0) as client:
        profile_url = f"{settings.CHARACTER_SERVICE_URL}/characters/{body.sender_character_id}/profile"
        resp = await client.get(profile_url)
        if resp.status_code != 200:
            raise HTTPException(status_code=404, detail="Профиль персонажа не найден")
        profile_data = resp.json()
    character_name = profile_data.get("character_name", "Неизвестный")

    # Get location name
    result = await session.execute(
        select(models.Location).where(models.Location.id == location_id)
    )
    loc = result.scalars().first()
    if not loc:
        raise HTTPException(status_code=404, detail="Локация не найдена")

    message = f"{character_name} зовёт вас на локацию «{loc.name}»"
    background_tasks.add_task(publish_notification_sync, body.target_user_id, message)

    return {"detail": "Уведомление отправлено"}


@router.post("/{destination_location_id}/move_and_post", response_model=schemas.PostResponse)
async def move_and_post(
        destination_location_id: int,
        movement: schemas.MovementPostRequest,
        background_tasks: BackgroundTasks,
        session: AsyncSession = Depends(get_db),
        current_user=Depends(get_current_user_via_http),
):
    """
    Эндпоинт для перемещения персонажа в новую локацию и одновременного создания поста.

    Логика:
      1. Получаем профиль персонажа через Character‑service, чтобы узнать его текущую локацию.
      2. Если current_location_id не указан (NULL), разрешаем переход в любую локацию.
         Иначе проверяем, является ли destination_location_id соседней локацией от текущей.
      3. Получаем стоимость перехода (energy_cost).
      4. Вызываем Attributes‑service для проверки наличия достаточной выносливости (current_stamina).
      5. Создаём пост для destination_location_id.
      6. Обновляем текущую локацию персонажа через Character‑service.
      7. Вызываем Attributes‑service для списания выносливости на стоимость перехода.
    """
    # 0. Проверяем, что персонаж принадлежит текущему пользователю
    await verify_character_ownership(session, movement.character_id, current_user.id)
    await check_not_in_battle(session, movement.character_id, "Вы не можете покинуть локацию во время боя")

    # 1. Получаем профиль персонажа (чтобы узнать current_location_id)
    async with httpx.AsyncClient(timeout=5.0) as client:
        profile_url = f"{settings.CHARACTER_SERVICE_URL}/characters/{movement.character_id}/profile"
        profile_resp = await client.get(profile_url)
        if profile_resp.status_code != 200:
            raise HTTPException(status_code=404, detail="Character profile not found")
        profile_data = profile_resp.json()
    current_location = profile_data.get("current_location_id")  # может быть NULL

    # 2. Проверяем, можно ли переходить в целевую локацию
    if current_location is None:
        # персонаж ещё ни разу не «стоял» в локации – позволяем перемещаться куда угодно
        movement_cost = 0
    elif int(current_location) == destination_location_id:
        # остаётся в той же самой локации
        movement_cost = 0
    else:
        # проверяем, действительно ли dest — сосед current
        q = await session.execute(
            select(models.LocationNeighbor).where(
                models.LocationNeighbor.location_id == current_location,
                models.LocationNeighbor.neighbor_id == destination_location_id
            )
        )
        neighbor = q.scalars().first()
        if not neighbor:
            raise HTTPException(
                status_code=400,
                detail="Destination is not adjacent to current location"
            )
        movement_cost = neighbor.energy_cost

    # 3. Проверяем, достаточно ли выносливости (stamina)
    async with httpx.AsyncClient(timeout=5.0) as client:
        attr_url = f"{settings.ATTRIBUTES_SERVICE_URL}/attributes/{movement.character_id}"
        attr_resp = await client.get(attr_url)
        if attr_resp.status_code != 200:
            raise HTTPException(status_code=404, detail="Character attributes not found")
        attr_data = attr_resp.json()
        current_stamina = attr_data.get("current_stamina", 0)
        if current_stamina < movement_cost:
            raise HTTPException(status_code=400, detail="Not enough stamina to move")

    # 4. Создаём пост для новой локации (destination_location_id)
    # use the path parameter
    payload = {
        "character_id": movement.character_id,
        "location_id": destination_location_id,
        "content": movement.content
    }

    # обернуть в Pydantic-модель
    post_in = schemas.PostCreate(**payload)

    # и передать уже её
    new_post = await crud.create_post(session, post_in)

    # 5. Обновляем текущую локацию персонажа через Character‑service
    async with httpx.AsyncClient(timeout=5.0) as client:
        update_url = f"{settings.CHARACTER_SERVICE_URL}/characters/{movement.character_id}/update_location"
        update_resp = await client.put(update_url, json={"new_location_id": destination_location_id})
        if update_resp.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to update character location")

    # 6. Списываем выносливость (вызываем эндпоинт consume_stamina в Attributes‑service)
    async with httpx.AsyncClient(timeout=5.0) as client:
        consume_url = f"{settings.ATTRIBUTES_SERVICE_URL}/attributes/{movement.character_id}/consume_stamina"
        consume_resp = await client.post(consume_url, json={"amount": movement_cost})
        if consume_resp.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to deduct stamina for movement")

    # 7. Уведомляем пользователей, добавивших локацию в избранное
    dest_result = await session.execute(
        select(models.Location).where(models.Location.id == destination_location_id)
    )
    dest_loc = dest_result.scalars().first()
    if dest_loc:
        location_name = dest_loc.name
        fav_user_ids = await crud.get_favorite_user_ids(session, destination_location_id)
        author_user_id = current_user.id
        for uid in fav_user_ids:
            if uid != author_user_id:
                msg = f"Новый пост на локации «{location_name}»"
                background_tasks.add_task(publish_notification_sync, uid, msg)

    # Fire-and-forget: trigger mob spawn check at destination location
    background_tasks.add_task(
        _try_spawn_mob, destination_location_id, movement.character_id
    )

    return new_post


@router.post("/posts/as-npc", response_model=schemas.PostResponse)
async def create_post_as_npc(
        body: schemas.NpcPostCreate,
        session: AsyncSession = Depends(get_db),
        admin_user=Depends(get_admin_user),
        token: str = Depends(OAUTH2_SCHEME),
):
    """
    Admin-only: создать пост от имени NPC на указанной локации.
    Не требует проверки перемещения/выносливости.
    """
    # 1. Проверяем, что NPC существует через character-service
    async with httpx.AsyncClient(timeout=5.0) as client:
        npc_url = f"{settings.CHARACTER_SERVICE_URL}/characters/admin/npcs/{body.npc_id}"
        resp = await client.get(npc_url, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code != 200:
            raise HTTPException(status_code=404, detail="NPC не найден")

    # 2. Проверяем, что локация существует
    loc_result = await session.execute(
        select(models.Location).where(models.Location.id == body.location_id)
    )
    if not loc_result.scalars().first():
        raise HTTPException(status_code=404, detail="Локация не найдена")

    # 3. Создаём пост от имени NPC
    post_in = schemas.PostCreate(
        character_id=body.npc_id,
        location_id=body.location_id,
        content=body.content,
    )
    new_post = await crud.create_post(session, post_in)
    return new_post


# --------------------------------------------------------------------
# AREA
# --------------------------------------------------------------------
@router.get("/areas/list", response_model=List[schemas.AreaRead])
async def get_areas_list_route(session: AsyncSession = Depends(get_db)):
    """Returns all areas sorted by sort_order."""
    return await crud.get_areas_list(session)


@router.get("/areas/{area_id}/details")
async def get_area_details_route(area_id: int, session: AsyncSession = Depends(get_db)):
    """Returns area details with its countries."""
    data = await crud.get_area_details(session, area_id)
    if not data:
        raise HTTPException(status_code=404, detail="Area not found")
    return data


@router.post("/areas/create", response_model=schemas.AreaRead)
async def create_area_route(
    body: schemas.AreaCreate,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("locations:create")),
):
    return await crud.create_area(session, body)


@router.put("/areas/{area_id}/update", response_model=schemas.AreaRead)
async def update_area_route(
    area_id: int,
    body: schemas.AreaUpdate,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("locations:update")),
):
    return await crud.update_area(session, area_id, body)


@router.delete("/areas/{area_id}/delete", response_model=dict)
async def delete_area_route(
    area_id: int,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("locations:delete")),
):
    try:
        await crud.delete_area(session, area_id)
        return {"status": "success", "message": f"Area {area_id} has been deleted."}
    except HTTPException as e:
        raise e
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# --------------------------------------------------------------------
# CLICKABLE ZONES
# --------------------------------------------------------------------
@router.get("/clickable-zones/{parent_type}/{parent_id}", response_model=List[schemas.ClickableZoneRead])
async def get_clickable_zones_route(
    parent_type: str,
    parent_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Returns all clickable zones for a given parent (area or country)."""
    if parent_type not in ("area", "country"):
        raise HTTPException(status_code=400, detail="parent_type must be 'area' or 'country'")
    return await crud.get_clickable_zones_by_parent(session, parent_type, parent_id)


@router.post("/clickable-zones/create", response_model=schemas.ClickableZoneRead)
async def create_clickable_zone_route(
    body: schemas.ClickableZoneCreate,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("locations:create")),
):
    return await crud.create_clickable_zone(session, body)


@router.put("/clickable-zones/{zone_id}/update", response_model=schemas.ClickableZoneRead)
async def update_clickable_zone_route(
    zone_id: int,
    body: schemas.ClickableZoneUpdate,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("locations:update")),
):
    return await crud.update_clickable_zone(session, zone_id, body)


@router.delete("/clickable-zones/{zone_id}/delete", response_model=dict)
async def delete_clickable_zone_route(
    zone_id: int,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("locations:delete")),
):
    try:
        await crud.delete_clickable_zone(session, zone_id)
        return {"status": "success", "message": f"ClickableZone {zone_id} has been deleted."}
    except HTTPException as e:
        raise e
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# --------------------------------------------------------------------
# HIERARCHY TREE
# --------------------------------------------------------------------
@router.get("/hierarchy/tree", response_model=List[schemas.HierarchyNode])
async def get_hierarchy_tree_route(session: AsyncSession = Depends(get_db)):
    """Returns the full hierarchy tree for navigation."""
    return await crud.get_hierarchy_tree(session)


# --------------------------------------------------------------------
# RULES
# --------------------------------------------------------------------
rules_router = APIRouter(prefix="/rules")


@rules_router.get("/list", response_model=List[schemas.GameRuleRead])
async def get_rules_list(session: AsyncSession = Depends(get_db)):
    """Возвращает все правила игры (публичный)."""
    return await crud.get_all_rules(session)


@rules_router.get("/{rule_id}", response_model=schemas.GameRuleRead)
async def get_rule(rule_id: int, session: AsyncSession = Depends(get_db)):
    """Возвращает правило по ID (публичный)."""
    rule = await crud.get_rule_by_id(session, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Правило не найдено")
    return rule


@rules_router.post("/create", response_model=schemas.GameRuleRead)
async def create_rule(
    body: schemas.GameRuleCreate,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("rules:create")),
):
    """Создаёт новое правило (только админ)."""
    return await crud.create_rule(session, body)


@rules_router.put("/reorder")
async def reorder_rules(
    body: schemas.GameRuleReorder,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("rules:update")),
):
    """Массовое обновление sort_order (только админ)."""
    await crud.reorder_rules(session, body.order)
    return {"status": "success"}


@rules_router.put("/{rule_id}/update", response_model=schemas.GameRuleRead)
async def update_rule(
    rule_id: int,
    body: schemas.GameRuleUpdate,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("rules:update")),
):
    """Обновляет правило (только админ, partial update)."""
    return await crud.update_rule(session, rule_id, body)


@rules_router.delete("/{rule_id}/delete")
async def delete_rule(
    rule_id: int,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("rules:delete")),
):
    """Удаляет правило (только админ)."""
    await crud.delete_rule(session, rule_id)
    return {"status": "success", "message": f"Rule {rule_id} has been deleted."}


# --------------------------------------------------------------------
# GAME TIME
# --------------------------------------------------------------------
from datetime import datetime


@router.get("/game-time", response_model=schemas.GameTimePublicResponse)
async def get_game_time_public(session: AsyncSession = Depends(get_db)):
    """Публичный эндпоинт: возвращает epoch + offset_days + server_time для расчёта на фронтенде."""
    config = await crud.get_game_time_config(session)
    now = datetime.utcnow()
    if config:
        return {
            "epoch": config.epoch,
            "offset_days": config.offset_days,
            "server_time": now,
        }
    # Fallback to defaults if no row exists
    return {
        "epoch": datetime(2026, 3, 19, 0, 0, 0),
        "offset_days": 0,
        "server_time": now,
    }


@router.get("/game-time/admin", response_model=schemas.GameTimeAdminResponse)
async def get_game_time_admin(
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("gametime:read")),
):
    """Админский эндпоинт: возвращает полную конфигурацию + вычисленное игровое время."""
    config = await crud.get_game_time_config(session)
    if not config:
        raise HTTPException(status_code=404, detail="Конфигурация игрового времени не найдена")
    now = datetime.utcnow()
    computed = crud.compute_game_time(config.epoch, config.offset_days, now)
    return {
        "id": config.id,
        "epoch": config.epoch,
        "offset_days": config.offset_days,
        "updated_at": config.updated_at,
        "computed": computed,
        "server_time": now,
    }


@router.put("/game-time/admin", response_model=schemas.GameTimeAdminResponse)
async def update_game_time_admin(
    body: schemas.GameTimeAdminUpdate,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("gametime:update")),
):
    """
    Обновляет конфигурацию игрового времени.
    Два режима:
      - Direct: задать epoch и/или offset_days напрямую.
      - Set-date: задать target_year/target_segment/target_week — бэкенд вычислит offset_days.
    """
    now = datetime.utcnow()

    # Determine if set-date mode is used
    if body.target_year is not None:
        # Validate target_year
        if body.target_year < 1:
            raise HTTPException(status_code=400, detail="Год должен быть >= 1")

        # Validate target_segment
        if body.target_segment and body.target_segment not in crud.VALID_SEGMENT_NAMES:
            raise HTTPException(
                status_code=400,
                detail=f"Недопустимое имя сегмента: {body.target_segment}. "
                       f"Допустимые: {', '.join(crud.VALID_SEGMENT_NAMES)}",
            )

        target_segment = body.target_segment or "spring"

        # Find segment info
        segment_info = None
        for s in crud.YEAR_SEGMENTS:
            if s["name"] == target_segment:
                segment_info = s
                break

        # Validate week for seasons
        if segment_info and segment_info["type"] == "season":
            target_week = body.target_week or 1
            if target_week < 1 or target_week > 13:
                raise HTTPException(
                    status_code=400,
                    detail="Неделя должна быть от 1 до 13 для сезонов",
                )
        else:
            target_week = None

        # Compute target_day_in_year
        cumulative = 0
        for segment in crud.YEAR_SEGMENTS:
            if segment["name"] == target_segment:
                if segment["type"] == "season" and target_week:
                    target_day_in_year = cumulative + (target_week - 1) * crud.DAYS_PER_WEEK
                else:
                    target_day_in_year = cumulative
                break
            cumulative += segment["real_days"]

        target_total_days = (body.target_year - 1) * crud.DAYS_PER_YEAR + target_day_in_year

        # Determine the epoch to use
        epoch_to_use = body.epoch
        if epoch_to_use is None:
            config = await crud.get_game_time_config(session)
            epoch_to_use = config.epoch if config else datetime(2026, 3, 19, 0, 0, 0)

        import math
        elapsed_without_offset = math.floor((now - epoch_to_use).total_seconds() / 86400)
        computed_offset = target_total_days - elapsed_without_offset

        update_data = {"offset_days": computed_offset}
        if body.epoch is not None:
            update_data["epoch"] = body.epoch
    else:
        # Direct mode
        update_data = {}
        if body.epoch is not None:
            update_data["epoch"] = body.epoch
        if body.offset_days is not None:
            update_data["offset_days"] = body.offset_days

    config = await crud.update_game_time_config(session, update_data)
    now = datetime.utcnow()
    computed = crud.compute_game_time(config.epoch, config.offset_days, now)
    return {
        "id": config.id,
        "epoch": config.epoch,
        "offset_days": config.offset_days,
        "updated_at": config.updated_at,
        "computed": computed,
        "server_time": now,
    }


# --------------------------------------------------------------------
# LOOT — Drop & Pickup
# --------------------------------------------------------------------
@router.post("/{location_id}/loot/drop", response_model=schemas.LocationLootItem)
async def drop_loot(
    location_id: int,
    body: schemas.LocationLootDrop,
    request: Request,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """
    Выбросить предмет из инвентаря персонажа на землю в указанной локации.
    """
    # 1. Проверяем принадлежность персонажа
    await verify_character_ownership(session, body.character_id, current_user.id)

    # 2. Проверяем, что персонаж находится в данной локации
    async with httpx.AsyncClient(timeout=5.0) as client:
        profile_url = f"{settings.CHARACTER_SERVICE_URL}/characters/{body.character_id}/profile"
        profile_resp = await client.get(profile_url)
        if profile_resp.status_code != 200:
            raise HTTPException(status_code=404, detail="Профиль персонажа не найден")
        profile_data = profile_resp.json()

    current_location = profile_data.get("current_location_id")
    if current_location is None or int(current_location) != location_id:
        raise HTTPException(status_code=400, detail="Персонаж не находится в этой локации")

    # 3. Удаляем предмет из инвентаря через inventory-service
    auth_header = request.headers.get("authorization", "")
    async with httpx.AsyncClient(timeout=5.0) as client:
        remove_url = (
            f"{settings.INVENTORY_SERVICE_URL}/inventory/{body.character_id}"
            f"/items/{body.item_id}?quantity={body.quantity}"
        )
        remove_resp = await client.delete(
            remove_url,
            headers={"Authorization": auth_header},
        )
        if remove_resp.status_code != 200:
            detail = "Не удалось удалить предмет из инвентаря"
            try:
                detail = remove_resp.json().get("detail", detail)
            except Exception:
                pass
            raise HTTPException(status_code=remove_resp.status_code, detail=detail)

    # 4. Создаём запись лута в локации
    loot = await crud.create_location_loot(
        session, location_id, body.item_id, body.quantity, body.character_id
    )

    # 5. Получаем данные предмета для ответа
    loot_list = await crud.get_location_loot(session, location_id)
    for item in loot_list:
        if item["id"] == loot.id:
            return item

    # Fallback — вернуть без обогащения
    return {
        "id": loot.id,
        "location_id": loot.location_id,
        "item_id": loot.item_id,
        "quantity": loot.quantity,
        "dropped_by_character_id": loot.dropped_by_character_id,
        "dropped_at": loot.dropped_at,
    }


@router.post("/{location_id}/loot/{loot_id}/pickup", response_model=schemas.LocationLootItem)
async def pickup_loot(
    location_id: int,
    loot_id: int,
    body: schemas.LocationLootPickup,
    request: Request,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_via_http),
):
    """
    Подобрать лут из локации и добавить в инвентарь персонажа.
    """
    # 1. Проверяем принадлежность персонажа
    await verify_character_ownership(session, body.character_id, current_user.id)

    # 2. Проверяем, что персонаж находится в данной локации
    async with httpx.AsyncClient(timeout=5.0) as client:
        profile_url = f"{settings.CHARACTER_SERVICE_URL}/characters/{body.character_id}/profile"
        profile_resp = await client.get(profile_url)
        if profile_resp.status_code != 200:
            raise HTTPException(status_code=404, detail="Профиль персонажа не найден")
        profile_data = profile_resp.json()

    current_location = profile_data.get("current_location_id")
    if current_location is None or int(current_location) != location_id:
        raise HTTPException(status_code=400, detail="Персонаж не находится в этой локации")

    # 3. Забираем лут (SELECT FOR UPDATE + delete)
    loot_data = await crud.pickup_location_loot(session, loot_id)
    if not loot_data:
        raise HTTPException(status_code=404, detail="Лут не найден или уже подобран")

    # Проверяем, что лут принадлежит этой локации
    if loot_data["location_id"] != location_id:
        # Компенсация: вернуть лут обратно
        await crud.create_location_loot(
            session,
            loot_data["location_id"],
            loot_data["item_id"],
            loot_data["quantity"],
            loot_data["dropped_by_character_id"],
        )
        raise HTTPException(status_code=400, detail="Лут не принадлежит этой локации")

    # 4. Добавляем предмет в инвентарь через inventory-service
    auth_header = request.headers.get("authorization", "")
    async with httpx.AsyncClient(timeout=5.0) as client:
        add_url = f"{settings.INVENTORY_SERVICE_URL}/inventory/{body.character_id}/items"
        add_resp = await client.post(
            add_url,
            json={"item_id": loot_data["item_id"], "quantity": loot_data["quantity"]},
            headers={"Authorization": auth_header},
        )
        if add_resp.status_code != 200:
            # Компенсация: вернуть лут обратно
            logger.error(
                f"Не удалось добавить предмет в инвентарь, возвращаем лут: {add_resp.text}"
            )
            await crud.create_location_loot(
                session,
                loot_data["location_id"],
                loot_data["item_id"],
                loot_data["quantity"],
                loot_data["dropped_by_character_id"],
            )
            raise HTTPException(
                status_code=500,
                detail="Не удалось добавить предмет в инвентарь",
            )

    # 5. Возвращаем данные подобранного лута
    return {
        "id": loot_data["id"],
        "location_id": loot_data["location_id"],
        "item_id": loot_data["item_id"],
        "quantity": loot_data["quantity"],
        "dropped_by_character_id": loot_data["dropped_by_character_id"],
        "dropped_at": loot_data["dropped_at"],
    }


# --------------------------------------------------------------------
# POST MODERATION — Player endpoints
# --------------------------------------------------------------------
@router.post("/posts/{post_id}/request-deletion", response_model=schemas.PostDeletionRequestRead)
async def request_post_deletion(
    post_id: int,
    body: schemas.PostDeletionRequestCreate,
    session: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """Игрок запрашивает удаление своего поста. Запрос отправляется модераторам."""
    req = await crud.create_deletion_request(session, post_id, current_user.id, body.reason)
    return {
        "id": req.id,
        "post_id": req.post_id,
        "user_id": req.user_id,
        "reason": req.reason,
        "status": req.status,
        "created_at": req.created_at,
        "reviewed_at": req.reviewed_at,
    }


@router.post("/posts/{post_id}/report", response_model=schemas.PostReportRead)
async def report_post(
    post_id: int,
    body: schemas.PostReportCreate,
    session: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """Игрок отправляет жалобу на пост. Одна жалоба от одного игрока на один пост."""
    report = await crud.create_report(session, post_id, current_user.id, body.reason)
    return {
        "id": report.id,
        "post_id": report.post_id,
        "user_id": report.user_id,
        "reason": report.reason,
        "status": report.status,
        "created_at": report.created_at,
        "reviewed_at": report.reviewed_at,
    }


# --------------------------------------------------------------------
# POST MODERATION — Admin endpoints
# --------------------------------------------------------------------
@router.get("/admin/moderation/deletion-requests", response_model=List[schemas.PostDeletionRequestRead])
async def get_deletion_requests(
    session: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_admin_user),
):
    """Список всех ожидающих запросов на удаление постов."""
    return await crud.get_pending_deletion_requests(session)


@router.get("/admin/moderation/reports", response_model=List[schemas.PostReportRead])
async def get_reports(
    session: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_admin_user),
):
    """Список всех ожидающих жалоб на посты."""
    return await crud.get_pending_reports(session)


@router.put("/admin/moderation/deletion-requests/{request_id}/review", response_model=schemas.PostDeletionRequestRead)
async def review_deletion_request(
    request_id: int,
    body: schemas.PostModerationReview,
    session: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_admin_user),
):
    """Модератор рассматривает запрос на удаление поста (approve/reject)."""
    req = await crud.review_deletion_request(session, request_id, body.action, current_user.id)
    return {
        "id": req.id,
        "post_id": req.post_id,
        "user_id": req.user_id,
        "reason": req.reason,
        "status": req.status,
        "created_at": req.created_at,
        "reviewed_at": req.reviewed_at,
    }


@router.put("/admin/moderation/reports/{report_id}/review", response_model=schemas.PostReportRead)
async def review_report(
    report_id: int,
    body: schemas.PostModerationReview,
    session: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_admin_user),
):
    """Модератор рассматривает жалобу на пост (resolve/dismiss)."""
    report = await crud.review_report(session, report_id, body.action, current_user.id)
    return {
        "id": report.id,
        "post_id": report.post_id,
        "user_id": report.user_id,
        "reason": report.reason,
        "status": report.status,
        "created_at": report.created_at,
        "reviewed_at": report.reviewed_at,
    }


# --------------------------------------------------------------------
# DIALOGUE TREES (Admin)
# --------------------------------------------------------------------
@router.post("/admin/dialogues", response_model=schemas.DialogueTreeRead)
async def create_dialogue_tree(
    body: schemas.DialogueTreeCreate,
    session: AsyncSession = Depends(get_db),
    admin: UserRead = Depends(get_admin_user),
):
    """Create a dialogue tree with nodes and options."""
    tree = await crud.create_dialogue_tree(session, body.dict())
    return tree


@router.get("/admin/dialogues", response_model=List[schemas.DialogueTreeListItem])
async def list_dialogue_trees(
    npc_id: Optional[int] = None,
    session: AsyncSession = Depends(get_db),
    admin: UserRead = Depends(get_admin_user),
):
    """List dialogue trees, optionally filtered by NPC id."""
    trees = await crud.list_dialogue_trees(session, npc_id=npc_id)
    return trees


@router.get("/admin/dialogues/{tree_id}", response_model=schemas.DialogueTreeRead)
async def get_dialogue_tree(
    tree_id: int,
    session: AsyncSession = Depends(get_db),
    admin: UserRead = Depends(get_admin_user),
):
    """Get a full dialogue tree with all nodes and options."""
    tree = await crud.get_dialogue_tree(session, tree_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Дерево диалога не найдено")
    return tree


@router.put("/admin/dialogues/{tree_id}", response_model=schemas.DialogueTreeRead)
async def update_dialogue_tree(
    tree_id: int,
    body: schemas.DialogueTreeUpdate,
    session: AsyncSession = Depends(get_db),
    admin: UserRead = Depends(get_admin_user),
):
    """Update a dialogue tree (replace all nodes/options if provided)."""
    tree = await crud.update_dialogue_tree(session, tree_id, body.dict(exclude_unset=True))
    if not tree:
        raise HTTPException(status_code=404, detail="Дерево диалога не найдено")
    return tree


@router.delete("/admin/dialogues/{tree_id}")
async def delete_dialogue_tree(
    tree_id: int,
    session: AsyncSession = Depends(get_db),
    admin: UserRead = Depends(get_admin_user),
):
    """Delete a dialogue tree and all its nodes/options."""
    deleted = await crud.delete_dialogue_tree(session, tree_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Дерево диалога не найдено")
    return {"detail": "Дерево диалога удалено"}


# --------------------------------------------------------------------
# DIALOGUE TREES (Player-facing)
# --------------------------------------------------------------------
@router.get("/npcs/{npc_id}/dialogue", response_model=schemas.DialogueNodeResponse)
async def get_npc_dialogue(
    npc_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Get the active dialogue root node for an NPC."""
    node_data = await crud.get_active_dialogue_for_npc(session, npc_id)
    if not node_data:
        raise HTTPException(status_code=404, detail="У этого NPC нет активного диалога")
    return node_data


@router.get("/npcs/{npc_id}/dialogue-quest-ids")
async def get_npc_dialogue_quest_ids(
    npc_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Get quest IDs that are linked to dialogue nodes for this NPC."""
    return await crud.get_dialogue_quest_ids(session, npc_id)


@router.post("/npcs/{npc_id}/dialogue/{node_id}/choose", response_model=schemas.DialogueNodeResponse)
async def choose_dialogue_option(
    npc_id: int,
    node_id: int,
    body: schemas.DialogueChooseRequest,
    session: AsyncSession = Depends(get_db),
):
    """Player selects a dialogue option. Returns the next node or conversation end."""
    # Verify the option belongs to this node
    node = await crud.get_dialogue_node(session, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Узел диалога не найден")

    # Find the selected option
    selected = None
    for opt in node.options:
        if opt.id == body.option_id:
            selected = opt
            break

    if not selected:
        raise HTTPException(status_code=400, detail="Вариант ответа не найден в этом узле")

    # If next_node_id is None, conversation ends
    if selected.next_node_id is None:
        return {
            "id": node_id,
            "npc_text": "Диалог завершён.",
            "action_type": None,
            "action_data": None,
            "options": [],
            "is_end": True,
        }

    next_node = await crud.get_dialogue_node(session, selected.next_node_id)
    if not next_node:
        raise HTTPException(status_code=404, detail="Следующий узел диалога не найден")

    return crud._build_node_response(next_node)


# --------------------------------------------------------------------
# NPC SHOP — Admin endpoints
# --------------------------------------------------------------------
@router.post("/admin/npc-shop/{npc_id}/items", response_model=schemas.NpcShopItemRead)
async def add_npc_shop_item(
    npc_id: int,
    body: schemas.NpcShopItemCreate,
    session: AsyncSession = Depends(get_db),
    admin: UserRead = Depends(get_admin_user),
):
    """Add an item to NPC's shop inventory."""
    shop_item = await crud.create_npc_shop_item(session, npc_id, body.dict())
    item_name = await crud.get_item_name(session, shop_item.item_id)
    return {
        "id": shop_item.id,
        "npc_id": shop_item.npc_id,
        "item_id": shop_item.item_id,
        "buy_price": shop_item.buy_price,
        "sell_price": shop_item.sell_price,
        "stock": shop_item.stock,
        "is_active": shop_item.is_active,
        "created_at": shop_item.created_at,
        "item_name": item_name,
    }


@router.get("/admin/npc-shop/{npc_id}/items", response_model=List[schemas.NpcShopItemRead])
async def list_npc_shop_items(
    npc_id: int,
    session: AsyncSession = Depends(get_db),
    admin: UserRead = Depends(get_admin_user),
):
    """List all shop items for an NPC (admin view, includes inactive)."""
    return await crud.get_npc_shop_items_admin(session, npc_id)


@router.put("/admin/npc-shop/items/{shop_item_id}", response_model=schemas.NpcShopItemRead)
async def update_npc_shop_item(
    shop_item_id: int,
    body: schemas.NpcShopItemUpdate,
    session: AsyncSession = Depends(get_db),
    admin: UserRead = Depends(get_admin_user),
):
    """Update price, stock, or active status of a shop item."""
    updated = await crud.update_npc_shop_item(session, shop_item_id, body.dict(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Товар в магазине не найден")
    item_name = await crud.get_item_name(session, updated.item_id)
    return {
        "id": updated.id,
        "npc_id": updated.npc_id,
        "item_id": updated.item_id,
        "buy_price": updated.buy_price,
        "sell_price": updated.sell_price,
        "stock": updated.stock,
        "is_active": updated.is_active,
        "created_at": updated.created_at,
        "item_name": item_name,
    }


@router.delete("/admin/npc-shop/items/{shop_item_id}")
async def delete_npc_shop_item(
    shop_item_id: int,
    session: AsyncSession = Depends(get_db),
    admin: UserRead = Depends(get_admin_user),
):
    """Remove an item from NPC's shop."""
    deleted = await crud.delete_npc_shop_item(session, shop_item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Товар в магазине не найден")
    return {"detail": "Товар удалён из магазина"}


# --------------------------------------------------------------------
# NPC SHOP — Player-facing endpoints
# --------------------------------------------------------------------

async def _fetch_charisma(character_id: int) -> Optional[int]:
    """Fetch charisma value from character-attributes-service.
    Returns None if the service is unreachable (graceful degradation).
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            url = f"{settings.ATTRIBUTES_SERVICE_URL}/attributes/{character_id}"
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("charisma", 0)
            else:
                logger.warning(
                    "Не удалось получить атрибуты персонажа %s: статус %s",
                    character_id, resp.status_code,
                )
                return None
    except Exception as exc:
        logger.warning(
            "Сервис атрибутов недоступен для персонажа %s: %s",
            character_id, exc,
        )
        return None


def _compute_charisma_discount(charisma: Optional[int]) -> float:
    """Return discount percentage (0..50) based on charisma value."""
    if charisma is None or charisma <= 0:
        return 0.0
    return min(charisma * 0.2, 50.0)


@router.get("/npcs/{npc_id}/shop", response_model=List[schemas.NpcShopItemRead])
async def get_npc_shop(
    npc_id: int,
    character_id: Optional[int] = None,
    session: AsyncSession = Depends(get_db),
):
    """Get NPC's shop items (active only, with item details).
    If character_id is provided, returns discounted_buy_price based on charisma.
    """
    items = await crud.get_npc_shop_items_player(session, npc_id)

    if character_id is not None:
        charisma = await _fetch_charisma(character_id)
        discount_pct = _compute_charisma_discount(charisma)
        result = []
        for item in items:
            item_dict = dict(item) if isinstance(item, dict) else {
                "id": item.id,
                "npc_id": item.npc_id,
                "item_id": item.item_id,
                "buy_price": item.buy_price,
                "sell_price": item.sell_price,
                "stock": item.stock,
                "is_active": item.is_active,
                "item_name": getattr(item, "item_name", None),
                "item_image": getattr(item, "item_image", None),
                "item_rarity": getattr(item, "item_rarity", None),
                "item_type": getattr(item, "item_type", None),
                "created_at": getattr(item, "created_at", None),
            }
            if discount_pct > 0:
                item_dict["discounted_buy_price"] = math.ceil(
                    item_dict["buy_price"] * (1 - discount_pct / 100)
                )
            else:
                item_dict["discounted_buy_price"] = item_dict["buy_price"]
            result.append(item_dict)
        return result

    return items


@router.post("/npcs/{npc_id}/shop/buy", response_model=schemas.ShopTransactionResponse)
async def buy_from_npc(
    npc_id: int,
    body: schemas.ShopBuyRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """
    Buy an item from NPC's shop.
    Flow:
    1. Verify character ownership
    2. Verify character is at NPC's location
    3. Check stock (if limited)
    4. Calculate total price
    5. Atomically deduct currency
    6. Add item to inventory via inventory-service
    7. Decrement stock if limited
    """
    # 1. Verify ownership
    await verify_character_ownership(session, body.character_id, current_user.id)

    # 2. Verify character is at NPC's location
    char_location = await crud.get_character_location(session, body.character_id)
    npc_location = await crud.get_npc_location(session, npc_id)
    if npc_location is None:
        raise HTTPException(status_code=404, detail="NPC не найден")
    if char_location is None or char_location != npc_location:
        raise HTTPException(status_code=400, detail="Персонаж не находится в локации этого NPC")

    # 3. Get shop item and validate
    shop_item = await crud.get_shop_item_by_id(session, body.shop_item_id)
    if not shop_item or shop_item.npc_id != npc_id or not shop_item.is_active:
        raise HTTPException(status_code=404, detail="Товар не найден в магазине этого NPC")

    if body.quantity < 1:
        raise HTTPException(status_code=400, detail="Количество должно быть >= 1")

    # Check stock
    if shop_item.stock is not None and shop_item.stock < body.quantity:
        raise HTTPException(status_code=400, detail="Недостаточно товара на складе")

    # 4. Fetch charisma and calculate discounted price
    charisma = await _fetch_charisma(body.character_id)
    discount_pct = _compute_charisma_discount(charisma)
    if discount_pct > 0:
        discounted_unit_price = math.ceil(shop_item.buy_price * (1 - discount_pct / 100))
    else:
        discounted_unit_price = shop_item.buy_price
    total_price = discounted_unit_price * body.quantity

    # 5. Atomically deduct currency
    new_balance = await crud.deduct_currency(session, body.character_id, total_price)
    if new_balance is None:
        raise HTTPException(status_code=400, detail="Недостаточно валюты")

    # 6. Add item to inventory via inventory-service
    auth_header = request.headers.get("authorization", "")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            add_url = f"{settings.INVENTORY_SERVICE_URL}/inventory/{body.character_id}/items"
            add_resp = await client.post(
                add_url,
                json={"item_id": shop_item.item_id, "quantity": body.quantity},
                headers={"Authorization": auth_header},
            )
            if add_resp.status_code != 200:
                # Compensate: refund currency
                await crud.add_currency(session, body.character_id, total_price)
                detail = "Не удалось добавить предмет в инвентарь"
                try:
                    detail = add_resp.json().get("detail", detail)
                except Exception:
                    pass
                raise HTTPException(status_code=500, detail=detail)
    except httpx.HTTPError:
        # Compensate: refund currency
        await crud.add_currency(session, body.character_id, total_price)
        raise HTTPException(status_code=503, detail="Сервис инвентаря недоступен")

    # 7. Decrement stock if limited
    if shop_item.stock is not None:
        await crud.decrement_stock(session, shop_item.id, body.quantity)

    item_name = await crud.get_item_name(session, shop_item.item_id)

    return {
        "success": True,
        "message": "Покупка совершена",
        "new_balance": new_balance,
        "item_name": item_name,
        "quantity": body.quantity,
        "total_price": total_price,
        "discount_percent": discount_pct,
    }


@router.post("/npcs/{npc_id}/shop/sell", response_model=schemas.ShopTransactionResponse)
async def sell_to_npc(
    npc_id: int,
    body: schemas.ShopSellRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """
    Sell an item to NPC.
    Flow:
    1. Verify character ownership
    2. Verify character is at NPC's location
    3. Find sell_price for this item (must be > 0)
    4. Remove item from inventory via inventory-service
    5. Add currency to character
    """
    # 1. Verify ownership
    await verify_character_ownership(session, body.character_id, current_user.id)

    # 2. Verify character is at NPC's location
    char_location = await crud.get_character_location(session, body.character_id)
    npc_location = await crud.get_npc_location(session, npc_id)
    if npc_location is None:
        raise HTTPException(status_code=404, detail="NPC не найден")
    if char_location is None or char_location != npc_location:
        raise HTTPException(status_code=400, detail="Персонаж не находится в локации этого NPC")

    if body.quantity < 1:
        raise HTTPException(status_code=400, detail="Количество должно быть >= 1")

    # 3. Find sell_price
    sell_price = await crud.find_sell_price_for_item(session, npc_id, body.item_id)
    if sell_price is None:
        raise HTTPException(status_code=400, detail="Этот NPC не покупает данный предмет")

    total_price = sell_price * body.quantity

    # 4. Remove item from inventory via inventory-service
    auth_header = request.headers.get("authorization", "")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            remove_url = (
                f"{settings.INVENTORY_SERVICE_URL}/inventory/{body.character_id}"
                f"/items/{body.item_id}?quantity={body.quantity}"
            )
            remove_resp = await client.delete(
                remove_url,
                headers={"Authorization": auth_header},
            )
            if remove_resp.status_code != 200:
                detail = "Не удалось удалить предмет из инвентаря"
                try:
                    detail = remove_resp.json().get("detail", detail)
                except Exception:
                    pass
                raise HTTPException(status_code=remove_resp.status_code, detail=detail)
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Сервис инвентаря недоступен")

    # 5. Add currency to character
    new_balance = await crud.add_currency(session, body.character_id, total_price)

    item_name = await crud.get_item_name(session, body.item_id)

    return {
        "success": True,
        "message": "Продажа совершена",
        "new_balance": new_balance,
        "item_name": item_name,
        "quantity": body.quantity,
        "total_price": total_price,
    }


# --------------------------------------------------------------------
# QUESTS — Admin endpoints
# --------------------------------------------------------------------
@router.post("/admin/quests", response_model=schemas.QuestRead)
async def create_quest(
    body: schemas.QuestCreate,
    session: AsyncSession = Depends(get_db),
    admin: UserRead = Depends(get_admin_user),
):
    """Create a new quest with objectives."""
    data = body.dict()
    # Convert objectives from Pydantic models to dicts
    data["objectives"] = [obj.dict() for obj in body.objectives]
    quest = await crud.create_quest(session, data)
    return quest


@router.get("/admin/quests", response_model=List[schemas.QuestListItem])
async def list_quests_admin(
    npc_id: Optional[int] = None,
    quest_type: Optional[str] = None,
    session: AsyncSession = Depends(get_db),
    admin: UserRead = Depends(get_admin_user),
):
    """List all quests with optional filters."""
    return await crud.get_quests_admin(session, npc_id=npc_id, quest_type=quest_type)


@router.get("/admin/quests/{quest_id}", response_model=schemas.QuestRead)
async def get_quest_admin(
    quest_id: int,
    session: AsyncSession = Depends(get_db),
    admin: UserRead = Depends(get_admin_user),
):
    """Get quest details with objectives."""
    quest = await crud.get_quest_by_id(session, quest_id)
    if not quest:
        raise HTTPException(status_code=404, detail="Квест не найден")
    return quest


@router.put("/admin/quests/{quest_id}", response_model=schemas.QuestRead)
async def update_quest_admin(
    quest_id: int,
    body: schemas.QuestUpdate,
    session: AsyncSession = Depends(get_db),
    admin: UserRead = Depends(get_admin_user),
):
    """Update a quest. If objectives are provided, they replace existing ones."""
    data = body.dict(exclude_unset=True)
    if "objectives" in data and data["objectives"] is not None:
        data["objectives"] = [obj.dict() for obj in body.objectives]
    updated = await crud.update_quest(session, quest_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Квест не найден")
    return updated


@router.delete("/admin/quests/{quest_id}")
async def delete_quest_admin(
    quest_id: int,
    session: AsyncSession = Depends(get_db),
    admin: UserRead = Depends(get_admin_user),
):
    """Delete a quest."""
    deleted = await crud.delete_quest(session, quest_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Квест не найден")
    return {"detail": "Квест удалён"}


# --------------------------------------------------------------------
# QUESTS — Player-facing endpoints
# --------------------------------------------------------------------
@router.get("/npcs/{npc_id}/quests")
async def get_npc_quests(
    npc_id: int,
    character_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Get all quests from an NPC with player_status for a specific character."""
    return await crud.get_available_quests_for_npc(session, npc_id, character_id)


@router.post("/quests/{quest_id}/accept")
async def accept_quest(
    quest_id: int,
    body: schemas.QuestAcceptRequest,
    session: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """Accept a quest."""
    await verify_character_ownership(session, body.character_id, current_user.id)
    cq = await crud.accept_quest(session, quest_id, body.character_id)
    return {"detail": "Квест принят", "character_quest_id": cq.id}


@router.get("/quests/active", response_model=List[schemas.ActiveQuestRead])
async def get_active_quests(
    character_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Get player's active quests with progress."""
    return await crud.get_active_quests(session, character_id)


@router.post("/quests/{quest_id}/complete", response_model=schemas.QuestCompleteResponse)
async def complete_quest(
    quest_id: int,
    body: schemas.QuestCompleteRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """
    Attempt to complete a quest. Checks all objectives are done.
    Awards rewards: currency (direct SQL), exp (direct SQL), items (inventory-service).
    """
    await verify_character_ownership(session, body.character_id, current_user.id)

    # Check if quest is completable
    check = await crud.check_quest_completable(session, body.character_id, quest_id)
    if not check:
        raise HTTPException(status_code=404, detail="Активный квест не найден")
    if not check["all_completed"]:
        raise HTTPException(status_code=400, detail="Не все задачи выполнены")

    # Get quest for rewards
    quest = await crud.get_quest_by_id(session, quest_id)
    if not quest:
        raise HTTPException(status_code=404, detail="Квест не найден")

    # Award currency
    new_balance = None
    if quest.reward_currency > 0:
        new_balance = await crud.add_currency(session, body.character_id, quest.reward_currency)

    # Award experience
    if quest.reward_exp > 0:
        await crud.add_experience(session, body.character_id, quest.reward_exp)

    # Award items via inventory-service
    if quest.reward_items:
        auth_header = request.headers.get("authorization", "")
        for reward_item in quest.reward_items:
            item_id = reward_item.get("item_id")
            quantity = reward_item.get("quantity", 1)
            if not item_id:
                continue
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    add_url = f"{settings.INVENTORY_SERVICE_URL}/inventory/{body.character_id}/items"
                    add_resp = await client.post(
                        add_url,
                        json={"item_id": item_id, "quantity": quantity},
                        headers={"Authorization": auth_header},
                    )
                    if add_resp.status_code != 200:
                        logger.warning(
                            f"Failed to add reward item {item_id} for quest {quest_id}: "
                            f"{add_resp.status_code}"
                        )
            except httpx.HTTPError as e:
                logger.warning(f"Inventory service error for quest reward: {e}")

    # Mark quest as completed
    await crud.complete_quest_record(session, check["character_quest_id"])

    return {
        "success": True,
        "message": "Квест выполнен! Награды получены.",
        "reward_currency": quest.reward_currency,
        "reward_exp": quest.reward_exp,
        "reward_items": quest.reward_items,
        "new_balance": new_balance,
    }


@router.post("/quests/{quest_id}/abandon")
async def abandon_quest(
    quest_id: int,
    body: schemas.QuestAbandonRequest,
    session: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(get_current_user_via_http),
):
    """Abandon an active quest."""
    await verify_character_ownership(session, body.character_id, current_user.id)
    abandoned = await crud.abandon_quest(session, body.character_id, quest_id)
    if not abandoned:
        raise HTTPException(status_code=404, detail="Активный квест не найден")
    return {"detail": "Квест отменён"}


@router.post("/quests/progress/update")
async def update_quest_progress(
    body: schemas.QuestProgressUpdateRequest,
    session: AsyncSession = Depends(get_db),
):
    """
    Update objective progress. Called by game systems when player kills mob,
    collects item, etc.
    """
    result = await crud.update_quest_progress(
        session, body.character_id, body.quest_id, body.objective_id, body.increment
    )
    if not result:
        raise HTTPException(status_code=404, detail="Прогресс квеста не найден")
    return result


# --------------------------------------------------------------------
# ARCHIVE (Lore Wiki)
# --------------------------------------------------------------------
archive_router = APIRouter(prefix="/archive")


@archive_router.get("/articles", response_model=schemas.ArchiveSearchResult)
async def list_articles(
    category_slug: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    session: AsyncSession = Depends(get_db),
):
    """List articles with optional category/search filters and pagination."""
    articles, total = await crud.get_articles(session, category_slug=category_slug, search=search, page=page, per_page=per_page)
    return {"articles": articles, "total": total}


@archive_router.get("/articles/preview/{slug}", response_model=schemas.ArchiveArticlePreview)
async def get_article_preview(slug: str, session: AsyncSession = Depends(get_db)):
    """Get minimal article data for hover preview tooltip."""
    return await crud.get_article_preview(session, slug)


@archive_router.get("/articles/{slug}", response_model=schemas.ArchiveArticleRead)
async def get_article_by_slug(slug: str, session: AsyncSession = Depends(get_db)):
    """Get full article by slug."""
    return await crud.get_article_by_slug(session, slug)


@archive_router.get("/categories", response_model=List[schemas.ArchiveCategoryWithCount])
async def list_categories(session: AsyncSession = Depends(get_db)):
    """List all categories with article counts."""
    return await crud.get_all_categories(session)


@archive_router.get("/featured", response_model=List[schemas.ArchiveArticleListItem])
async def get_featured_articles(session: AsyncSession = Depends(get_db)):
    """Get featured articles."""
    return await crud.get_featured_articles(session)


@archive_router.post("/articles/create", response_model=schemas.ArchiveArticleRead)
async def create_article(
    body: schemas.ArchiveArticleCreate,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("archive:create")),
):
    """Create a new archive article."""
    return await crud.create_article(session, body, user_id=current_user.id)


@archive_router.put("/articles/{id}/update", response_model=schemas.ArchiveArticleRead)
async def update_article(
    id: int,
    body: schemas.ArchiveArticleUpdate,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("archive:update")),
):
    """Update an existing archive article."""
    return await crud.update_article(session, id, body)


@archive_router.delete("/articles/{id}/delete")
async def delete_article(
    id: int,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("archive:delete")),
):
    """Delete an archive article."""
    await crud.delete_article(session, id)
    return {"status": "success"}


@archive_router.post("/categories/create", response_model=schemas.ArchiveCategoryRead)
async def create_category(
    body: schemas.ArchiveCategoryCreate,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("archive:create")),
):
    """Create a new archive category."""
    return await crud.create_category(session, body)


@archive_router.put("/categories/{id}/update", response_model=schemas.ArchiveCategoryRead)
async def update_category(
    id: int,
    body: schemas.ArchiveCategoryUpdate,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("archive:update")),
):
    """Update an existing archive category."""
    return await crud.update_category(session, id, body)


@archive_router.delete("/categories/{id}/delete")
async def delete_category(
    id: int,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("archive:delete")),
):
    """Delete an archive category."""
    await crud.delete_category(session, id)
    return {"status": "success"}


@archive_router.put("/categories/reorder")
async def reorder_categories(
    items: List[dict],
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("archive:update")),
):
    """Reorder categories by providing list of {id, sort_order} dicts."""
    await crud.reorder_categories(session, items)
    return {"status": "success"}


# --------------------------------------------------------------------
# Подключаем маршруты
# --------------------------------------------------------------------
app.include_router(router)
app.include_router(rules_router)
app.include_router(archive_router)

