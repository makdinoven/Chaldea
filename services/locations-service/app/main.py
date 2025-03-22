from typing import List
from fastapi import FastAPI, Depends, HTTPException, APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

import models
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
    allow_origins=["http://4452515-co41851.twc1.net"],
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


# --------------------------------------------------------------------
# LOCATION
# --------------------------------------------------------------------
@router.post("/", response_model=schemas.LocationCreate)
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

# --------------------------------------------------------------------
# Подключаем маршруты
# --------------------------------------------------------------------
app.include_router(router)

