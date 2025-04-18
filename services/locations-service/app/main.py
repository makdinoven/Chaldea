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
from database import engine, get_db
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

@app.on_event("startup")
async def startup():
    # создаем таблицы при запуске приложения
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/locations")


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
async def create_country_route(body: schemas.CountryCreate, session: AsyncSession = Depends(get_db)):
    new_c = await crud.create_new_country(
        session,
        name=body.name,
        description=body.description,
        leader_id=body.leader_id,
        map_image_url=body.map_image_url
    )
    return new_c

@router.put("/countries/{country_id}/update", response_model=schemas.CountryRead)
async def update_country_route(country_id: int, body: schemas.CountryUpdate, session: AsyncSession = Depends(get_db)):
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
async def create_region_route(body: schemas.RegionCreate, session: AsyncSession = Depends(get_db)):
    new_r = await crud.create_new_region(session, body)
    return new_r

@router.put("/regions/{region_id}/update", response_model=schemas.RegionUpdateResponse)
async def update_region_route(region_id: int, body: schemas.RegionUpdate, session: AsyncSession = Depends(get_db)):
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
    session: AsyncSession = Depends(get_db)
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
    session: AsyncSession = Depends(get_db)
):
    try:
        return await crud.create_district(session, district)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Не удалось создать район: {str(e)}"
        )

@router.put("/districts/{district_id}/update", response_model=schemas.DistrictRead)
async def update_district_route(district_id: int, body: schemas.DistrictUpdate, session: AsyncSession = Depends(get_db)):
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
    session: AsyncSession = Depends(get_db)
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
async def create_location(location: schemas.LocationCreate, db: AsyncSession = Depends(get_db)):
    try:
        db_location = await crud.create_location(db, location)
        # Возвращаем только базовые поля без связанных данных
        return {
            "id": db_location.id,
            "name": db_location.name,
            "district_id": db_location.district_id,
            "type": db_location.type,
            "image_url": db_location.image_url,
            "recommended_level": db_location.recommended_level,
            "quick_travel_marker": db_location.quick_travel_marker,
            "parent_id": db_location.parent_id,
            "description": db_location.description
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{location_id}/update", response_model=schemas.LocationRead)
async def update_location_route(location_id: int, body: schemas.LocationUpdate, session: AsyncSession = Depends(get_db)):
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
            "description": db_location.description or ""
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
    session: AsyncSession = Depends(get_db)
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
async def create_neighbor(location_id: int, neighbor_data: schemas.LocationNeighborCreate, session: AsyncSession = Depends(get_db)):
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
async def delete_neighbor(location_id: int, neighbor_id: int, session: AsyncSession = Depends(get_db)):
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
    db: AsyncSession = Depends(get_db)
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
async def create_new_post(post_data: schemas.PostCreate, session: AsyncSession = Depends(get_db)):
    return await crud.create_post(session, post_data)

@router.get("/{location_id}/posts/", response_model=List[schemas.PostResponse])
async def get_posts_in_location(location_id: int, session: AsyncSession = Depends(get_db)):
    return await crud.get_posts_by_location(session, location_id)

@router.get("/admin/data", response_model=schemas.AdminPanelData)
async def get_admin_panel_data_route(session: AsyncSession = Depends(get_db)):
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
        session: AsyncSession = Depends(get_db)
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
    # 1. Получаем профиль персонажа (чтобы узнать current_location_id)
    async with httpx.AsyncClient(timeout=5.0) as client:
        profile_url = f"{settings.CHARACTER_SERVICE_URL}/characters/{movement.character_id}/profile"
        profile_resp = await client.get(profile_url)
        if profile_resp.status_code != 200:
            raise HTTPException(status_code=404, detail="Character profile not found")
        profile_data = profile_resp.json()
    current_location = profile_data.get("current_location_id")  # может быть NULL

    # 2. Проверяем, можно ли переходить в целевую локацию
    if current_location == destination_location_id:
        movement_cost = 0
    else:
        q = await session.execute(
            select(models.LocationNeighbor).where(
                models.LocationNeighbor.location_id == current_location,
                models.LocationNeighbor.neighbor_id == destination_location_id
            )
        )
        neighbor = q.scalars().first()
        if not neighbor:
            raise HTTPException(status_code=400,
                                detail="Destination is not adjacent to current location")
        movement_cost = neighbor.energy_cost
    # Если current_location is NULL, переезд разрешён без дополнительной стоимости.

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
# Подключаем маршруты
# --------------------------------------------------------------------
app.include_router(router)

