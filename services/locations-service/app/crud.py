from fastapi import HTTPException
from sqlalchemy.orm import Session
from models import District, Location, LocationPath, LocationNeighbor, Region, Post
from schemas import DistrictCreate, LocationCreate, Country


# Создание района
def create_district(session: Session, district_data: DistrictCreate) -> District:
    new_district = District(**district_data.dict())
    session.add(new_district)
    session.commit()
    session.refresh(new_district)
    return new_district


# Получение локации по ID
def get_location_by_id(session: Session, location_id: int) -> Location:
    """
    Возвращает локацию по ID.
    """
    return session.query(Location).filter(Location.id == location_id).first()


# Создание локации или подрайона
def create_location(session: Session, location_data: LocationCreate) -> Location:
    """
    Создает новую локацию или подрайон.
    """
    new_location = Location(**location_data.dict())
    session.add(new_location)
    session.commit()
    session.refresh(new_location)

    # Заполнение таблицы LocationsPath
    if location_data.parent_id:
        parent_paths = session.query(LocationPath).filter(LocationPath.descendant_id == location_data.parent_id).all()
        for path in parent_paths:
            session.add(
                LocationPath(
                    ancestor_id=path.ancestor_id,
                    descendant_id=new_location.id,
                    depth=path.depth + 1
                )
            )
    session.add(
        LocationPath(
            ancestor_id=new_location.id,
            descendant_id=new_location.id,
            depth=0
        )
    )
    session.commit()
    return new_location


# Добавление соседа

def add_neighbor(session: Session, location_id: int, neighbor_id: int, energy_cost: int) -> dict:
    """
    Добавляет связь между двумя локациями и автоматически создает обратную связь.
    """
    # Добавляем прямую связь
    forward_neighbor = LocationNeighbor(
        location_id=location_id,
        neighbor_id=neighbor_id,
        energy_cost=energy_cost
    )
    session.add(forward_neighbor)

    # Добавляем обратную связь
    reverse_neighbor = LocationNeighbor(
        location_id=neighbor_id,
        neighbor_id=location_id,
        energy_cost=energy_cost  # Можно изменить логику, если стоимость отличается
    )
    session.add(reverse_neighbor)

    session.commit()

    return {
        "forward": {
            "location_id": forward_neighbor.location_id,
            "neighbor_id": forward_neighbor.neighbor_id,
            "energy_cost": forward_neighbor.energy_cost,
        },
        "reverse": {
            "location_id": reverse_neighbor.location_id,
            "neighbor_id": reverse_neighbor.neighbor_id,
            "energy_cost": reverse_neighbor.energy_cost,
        },
    }


def get_nested_locations(session: Session, parent_id: int):
    """
    Рекурсивно получает вложенные локации и подрайоны для указанного parent_id.
    """
    locations = (
        session.query(Location)
        .filter(Location.parent_id == parent_id)
        .all()
    )

    result = []
    for location in locations:
        location_data = {
            "location_id": location.id,
            "location_name": location.name,
            "type": location.type,
            "image_url": location.image_url,
            "children": get_nested_locations(session, location.id),  # Рекурсия
        }
        result.append(location_data)

    return result

# Получение всех локаций в регионе
def get_region_details(session: Session, region_id: int):
    """
    Возвращает все районы, локации и подрайоны для указанного региона.
    """
    # Получаем регион
    region = session.query(Region).filter(Region.id == region_id).first()
    if not region:
        return None

    # Формируем вложенную структуру
    result = {
        "region_id": region.id,
        "region_name": region.name,
        "region_description": region.description,
        "districts": [],
    }

    # Получаем районы в регионе
    districts = session.query(District).filter(District.region_id == region.id).all()
    for district in districts:
        district_data = {
            "district_id": district.id,
            "district_name": district.name,
            "district_image": district.image_url,
            "locations": [],
        }

        # Получаем локации верхнего уровня (без parent_id) для района
        locations = (
            session.query(Location)
            .filter(Location.district_id == district.id)
            .filter(Location.parent_id.is_(None))
            .all()
        )

        for location in locations:
            location_data = {
                "location_id": location.id,
                "location_name": location.name,
                "type": location.type,
                "image_url": location.image_url,
                "children": get_nested_locations(session, location.id),  # Рекурсия
            }
            district_data["locations"].append(location_data)

        result["districts"].append(district_data)

    return result

def get_location_details(session: Session, location_id: int):
    """
    Возвращает информацию о конкретной локации, включая описание, соседей и подлокации.
    """
    location = session.query(Location).filter(Location.id == location_id).first()
    if not location:
        return None

    # Получаем соседей
    neighbors = session.query(LocationNeighbor).filter(LocationNeighbor.location_id == location_id).all()

    # Получаем подлокации
    children = session.query(Location).filter(Location.parent_id == location_id).all()

    return {
        "location_id": location.id,
        "name": location.name,
        "type": location.type,
        "description": location.description,
        "image_url": location.image_url,
        "recommended_level": location.recommended_level,
        "quick_travel_marker": location.quick_travel_marker,
        "district_id": location.district_id,
        "neighbors": [
            {
                "neighbor_id": neighbor.neighbor_id,
                "energy_cost": neighbor.energy_cost,
            }
            for neighbor in neighbors
        ],
        "children": [
            {
                "location_id": child.id,
                "name": child.name,
                "type": child.type,
                "image_url": child.image_url,
            }
            for child in children
        ],
    }

#Получение постов
def get_posts_by_location(session: Session, location_id: int):
    """
    Получает все посты в указанной локации.
    """
    return session.query(Post).filter(Post.location_id == location_id).all()

def create_post(session: Session, character_id: int, location_id: int, content: str) -> Post:
    """
    Создает новый пост в локации.
    """
    # Создаем новый пост
    new_post = Post(character_id=character_id, location_id=location_id, content=content)
    session.add(new_post)
    session.commit()
    session.refresh(new_post)  # Обновляем объект с присвоенным ID
    return new_post

def update_region(session: Session, region_id: int, data: dict) -> Region:
    """
    Обновляет данные региона.
    """
    region = session.query(Region).filter(Region.id == region_id).first()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")

    if "name" in data:
        region.name = data["name"]
    if "description" in data:
        region.description = data["description"]
    if "image_url" in data:
        region.image_url = data["image_url"]
    if "map_image_url" in data:
        region.map_image_url = data["map_image_url"]
    if "map_points" in data:
        region.map_points = data["map_points"]
    if "ruler_id" in data:
        region.ruler_id = data["ruler_id"]
    if "entrance_location_id" in data:
        region.entrance_location_id = data["entrance_location_id"]

    session.commit()
    session.refresh(region)
    return region


def add_map_point(session: Session, region_id: int, point_data: dict) -> list:
    """
    Добавляет точку на карту региона.
    """
    region = session.query(Region).filter(Region.id == region_id).first()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")

    map_points = region.map_points or []
    map_points.append(point_data)
    region.map_points = map_points

    session.commit()
    return map_points

def add_country_map_point(session: Session, country_id: int, point_data: dict) -> list:
    """
    Добавляет точку на карту региона.
    """
    country = session.query(Country).filter(Country.id == country_id).first()
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")

    map_points = country.map_points or []
    map_points.append(point_data)
    country.map_points = map_points

    session.commit()
    return map_points

def get_all_countries_with_details(session: Session) -> list:
    """
    Возвращает список всех стран с полной информацией.
    """
    countries = session.query(Country).all()

    return [
        {
            "id": country.id,
            "name": country.name,
            "description": country.description,
            "country_image_url": country.country_image_url,
            "map_image_url": country.map_image_url,
            "map_points": country.map_points,
            "leader_id": country.leader_id,
        }
        for country in countries
    ]
