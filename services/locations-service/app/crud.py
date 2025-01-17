from fastapi import HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from models import (
    Country, Region, District, Location, LocationNeighbor, Post
)
from schemas import (
    DistrictCreate, LocationCreate, PostCreate
)

# -------------------------------
#   Рекурсивный сбор вложенных локаций
# -------------------------------
def get_location_tree(session: Session, location: Location) -> dict:
    """
    Рекурсивно собирает дерево локаций (все уровни "children").
    Возвращает dict вида:
    {
      "id": ...,
      "name": ...,
      "type": ...,
      "image_url": ...,
      "recommended_level": ...,
      "quick_travel_marker": ...,
      "description": ...,
      "parent_id": ...,
      "children": [ ... ]
    }
    """
    children_db = session.query(Location).filter(Location.parent_id == location.id).all()
    children_list = [get_location_tree(session, child) for child in children_db]

    return {
        "id": location.id,
        "name": location.name,
        "type": location.type,
        "image_url": location.image_url,
        "recommended_level": location.recommended_level,
        "quick_travel_marker": location.quick_travel_marker,
        "description": location.description,
        "parent_id": location.parent_id,
        "children": children_list
    }

# -------------------------------
#   LOOKUP
# -------------------------------
def get_locations_lookup(session: Session) -> List[dict]:
    db_locs = session.query(Location).all()
    return [{"id": loc.id, "name": loc.name} for loc in db_locs]

def get_districts_lookup(session: Session) -> List[dict]:
    db_districts = session.query(District).all()
    return [{"id": d.id, "name": d.name} for d in db_districts]


# -------------------------------
#   COUNTRY
# -------------------------------
def create_new_country(session: Session, name: str, description: str,
                       leader_id: Optional[int], map_image_url: Optional[str]) -> Country:
    new_country = Country(
        name=name,
        description=description,
        leader_id=leader_id,
        map_image_url=map_image_url
    )
    session.add(new_country)
    session.commit()
    session.refresh(new_country)
    return new_country

def update_country(session: Session, country_id: int, data) -> Country:
    db_country = session.query(Country).filter(Country.id == country_id).first()
    if not db_country:
        raise HTTPException(status_code=404, detail="Country not found")

    if getattr(data, "name", None) is not None:
        db_country.name = data.name
    if getattr(data, "description", None) is not None:
        db_country.description = data.description
    if getattr(data, "leader_id", None) is not None:
        db_country.leader_id = data.leader_id
    if getattr(data, "map_image_url", None) is not None:
        db_country.map_image_url = data.map_image_url

    session.commit()
    session.refresh(db_country)
    return db_country


def get_country_details(session: Session, country_id: int) -> Optional[dict]:
    """
    Возвращает полную инфу о стране + для каждого региона:
      (id, name, image_url, x, y, entrance_location_id, entrance_location_name).
    """
    db_country = session.query(Country).filter(Country.id == country_id).first()
    if not db_country:
        return None

    result = {
        "id": db_country.id,
        "name": db_country.name,
        "description": db_country.description,
        "leader_id": db_country.leader_id,
        "map_image_url": db_country.map_image_url,
        "regions": []
    }

    for reg in db_country.regions:
        # Получаем входную локацию (если есть)
        entrance_loc_name = None
        if reg.entrance_location_id:
            entrance_loc = session.query(Location).get(reg.entrance_location_id)
            if entrance_loc:
                entrance_loc_name = entrance_loc.name

        result["regions"].append({
            "id": reg.id,
            "name": reg.name,
            "image_url": reg.image_url,
            "x": reg.x,
            "y": reg.y,
            "entrance_location_id": reg.entrance_location_id,
            "entrance_location_name": entrance_loc_name  # <-- добавленное поле
        })

    return result



def get_countries_lookup(session: Session) -> List[dict]:
    """
    Возвращает список {id, name} для всех стран.
    """
    db_countries = session.query(Country).all()
    return [{"id": c.id, "name": c.name} for c in db_countries]


# -------------------------------
#   REGION
# -------------------------------
def create_new_region(session: Session, data) -> Region:
    new_region = Region(
        country_id=data.country_id,
        name=data.name,
        description=data.description,
        image_url=data.image_url,
        entrance_location_id=data.entrance_location_id,
        leader_id=data.leader_id,
        x=data.x,
        y=data.y
    )
    session.add(new_region)
    session.commit()
    session.refresh(new_region)
    return new_region

def update_region(session: Session, region_id: int, data) -> Region:
    db_region = session.query(Region).filter(Region.id == region_id).first()
    if not db_region:
        raise HTTPException(status_code=404, detail="Region not found")

    if data.country_id is not None:
        db_region.country_id = data.country_id
    if data.name is not None:
        db_region.name = data.name
    if data.description is not None:
        db_region.description = data.description
    if data.image_url is not None:
        db_region.image_url = data.image_url
    if data.entrance_location_id is not None:
        db_region.entrance_location_id = data.entrance_location_id
    if data.leader_id is not None:
        db_region.leader_id = data.leader_id
    if data.x is not None:
        db_region.x = data.x
    if data.y is not None:
        db_region.y = data.y

    session.commit()
    session.refresh(db_region)
    return db_region


def get_region_full_details(session: Session, region_id: int) -> Optional[dict]:
    """
    Возвращает полную информацию о регионе + районы.
    Для района: все поля.
    Если есть entry_location, добавляем его id и name.
    Для локаций – рекурсивное дерево.
    """
    db_region = session.query(Region).filter(Region.id == region_id).first()
    if not db_region:
        return None

    # Основные поля региона
    region_data = {
        "id": db_region.id,
        "country_id": db_region.country_id,
        "name": db_region.name,
        "description": db_region.description,
        "image_url": db_region.image_url,
        "entrance_location_id": db_region.entrance_location_id,
        "leader_id": db_region.leader_id,
        "x": db_region.x,
        "y": db_region.y,
        "districts": []
    }

    # Собираем районы
    for dist in db_region.districts:
        # Добавим entry_location (id+name), если оно есть
        entry_loc_data = None
        if dist.entry_location_detail:
            entry_loc_data = {
                "id": dist.entry_location_detail.id,
                "name": dist.entry_location_detail.name
            }

        # Собираем локации рекурсивно
        district_locations = []
        for loc in dist.locations:
            # Только те локации, у которых parent_id = None (верхний уровень)
            if loc.parent_id is None:
                loc_tree = get_location_tree(session, loc)
                district_locations.append(loc_tree)

        dist_dict = {
            "id": dist.id,
            "name": dist.name,
            "description": dist.description,
            "image_url": dist.image_url,
            "recommended_level": dist.recommended_level,
            "entry_location": entry_loc_data,  # dict или None
            "x": dist.x,
            "y": dist.y,
            "locations": district_locations
        }
        region_data["districts"].append(dist_dict)

    return region_data


# -------------------------------
#   DISTRICT
# -------------------------------
def create_district(session: Session, district_data: DistrictCreate) -> District:
    new_district = District(**district_data.dict())
    session.add(new_district)
    session.commit()
    session.refresh(new_district)
    return new_district

def update_district(session: Session, district_id: int, data) -> District:
    db_district = session.query(District).filter(District.id == district_id).first()
    if not db_district:
        raise HTTPException(status_code=404, detail="District not found")

    if getattr(data, "name", None) is not None:
        db_district.name = data.name
    if getattr(data, "description", None) is not None:
        db_district.description = data.description
    if getattr(data, "image_url", None) is not None:
        db_district.image_url = data.image_url
    if getattr(data, "recommended_level", None) is not None:
        db_district.recommended_level = data.recommended_level
    if getattr(data, "entry_location", None) is not None:
        db_district.entry_location = data.entry_location
    if getattr(data, "x", None) is not None:
        db_district.x = data.x
    if getattr(data, "y", None) is not None:
        db_district.y = data.y

    session.commit()
    session.refresh(db_district)
    return db_district


# -------------------------------
#   LOCATION
# -------------------------------
def create_location(session: Session, location_data: LocationCreate) -> Location:
    new_location = Location(**location_data.dict())
    session.add(new_location)
    session.commit()
    session.refresh(new_location)
    return new_location

def update_location(session: Session, location_id: int, data) -> Location:
    db_location = session.query(Location).filter(Location.id == location_id).first()
    if not db_location:
        raise HTTPException(status_code=404, detail="Location not found")

    if getattr(data, "name", None) is not None:
        db_location.name = data.name
    if getattr(data, "district_id", None) is not None:
        db_location.district_id = data.district_id
    if getattr(data, "type", None) is not None:
        db_location.type = data.type
    if getattr(data, "image_url", None) is not None:
        db_location.image_url = data.image_url
    if getattr(data, "recommended_level", None) is not None:
        db_location.recommended_level = data.recommended_level
    if getattr(data, "quick_travel_marker", None) is not None:
        db_location.quick_travel_marker = data.quick_travel_marker
    if getattr(data, "description", None) is not None:
        db_location.description = data.description
    if getattr(data, "parent_id", None) is not None:
        db_location.parent_id = data.parent_id

    session.commit()
    session.refresh(db_location)
    return db_location

def get_location_by_id(session: Session, location_id: int) -> Optional[Location]:
    return session.query(Location).filter(Location.id == location_id).first()


# -------------------------------
#   NEIGHBORS
# -------------------------------
def add_neighbor(session: Session, location_id: int, neighbor_id: int, energy_cost: int) -> dict:
    forward = LocationNeighbor(
        location_id=location_id,
        neighbor_id=neighbor_id,
        energy_cost=energy_cost
    )
    session.add(forward)

    reverse = LocationNeighbor(
        location_id=neighbor_id,
        neighbor_id=location_id,
        energy_cost=energy_cost
    )
    session.add(reverse)
    session.commit()

    return {
        "forward": {
            "location_id": forward.location_id,
            "neighbor_id": forward.neighbor_id,
            "energy_cost": forward.energy_cost,
        },
        "reverse": {
            "location_id": reverse.location_id,
            "neighbor_id": reverse.neighbor_id,
            "energy_cost": reverse.energy_cost,
        },
    }


def get_location_details(session: Session, location_id: int) -> Optional[dict]:
    loc = session.query(Location).filter(Location.id == location_id).first()
    if not loc:
        return None

    neighbors = session.query(LocationNeighbor).filter(LocationNeighbor.location_id == location_id).all()
    children = session.query(Location).filter(Location.parent_id == location_id).all()

    return {
        "location_id": loc.id,
        "name": loc.name,
        "type": loc.type,
        "description": loc.description,
        "image_url": loc.image_url,
        "recommended_level": loc.recommended_level,
        "quick_travel_marker": loc.quick_travel_marker,
        "district_id": loc.district_id,
        "neighbors": [
            {"neighbor_id": n.neighbor_id, "energy_cost": n.energy_cost}
            for n in neighbors
        ],
        "children": [
            {
                "id": c.id,
                "name": c.name,
                "type": c.type,
                "image_url": c.image_url
            }
            for c in children
        ]
    }


# -------------------------------
#   POSTS
# -------------------------------
def create_post(session: Session, post_data: PostCreate) -> Post:
    new_post = Post(
        character_id=post_data.character_id,
        location_id=post_data.location_id,
        content=post_data.content
    )
    session.add(new_post)
    session.commit()
    session.refresh(new_post)
    return new_post

def get_posts_by_location(session: Session, location_id: int) -> list:
    return session.query(Post).filter(Post.location_id == location_id).all()


