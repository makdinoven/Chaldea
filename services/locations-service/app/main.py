from typing import List
from fastapi import FastAPI, Depends, HTTPException, APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio

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


# --------------------------------------------------------------------
# DISTRICT
# --------------------------------------------------------------------
@router.post("/districts/", response_model=schemas.DistrictRead)
async def create_new_district(district_data: schemas.DistrictCreate, session: AsyncSession = Depends(get_db)):
    return await crud.create_district(session, district_data)

@router.put("/districts/{district_id}/update", response_model=schemas.DistrictRead)
async def update_district_route(district_id: int, body: schemas.DistrictUpdate, session: AsyncSession = Depends(get_db)):
    return await crud.update_district(session, district_id, body)


# --------------------------------------------------------------------
# LOCATION
# --------------------------------------------------------------------
@router.post("/", response_model=schemas.LocationRead)
async def create_new_location(location_data: schemas.LocationCreate, session: AsyncSession = Depends(get_db)):
    if location_data.parent_id:
        parent = await crud.get_location_by_id(session, location_data.parent_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Parent location not found")
    return await crud.create_location(session, location_data)

@router.put("/{location_id}/update", response_model=schemas.LocationRead)
async def update_location_route(location_id: int, body: schemas.LocationUpdate, session: AsyncSession = Depends(get_db)):
    return await crud.update_location(session, location_id, body)

@router.get("/{location_id}/details")
async def get_location_details_route(location_id: int, session: AsyncSession = Depends(get_db)):
    data = await crud.get_location_details(session, location_id)
    if not data:
        raise HTTPException(status_code=404, detail="Location not found")
    return data


# --------------------------------------------------------------------
# NEIGHBORS
# --------------------------------------------------------------------
@router.post("/{location_id}/neighbors/", response_model=schemas.LocationNeighbor)
async def create_neighbor(location_id: int, neighbor_data: schemas.LocationNeighborCreate, session: AsyncSession = Depends(get_db)):
    loc = await crud.get_location_by_id(session, location_id)
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")

    neighbor = await crud.get_location_by_id(session, neighbor_data.neighbor_id)
    if not neighbor:
        raise HTTPException(status_code=404, detail="Neighbor location not found")

    return await crud.add_neighbor(session, location_id, neighbor_data.neighbor_id, neighbor_data.energy_cost)


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

