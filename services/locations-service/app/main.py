import os
from typing import List
from fastapi import FastAPI, Depends, HTTPException, APIRouter
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
from auth_http import get_admin_user, get_current_user_via_http, require_permission
from sqlalchemy import text

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
async def create_new_post(post_data: schemas.PostCreate, session: AsyncSession = Depends(get_db), current_user=Depends(get_current_user_via_http)):
    await verify_character_ownership(session, post_data.character_id, current_user.id)
    return await crud.create_post(session, post_data)

@router.get("/{location_id}/posts/", response_model=List[schemas.PostResponse])
async def get_posts_in_location(location_id: int, session: AsyncSession = Depends(get_db)):
    return await crud.get_posts_by_location(session, location_id)

@router.get("/admin/data", response_model=schemas.AdminPanelData)
async def get_admin_panel_data_route(session: AsyncSession = Depends(get_db), current_user=Depends(require_permission("locations:read"))):
    """
    Возвращает все данные для админ панели одним запросом
    """
    return await crud.get_admin_panel_data(session)


@router.get("/{location_id}/client/details", response_model=schemas.LocationClientDetails)
async def get_location_client_details(location_id: int, session: AsyncSession = Depends(get_db)):
    """
    Возвращает детальную информацию о локации для клиента.
    Помимо базовых данных локации, включает:
      - Список соседей
      - Список персонажей (игроков) в локации
      - Посты пользователей, обогащенные информацией о профиле автора, полученной из Character‑service
    """
    data = await crud.get_client_location_details(session, location_id)
    if not data:
        raise HTTPException(status_code=404, detail="Location not found")
    return data


@router.post("/{destination_location_id}/move_and_post", response_model=schemas.PostResponse)
async def move_and_post(
        destination_location_id: int,
        movement: schemas.MovementPostRequest,
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
# Подключаем маршруты
# --------------------------------------------------------------------
app.include_router(router)
app.include_router(rules_router)

