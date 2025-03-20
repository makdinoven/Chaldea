from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
from sqlalchemy.orm import selectinload

from models import (
    Country, Region, District, Location, LocationNeighbor, Post
)
from schemas import (
    DistrictCreate, LocationCreate, PostCreate
)

# -------------------------------
#   Рекурсивный сбор вложенных локаций
# -------------------------------
async def get_location_tree(session: AsyncSession, location: Location) -> dict:
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
    result = await session.execute(select(Location).where(Location.parent_id == location.id))
    children_db = result.scalars().all()
    children_list = [await get_location_tree(session, child) for child in children_db]

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
async def get_locations_lookup(session: AsyncSession) -> List[dict]:
    result = await session.execute(select(Location))
    db_locs = result.scalars().all()
    return [{"id": loc.id, "name": loc.name} for loc in db_locs]

async def get_districts_lookup(session: AsyncSession) -> List[dict]:
    result = await session.execute(select(District))
    db_districts = result.scalars().all()
    return [{"id": d.id, "name": d.name} for d in db_districts]


# -------------------------------
#   COUNTRY
# -------------------------------
async def create_new_country(session: AsyncSession, name: str, description: str,
                       leader_id: Optional[int], map_image_url: Optional[str]) -> Country:
    new_country = Country(
        name=name,
        description=description,
        leader_id=leader_id,
        map_image_url=map_image_url
    )
    session.add(new_country)
    await session.commit()
    await session.refresh(new_country)
    return new_country

async def update_country(session: AsyncSession, country_id: int, data) -> Country:
    result = await session.execute(select(Country).where(Country.id == country_id))
    db_country = result.scalars().first()
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

    await session.commit()
    await session.refresh(db_country)
    return db_country


async def get_country_details(session: AsyncSession, country_id: int) -> Optional[dict]:
    """Возвращает детали страны с регионами"""
    result = await session.execute(
        select(Country)
        .options(selectinload(Country.regions))
        .where(Country.id == country_id)
    )
    country = result.scalars().first()
    if not country:
        return None

    return {
        "id": country.id,
        "name": country.name,
        "description": country.description,
        "leader_id": country.leader_id,
        "map_image_url": country.map_image_url,
        "regions": [
            {
                "id": reg.id,
                "name": reg.name,
                "image_url": reg.image_url,
                "x": reg.x,
                "y": reg.y,
                "entrance_location_id": reg.entrance_location_id,
                "entrance_location_name": None  # Будет заполнено при необходимости
            } for reg in country.regions
        ]
    }


async def get_countries_lookup(session: AsyncSession) -> List[dict]:
    """
    Возвращает список {id, name} для всех стран.
    """
    result = await session.execute(select(Country))
    db_countries = result.scalars().all()
    return [{"id": c.id, "name": c.name} for c in db_countries]


# -------------------------------
#   REGION
# -------------------------------
async def create_new_region(session: AsyncSession, data) -> Region:
    new_region = Region(
        country_id=data.country_id,
        name=data.name,
        description=data.description,
        image_url=data.image_url,
        map_image_url=data.map_image_url,
        entrance_location_id=data.entrance_location_id,
        leader_id=data.leader_id,
        x=data.x,
        y=data.y
    )
    session.add(new_region)
    await session.commit()
    await session.refresh(new_region)
    return new_region

async def update_region(session: AsyncSession, region_id: int, data) -> Region:
    result = await session.execute(
        select(Region).where(Region.id == region_id)
    )
    db_region = result.scalars().first()
    if not db_region:
        raise HTTPException(status_code=404, detail="Регион не найден")
    # Обновляем только те поля, которые пришли в запросе
    for field, value in data.dict(exclude_unset=True).items():
        setattr(db_region, field, value)

    try:
        await session.commit()
        await session.refresh(db_region)
        return db_region
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))


async def get_region_full_details(session: AsyncSession, region_id: int) -> Optional[dict]:
    """Возвращает детали региона с районами и локациями"""
    result = await session.execute(
        select(Region)
        .options(
            selectinload(Region.districts)
            .selectinload(District.locations)
        )
        .where(Region.id == region_id)
    )
    region = result.scalars().first()
    if not region:
        return None

    # Получаем входную локацию региона, если есть
    entrance_location = None
    if region.entrance_location_id:
        entrance_result = await session.execute(
            select(Location).where(Location.id == region.entrance_location_id)
        )
        entrance_location = entrance_result.scalars().first()

    # Получаем все локации для каждого района
    districts_data = []
    for district in region.districts:
        # Получаем корневые локации района (без parent_id)
        root_locations_result = await session.execute(
            select(Location).where(
                Location.district_id == district.id,
                Location.parent_id.is_(None)
            )
        )
        root_locations = root_locations_result.scalars().all()
        
        # Строим дерево для каждой корневой локации
        locations_tree = []
        for location in root_locations:
            location_tree = await get_location_tree(session, location)
            locations_tree.append(location_tree)

        districts_data.append({
            "id": district.id,
            "name": district.name,
            "description": district.description,
            "entrance_location_id": district.entrance_location_id,
            "x": district.x,
            "y": district.y,
            "image_url": district.image_url,
            "locations": locations_tree
        })

    return {
        "id": region.id,
        "country_id": region.country_id,
        "name": region.name,
        "description": region.description,
        "image_url": region.image_url,
        "map_image_url": region.map_image_url,
        "entrance_location_id": region.entrance_location_id,
        "entrance_location_name": entrance_location.name if entrance_location else None,
        "leader_id": region.leader_id,
        "x": region.x,
        "y": region.y,
        "districts": districts_data
    }


# -------------------------------
#   DISTRICT
# -------------------------------
async def create_district(session: AsyncSession, district_data: DistrictCreate) -> District:
    new_district = District(**district_data.dict())
    session.add(new_district)
    await session.commit()
    await session.refresh(new_district)
    return new_district

async def update_district(session: AsyncSession, district_id: int, data) -> District:
    result = await session.execute(select(District).where(District.id == district_id))
    db_district = result.scalars().first()
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

    await session.commit()
    await session.refresh(db_district)
    return db_district


# -------------------------------
#   LOCATION
# -------------------------------
async def create_location(session: AsyncSession, location_data: LocationCreate) -> Location:
    new_location = Location(**location_data.dict())
    session.add(new_location)
    await session.commit()
    await session.refresh(new_location)
    return new_location

async def update_location(session: AsyncSession, location_id: int, data) -> Location:
    result = await session.execute(select(Location).where(Location.id == location_id))
    db_location = result.scalars().first()
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

    await session.commit()
    await session.refresh(db_location)
    return db_location

async def get_location_by_id(session: AsyncSession, location_id: int) -> Optional[Location]:
    result = await session.execute(select(Location).where(Location.id == location_id))
    return result.scalars().first()


# -------------------------------
#   NEIGHBORS
# -------------------------------
async def add_neighbor(session: AsyncSession, location_id: int, neighbor_id: int, energy_cost: int) -> dict:
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
    await session.commit()

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


async def get_location_details(session: AsyncSession, location_id: int) -> Optional[dict]:
    result = await session.execute(select(Location).where(Location.id == location_id))
    loc = result.scalars().first()
    if not loc:
        return None

    neighbors_result = await session.execute(
        select(LocationNeighbor).where(LocationNeighbor.location_id == location_id)
    )
    neighbors = neighbors_result.scalars().all()

    children_result = await session.execute(
        select(Location).where(Location.parent_id == location_id)
    )
    children = children_result.scalars().all()

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
async def create_post(session: AsyncSession, post_data: PostCreate) -> Post:
    new_post = Post(
        character_id=post_data.character_id,
        location_id=post_data.location_id,
        content=post_data.content
    )
    session.add(new_post)
    await session.commit()
    await session.refresh(new_post)
    return new_post

async def get_posts_by_location(session: AsyncSession, location_id: int) -> list:
    result = await session.execute(select(Post).where(Post.location_id == location_id))
    return result.scalars().all()

async def get_admin_panel_data(session: AsyncSession) -> dict:
    """
    Получает все данные для админ панели одним запросом
    """
    # Получаем все страны
    countries_result = await session.execute(select(Country))
    countries = countries_result.scalars().all()
    
    # Получаем все регионы с их районами
    regions_result = await session.execute(
        select(Region).options(
            selectinload(Region.districts)
        )
    )
    regions = regions_result.scalars().all()

    # Подготавливаем список регионов
    regions_data = []
    for region in regions:
        districts_data = []
        for district in region.districts:
            # Получаем локации для района
            locations_result = await session.execute(
                select(Location).where(Location.district_id == district.id)
            )
            locations = locations_result.scalars().all()
            
            districts_data.append({
                "id": district.id,
                "name": district.name,
                "region_id": district.region_id,
                "description": district.description,
                "entrance_location_id": district.entrance_location_id,
                "x": district.x,
                "y": district.y,
                "image_url": district.image_url,
                "locations": [
                    {
                        "id": loc.id,
                        "name": loc.name,
                        "type": loc.type,
                        "description": loc.description
                    } for loc in locations
                ]
            })
        
        regions_data.append({
            "id": region.id,
            "name": region.name,
            "description": region.description,
            "country_id": region.country_id,
            "entrance_location_id": region.entrance_location_id,
            "leader_id": region.leader_id,
            "x": region.x,
            "y": region.y,
            "map_image_url": region.map_image_url,
            "image_url": region.image_url,
            "districts": districts_data
        })

    return {
        "countries": [
            {
                "id": country.id,
                "name": country.name,
                "description": country.description,
                "leader_id": country.leader_id,
                "map_image_url": country.map_image_url
            } for country in countries
        ],
        "regions": regions_data
    }

async def get_countries_list(session: AsyncSession) -> List[dict]:
    """Получает базовый список стран"""
    result = await session.execute(select(Country))
    countries = result.scalars().all()
    return [
        {
            "id": country.id,
            "name": country.name,
            "description": country.description,
            "map_image_url": country.map_image_url
        } for country in countries
    ]


