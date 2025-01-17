from typing import List
from fastapi import FastAPI, Depends, HTTPException, APIRouter
from sqlalchemy.orm import Session

import models
import schemas
import crud
from database import SessionLocal, engine, get_db
from fastapi.middleware.cors import CORSMiddleware

# Создаем таблицы, если их нет
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

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
def locations_lookup(session: Session = Depends(get_db)):
    data = crud.get_locations_lookup(session)
    return data

@router.get("/districts/lookup", response_model=List[schemas.DistrictLookup])
def districts_lookup(session: Session = Depends(get_db)):
    data = crud.get_districts_lookup(session)
    return data

@router.get("/countries/lookup", response_model=List[schemas.CountryLookup])
def countries_lookup(session: Session = Depends(get_db)):
    """
    Возвращает список всех стран (id, name).
    """
    data = crud.get_countries_lookup(session)
    return data



# --------------------------------------------------------------------
# COUNTRY
# --------------------------------------------------------------------
@router.post("/countries/create", response_model=schemas.CountryRead)
def create_country_route(body: schemas.CountryCreate, session: Session = Depends(get_db)):
    new_c = crud.create_new_country(
        session,
        name=body.name,
        description=body.description,
        leader_id=body.leader_id,
        map_image_url=body.map_image_url
    )
    return new_c

@router.put("/countries/{country_id}/update", response_model=schemas.CountryRead)
def update_country_route(country_id: int, body: schemas.CountryUpdate, session: Session = Depends(get_db)):
    db_obj = crud.update_country(session, country_id, body)
    return db_obj

#
# >>> НОВЫЙ МАРШРУТ: /countries/{country_id}/details
#
@router.get("/countries/{country_id}/details")
def get_country_details_route(country_id: int, session: Session = Depends(get_db)):
    """
    Возвращает полную информацию о стране (id, name, description, leader_id, map_image_url)
    + Список регионов, у которых только (id, name, image_url, x, y).
    """
    data = crud.get_country_details(session, country_id)
    if not data:
        raise HTTPException(status_code=404, detail="Country not found")
    return data


# --------------------------------------------------------------------
# REGION
# --------------------------------------------------------------------
@router.post("/regions/create", response_model=schemas.RegionRead)
def create_region_route(body: schemas.RegionCreate, session: Session = Depends(get_db)):
    new_r = crud.create_new_region(session, body)
    return new_r

@router.put("/regions/{region_id}/update", response_model=schemas.RegionRead)
def update_region_route(region_id: int, body: schemas.RegionUpdate, session: Session = Depends(get_db)):
    return crud.update_region(session, region_id, body)

#
# >>> НОВЫЙ МАРШРУТ: /regions/{region_id}/details
#
@router.get("/regions/{region_id}/details")
def get_region_full_details_route(region_id: int, session: Session = Depends(get_db)):
    """
    Возвращает всю информацию о регионе (id, country_id, name, description, image_url, entrance_location_id,
    leader_id, x, y) + список районов. Для района:
    - все поля (id, name, ... x, y)
    - entry_location: {id, name}, если есть
    - все локации с рекурсивной вложенностью.
    """
    data = crud.get_region_full_details(session, region_id)
    if not data:
        raise HTTPException(status_code=404, detail="Region not found")
    return data


# --------------------------------------------------------------------
# DISTRICT
# --------------------------------------------------------------------
@router.post("/districts/", response_model=schemas.DistrictRead)
def create_new_district(district_data: schemas.DistrictCreate, session: Session = Depends(get_db)):
    return crud.create_district(session, district_data)

@router.put("/districts/{district_id}/update", response_model=schemas.DistrictRead)
def update_district_route(district_id: int, body: schemas.DistrictUpdate, session: Session = Depends(get_db)):
    return crud.update_district(session, district_id, body)


# --------------------------------------------------------------------
# LOCATION
# --------------------------------------------------------------------
@router.post("/", response_model=schemas.LocationRead)
def create_new_location(location_data: schemas.LocationCreate, session: Session = Depends(get_db)):
    if location_data.parent_id:
        parent = crud.get_location_by_id(session, location_data.parent_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Parent location not found")
    return crud.create_location(session, location_data)

@router.put("/{location_id}/update", response_model=schemas.LocationRead)
def update_location_route(location_id: int, body: schemas.LocationUpdate, session: Session = Depends(get_db)):
    return crud.update_location(session, location_id, body)

@router.get("/{location_id}/details")
def get_location_details_route(location_id: int, session: Session = Depends(get_db)):
    data = crud.get_location_details(session, location_id)
    if not data:
        raise HTTPException(status_code=404, detail="Location not found")
    return data


# --------------------------------------------------------------------
# NEIGHBORS
# --------------------------------------------------------------------
@router.post("/{location_id}/neighbors/", response_model=schemas.LocationNeighbor)
def create_neighbor(location_id: int, neighbor_data: schemas.LocationNeighborCreate, session: Session = Depends(get_db)):
    loc = crud.get_location_by_id(session, location_id)
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")

    neighbor = crud.get_location_by_id(session, neighbor_data.neighbor_id)
    if not neighbor:
        raise HTTPException(status_code=404, detail="Neighbor location not found")

    return crud.add_neighbor(session, location_id, neighbor_data.neighbor_id, neighbor_data.energy_cost)


# --------------------------------------------------------------------
# POSTS
# --------------------------------------------------------------------
@router.post("/posts/", response_model=schemas.PostResponse)
def create_new_post(post_data: schemas.PostCreate, session: Session = Depends(get_db)):
    return crud.create_post(session, post_data)

@router.get("/{location_id}/posts/", response_model=List[schemas.PostResponse])
def get_posts_in_location(location_id: int, session: Session = Depends(get_db)):
    return crud.get_posts_by_location(session, location_id)


# --------------------------------------------------------------------
# Подключаем маршруты
# --------------------------------------------------------------------
app.include_router(router)
