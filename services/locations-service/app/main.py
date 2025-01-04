from typing import List

from fastapi import FastAPI, Depends, HTTPException, APIRouter
from sqlalchemy.orm import Session
import models
import schemas
import crud
from database import SessionLocal, engine, get_db
from fastapi.middleware.cors import CORSMiddleware

# Создаем все таблицы в базе данных, если они еще не созданы
models.Base.metadata.create_all(bind=engine)

# Создаем экземпляр приложения FastAPI
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/locations")


# Создание района
@router.post("/districts/", response_model=schemas.District)
def create_new_district(
    district_data: schemas.DistrictCreate,
    session: Session = Depends(get_db)
):
    """
    Создает новый район.
    """
    return crud.create_district(session, district_data)


# Создание локации или подрайона
@router.post("/", response_model=schemas.Location)
def create_new_location(location_data: schemas.LocationCreate, session: Session = Depends(get_db)):
    """
    Создает новую локацию или подрайон.
    """
    # Проверяем, что parent_id существует, если оно указано
    if location_data.parent_id:
        parent = crud.get_location_by_id(session, location_data.parent_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Parent location not found")
    return crud.create_location(session, location_data)


# Добавление соседа
@router.post("/{location_id}/neighbors/", response_model=schemas.LocationNeighbor)
def create_neighbor(location_id: int, neighbor_data: schemas.LocationNeighborCreate, session: Session = Depends(get_db)):
    """
    Добавляет соседа для локации.
    """
    # Проверяем существование location_id и neighbor_id
    location = crud.get_location_by_id(session, location_id)
    neighbor = crud.get_location_by_id(session, neighbor_data.neighbor_id)

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    if not neighbor:
        raise HTTPException(status_code=404, detail="Neighbor location not found")

    return crud.add_neighbor(session, location_id, neighbor_data.neighbor_id, neighbor_data.energy_cost)

#Получение информации о регионе
@router.get("/regions/{region_id}/details/", response_model=schemas.Region)
def get_region_details_route(region_id: int, session: Session = Depends(get_db)):
    """
    Возвращает данные о регионе с учетом карты, правителя и входной локации.
    """
    region = crud.get_region_details(session, region_id)
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")
    return region

@router.get("/{location_id}/details")
def get_location_details_route(location_id: int, session: Session = Depends(get_db)):
    """
    Возвращает всю информацию о локации, включая описание, соседей и подлокации.
    """
    result = crud.get_location_details(session, location_id)
    if not result:
        raise HTTPException(status_code=404, detail="Location not found")
    return result

@router.get("/locations/{location_id}/posts/", response_model=List[schemas.PostResponse])
def get_posts(location_id: int, session: Session = Depends(get_db)):
    """
    Возвращает все посты в указанной локации.
    """
    return crud.get_posts_by_location(session, location_id)


@router.post("/posts/", response_model=schemas.PostResponse)
def create_new_post(post_data: schemas.PostCreate, session: Session = Depends(get_db)):
    """
    Создает новый пост в указанной локации.
    """
    # Создаем пост
    new_post = crud.create_post(
        session=session,
        character_id=post_data.character_id,
        location_id=post_data.location_id,
        content=post_data.content
    )
    return new_post

@router.put("/regions/{region_id}", response_model=schemas.Region)
def update_region_route(region_id: int, data: dict, session: Session = Depends(get_db)):
    """
    Обновляет данные региона.
    """
    return crud.update_region(session, region_id, data)

@router.post("/regions/{region_id}/map_points/", response_model=List[schemas.MapPointCreate])
def add_map_point_route(region_id: int, point_data: dict, session: Session = Depends(get_db)):
    """
    Добавляет точку на карту региона.
    """
    return crud.add_map_point(session, region_id, point_data)

@router.post("/countries/{country_id}/map_points/", response_model=List[schemas.MapPointCreate])
def add_map_point_country_route(country_id: int, point_data: dict, session: Session = Depends(get_db)):
    """
    Добавляет точку на карту страны.
    """
    return crud.add_country_map_point(session, country_id, point_data)

@router.get("/countries/", response_model=List[schemas.Country])
def get_all_countries_route(session: Session = Depends(get_db)):
    """
    Возвращает список всех стран с полной информацией.
    """
    return crud.get_all_countries_with_details(session)


# Подключаем маршруты
app.include_router(router)
