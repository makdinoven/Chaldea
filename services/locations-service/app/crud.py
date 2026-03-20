import logging
import httpx
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
from sqlalchemy.orm import selectinload
from sqlalchemy import text, delete
from config import settings
import models
from models import (
    Country, Region, District, Location, LocationNeighbor, Post, GameRule,
    Area, ClickableZone, GameTimeConfig
)
from schemas import (
    DistrictCreate, LocationCreate, PostCreate, LocationNeighborCreate,
    GameRuleCreate, GameRuleUpdate, GameRuleReorderItem,
    AreaCreate, AreaUpdate, ClickableZoneCreate, ClickableZoneUpdate
)

# -------------------------------
#   Рекурсивный сбор вложенных локаций
# -------------------------------
async def get_location_tree(session: AsyncSession, location: Location) -> dict:
    """
    Рекурсивно собирает дерево локаций (все уровни "children").
    """
    try:
        # Получаем все дочерние локации за один запрос
        stmt = select(Location).where(Location.parent_id == location.id)
        result = await session.execute(stmt)
        children_db = result.scalars().all()
        
        # Создаем список для хранения дочерних локаций
        children_list = []
        
        # Обрабатываем каждую дочернюю локацию
        for child in children_db:
            # Рекурсивно получаем дерево для дочерней локации
            child_tree = await get_location_tree(session, child)
            children_list.append(child_tree)

        # Возвращаем информацию о текущей локации и ее дочерних элементах
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
    except Exception as e:
        print(f"Ошибка при получении дерева локаций: {e}")
        return {
            "id": location.id,
            "name": location.name,
            "type": location.type,
            "image_url": location.image_url,
            "recommended_level": location.recommended_level,
            "quick_travel_marker": location.quick_travel_marker,
            "description": location.description,
            "parent_id": location.parent_id,
            "children": []
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
                       leader_id: Optional[int], map_image_url: Optional[str],
                       area_id: Optional[int] = None,
                       x: Optional[float] = None,
                       y: Optional[float] = None,
                       emblem_url: Optional[str] = None) -> Country:
    new_country = Country(
        name=name,
        description=description,
        leader_id=leader_id,
        map_image_url=map_image_url,
        emblem_url=emblem_url,
        area_id=area_id,
        x=x,
        y=y,
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

    for field, value in data.dict(exclude_unset=True).items():
        setattr(db_country, field, value)

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
        "emblem_url": country.emblem_url,
        "regions": [
            {
                "id": reg.id,
                "country_id":country.id,
                "name": reg.name,
                "image_url": reg.image_url,
                "x": reg.x,
                "y": reg.y,
                "description":reg.description
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
        )
        .where(Region.id == region_id)
    )
    region = result.scalars().first()
    if not region:
        return None

    # Получаем все локации для региона одним запросом (district-based + standalone)
    district_ids = [d.id for d in region.districts]
    from sqlalchemy import or_
    location_filter = []
    if district_ids:
        location_filter.append(Location.district_id.in_(district_ids))
    location_filter.append(
        (Location.region_id == region_id) & (Location.district_id.is_(None))
    )
    locations_result = await session.execute(
        select(Location).where(or_(*location_filter))
    )
    all_locations = locations_result.scalars().all()

    # Создаем словарь для быстрого доступа к локациям
    locations_by_id = {loc.id: {
        "id": loc.id,
        "name": loc.name,
        "type": loc.type,
        "image_url": loc.image_url,
        "recommended_level": loc.recommended_level,
        "quick_travel_marker": loc.quick_travel_marker,
        "description": loc.description,
        "parent_id": loc.parent_id,
        "marker_type": loc.marker_type,
        "map_icon_url": loc.map_icon_url,
        "map_x": loc.map_x,
        "map_y": loc.map_y,
        "children": []
    } for loc in all_locations}

    # Строим дерево локаций
    root_locations = []
    for loc in all_locations:
        if loc.parent_id is None:
            root_locations.append(locations_by_id[loc.id])
        else:
            parent = locations_by_id.get(loc.parent_id)
            if parent:
                parent["children"].append(locations_by_id[loc.id])

    # Получаем данные для entrance_location, если он задан
    entrance_location = None
    if region.entrance_location_id is not None:
        entrance_location = locations_by_id.get(region.entrance_location_id)
        # Если нужно вернуть только id и name, можно использовать:
        # entrance_location = {"id": entrance_location["id"], "name": entrance_location["name"]} if entrance_location else None

    # Формируем данные по районам
    districts_data = []
    for district in region.districts:
        district_root_locations = [
            loc for loc in root_locations
            if loc["id"] in [l.id for l in all_locations if l.district_id == district.id]
        ]
        entrance_location = None
        if district.entrance_location_id:
            entrance_location = locations_by_id.get(district.entrance_location_id)

        districts_data.append({
            "id": district.id,
            "name": district.name,
            "description": district.description,
            "entrance_location": entrance_location,
            "x": district.x,
            "y": district.y,
            "image_url": district.image_url,
            "map_icon_url": district.map_icon_url,
            "locations": district_root_locations
        })

    # Build unified map_items list combining locations and districts
    map_items = []
    for loc in all_locations:
        if loc.map_x is not None and loc.map_y is not None:
            map_items.append({
                "id": loc.id,
                "name": loc.name,
                "type": "location",
                "map_icon_url": loc.map_icon_url,
                "map_x": loc.map_x,
                "map_y": loc.map_y,
                "marker_type": loc.marker_type,
                "image_url": loc.image_url,
            })
    for district in region.districts:
        if district.x is not None and district.y is not None:
            map_items.append({
                "id": district.id,
                "name": district.name,
                "type": "district",
                "map_icon_url": district.map_icon_url,
                "map_x": district.x,
                "map_y": district.y,
                "marker_type": None,
                "image_url": district.image_url,
            })

    # Получаем neighbor_edges для всех локаций региона
    all_location_ids = [loc.id for loc in all_locations]
    neighbor_edges = []
    if all_location_ids:
        neighbors_result = await session.execute(
            select(LocationNeighbor).where(
                LocationNeighbor.location_id.in_(all_location_ids),
                LocationNeighbor.neighbor_id.in_(all_location_ids)
            )
        )
        all_neighbors = neighbors_result.scalars().all()
        seen_edges = set()
        for n in all_neighbors:
            edge = (min(n.location_id, n.neighbor_id), max(n.location_id, n.neighbor_id))
            if edge not in seen_edges:
                seen_edges.add(edge)
                neighbor_edges.append({"from_id": edge[0], "to_id": edge[1]})

    return {
        "id": region.id,
        "country_id": region.country_id,
        "name": region.name,
        "description": region.description,
        "image_url": region.image_url,
        "map_image_url": region.map_image_url,
        # Возвращаем объект локации вместо простого id
        "entrance_location": entrance_location,
        "leader_id": region.leader_id,
        "x": region.x,
        "y": region.y,
        "districts": districts_data,
        "map_items": map_items,
        "neighbor_edges": neighbor_edges,
    }


# -------------------------------
#   DISTRICT
# -------------------------------
async def create_district(session: AsyncSession, district: DistrictCreate) -> District:
    """Создает новый район"""
    db_district = District(
        name=district.name,
        description=district.description,
        region_id=district.region_id,
        entrance_location_id=district.entrance_location_id,
        recommended_level=district.recommended_level,
        x=district.x,
        y=district.y,
        image_url=district.image_url or "",  # Используем пустую строку вместо None
        map_icon_url=district.map_icon_url,
    )
    
    session.add(db_district)
    await session.commit()
    await session.refresh(db_district)
    
    # Получаем район со всеми связанными данными
    stmt = select(District).where(District.id == db_district.id).options(
        selectinload(District.locations)
    )
    result = await session.execute(stmt)
    district_with_relations = result.scalar_one_or_none()
    
    return district_with_relations

async def update_district(session: AsyncSession, district_id: int, data) -> District:
    result = await session.execute(
        select(District)
        .options(
            selectinload(District.entrance_location_detail),
            selectinload(District.locations)  # добавляем eager‑loading для locations
        )
        .where(District.id == district_id)
    )
    db_district = result.scalars().first()
    if not db_district:
        raise HTTPException(status_code=404, detail="District not found")
    
    # Обновление полей
    if getattr(data, "name", None) is not None:
        db_district.name = data.name
    if getattr(data, "description", None) is not None:
        db_district.description = data.description
    if getattr(data, "image_url", None) is not None:
        db_district.image_url = data.image_url
    if getattr(data, "recommended_level", None) is not None:
        db_district.recommended_level = data.recommended_level
    if getattr(data, "entrance_location_id", None) is not None:
        db_district.entrance_location_id = data.entrance_location_id
    if getattr(data, "x", None) is not None:
        db_district.x = data.x
    if getattr(data, "y", None) is not None:
        db_district.y = data.y
    if getattr(data, "map_icon_url", None) is not None:
        db_district.map_icon_url = data.map_icon_url

    await session.commit()
    await session.refresh(db_district)
    return db_district

# -------------------------------
#   LOCATION
# -------------------------------
async def create_location(session: AsyncSession, location_data: LocationCreate) -> Location:
    try:
        print("=== Начало создания локации ===")
        print(f"Входные данные: {location_data}")

        # Validate: must have either district_id or region_id
        if not location_data.district_id and not location_data.region_id:
            raise HTTPException(
                status_code=400,
                detail="Необходимо указать district_id или region_id"
            )

        # Создаем словарь с данными локации
        location_dict = location_data.dict()
        print(f"Преобразованные данные: {location_dict}")

        # Устанавливаем значения по умолчанию
        location_dict['type'] = 'location'
        location_dict['image_url'] = location_dict.get('image_url', '')
        location_dict['description'] = location_dict.get('description', '')
        location_dict['recommended_level'] = location_dict.get('recommended_level', 1)
        location_dict['quick_travel_marker'] = location_dict.get('quick_travel_marker', False)
        print(f"Данные после установки значений по умолчанию: {location_dict}")

        # Создаем новую локацию
        print("Создание объекта Location...")
        new_location = Location(**location_dict)
        print(f"Объект Location создан: {new_location.__dict__}")
        
        print("Добавление в сессию...")
        session.add(new_location)
        
        print("Выполнение commit...")
        await session.commit()
        
        print("Обновление объекта...")
        await session.refresh(new_location)
        print(f"Локация создана с ID: {new_location.id}")

        # Если есть parent_id, обновляем тип родительской локации
        if new_location.parent_id:
            print(f"Обновление типа родительской локации (ID: {new_location.parent_id})")
            parent = await get_location_by_id(session, new_location.parent_id)
            if parent:
                print("Родительская локация найдена, обновляем тип на subdistrict")
                parent.type = 'subdistrict'
                await session.commit()
                await session.refresh(parent)
                print("Тип родительской локации обновлен")

        print("=== Создание локации завершено успешно ===")
        return new_location
    except Exception as e:
        print(f"=== ОШИБКА при создании локации ===")
        print(f"Тип ошибки: {type(e)}")
        print(f"Текст ошибки: {str(e)}")
        print(f"Traceback:")
        import traceback
        traceback.print_exc()
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))

async def update_location(session: AsyncSession, location_id: int, location_data) -> Location:
    """Обновляет локацию"""
    try:
        # Получаем локацию
        result = await session.execute(select(Location).where(Location.id == location_id))
        location = result.scalars().first()
        if not location:
            raise HTTPException(status_code=404, detail="Location not found")
        
        # Обновляем только те поля, которые пришли в запросе
        update_data = location_data.dict(exclude_unset=True)
        
        # Устанавливаем значения по умолчанию для обязательных полей
        if 'image_url' in update_data and update_data['image_url'] is None:
            update_data['image_url'] = ""
        if 'description' in update_data and update_data['description'] is None:
            update_data['description'] = ""
            
        for field, value in update_data.items():
            setattr(location, field, value)
        
        await session.commit()
        await session.refresh(location)
        return location
    except Exception as e:
        await session.rollback()
        print(f"Ошибка при обновлении локации: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def get_location_by_id(session: AsyncSession, location_id: int) -> Optional[Location]:
    result = await session.execute(select(Location).where(Location.id == location_id))
    return result.scalars().first()


# -------------------------------
#   NEIGHBORS
# -------------------------------
async def add_neighbor(session: AsyncSession, location_id: int, neighbor_id: int, energy_cost: int) -> dict:
    """Добавляет соседа к локации"""
    # Проверяем, существует ли уже такая связь
    forward_result = await session.execute(
        select(LocationNeighbor).where(
            LocationNeighbor.location_id == location_id,
            LocationNeighbor.neighbor_id == neighbor_id
        )
    )
    existing_forward = forward_result.scalars().first()
    
    if existing_forward:
        # Если связь уже существует, обновляем energy_cost
        existing_forward.energy_cost = energy_cost
    else:
        # Иначе создаем новую связь
        forward = LocationNeighbor(
            location_id=location_id,
            neighbor_id=neighbor_id,
            energy_cost=energy_cost
        )
        session.add(forward)

    # То же самое для обратной связи
    reverse_result = await session.execute(
        select(LocationNeighbor).where(
            LocationNeighbor.location_id == neighbor_id,
            LocationNeighbor.neighbor_id == location_id
        )
    )
    existing_reverse = reverse_result.scalars().first()
    
    if existing_reverse:
        existing_reverse.energy_cost = energy_cost
    else:
        reverse = LocationNeighbor(
            location_id=neighbor_id,
            neighbor_id=location_id,
            energy_cost=energy_cost
        )
        session.add(reverse)
    
    # Сохраняем изменения
    await session.commit()
    
    # Возвращаем информацию о созданной связи
    return {
        "location_id": location_id,
        "neighbor_id": neighbor_id,
        "energy_cost": energy_cost
    }


async def get_location_details(session: AsyncSession, location_id: int) -> Optional[dict]:
    result = await session.execute(select(Location).where(Location.id == location_id))
    loc = result.scalars().first()
    if not loc:
        return None

    # Получаем соседей
    neighbors_result = await session.execute(
        select(LocationNeighbor).where(LocationNeighbor.location_id == location_id)
    )
    neighbors = neighbors_result.scalars().all()

    # Получаем дочерние локации
    children_result = await session.execute(
        select(Location).where(Location.parent_id == location_id)
    )
    children = children_result.scalars().all()

    # Формируем и возвращаем результат
    return {
        "id": loc.id,
        "name": loc.name,
        "type": loc.type,
        "parent_id": loc.parent_id,
        "description": loc.description,
        "image_url": loc.image_url,
        "recommended_level": loc.recommended_level,
        "quick_travel_marker": loc.quick_travel_marker,
        "district_id": loc.district_id,
        "region_id": loc.region_id,
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
    result = await session.execute(select(Post).where(Post.location_id == location_id).order_by(Post.id.desc()))
    return result.scalars().all()

async def get_admin_panel_data(session: AsyncSession) -> dict:
    """
    Получает все данные для админ панели одним запросом
    """
    # Получаем все области
    areas_result = await session.execute(
        select(Area).order_by(Area.sort_order.asc(), Area.id.asc())
    )
    areas = areas_result.scalars().all()

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
                "map_icon_url": district.map_icon_url,
                "locations": [
                    {
                        "id": loc.id,
                        "name": loc.name,
                        "type": loc.type,
                        "description": loc.description,
                        "marker_type": loc.marker_type,
                        "image_url": loc.image_url,
                        "map_icon_url": loc.map_icon_url,
                        "map_x": loc.map_x,
                        "map_y": loc.map_y,
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
        "areas": [
            {
                "id": area.id,
                "name": area.name,
                "description": area.description,
                "map_image_url": area.map_image_url,
                "sort_order": area.sort_order,
            } for area in areas
        ],
        "countries": [
            {
                "id": country.id,
                "name": country.name,
                "description": country.description,
                "leader_id": country.leader_id,
                "map_image_url": country.map_image_url,
                "emblem_url": country.emblem_url,
                "area_id": country.area_id,
                "x": country.x,
                "y": country.y,
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
            "map_image_url": country.map_image_url,
            "emblem_url": country.emblem_url,
            "area_id": country.area_id,
            "x": country.x,
            "y": country.y,
        } for country in countries
    ]

async def get_locations_by_district(session: AsyncSession, district_id: int):
    """Получает список всех локаций в районе"""
    query = select(Location).where(Location.district_id == district_id)
    result = await session.execute(query)
    locations = result.scalars().all()
    return [
        {
            "id": loc.id,
            "name": loc.name,
            "type": loc.type,
            "recommended_level": loc.recommended_level
        }
        for loc in locations
    ]

async def get_location_children(db: AsyncSession, location_id: int):
    """
    Получает список дочерних локаций для указанной локации.
    """
    try:
        stmt = select(Location).where(Location.parent_id == location_id)
        result = await db.execute(stmt)
        children = result.scalars().all()
        return children
    except Exception as e:
        print(f"Ошибка при получении дочерних локаций: {e}")
        return []


async def update_location_neighbors(
        db: AsyncSession,
        location_id: int,
        neighbors: List[LocationNeighborCreate]
) -> List[dict]:
    """
    Обновляет (перезаписывает) список соседей для локации location_id.
    Удаляет все существующие связи (X->N, N->X), и создаёт новые пары в обе стороны.
    """
    try:
        # 1) Удаляем любые связи, где X — одна из сторон
        await db.execute(
            delete(LocationNeighbor).where(
                (LocationNeighbor.location_id == location_id)
                | (LocationNeighbor.neighbor_id == location_id)
            )
        )
        await db.commit()

        # 2) Создаём новые связи (в обе стороны)
        new_neighbors = []
        for neighbor in neighbors:
            # Сначала проверяем, что такая локация существует
            neighbor_exists = await db.execute(
                select(Location).where(Location.id == neighbor.neighbor_id)
            )
            if not neighbor_exists.scalars().first():
                # Если локации нет — пропускаем
                continue

            # Прямое направление X->N
            forward = LocationNeighbor(
                location_id=location_id,
                neighbor_id=neighbor.neighbor_id,
                energy_cost=neighbor.energy_cost
            )
            db.add(forward)

            # Обратное направление N->X
            reverse = LocationNeighbor(
                location_id=neighbor.neighbor_id,
                neighbor_id=location_id,
                energy_cost=neighbor.energy_cost
            )
            db.add(reverse)

            # Добавляем в список для возврата клиенту
            new_neighbors.append({
                "neighbor_id": neighbor.neighbor_id,
                "energy_cost": neighbor.energy_cost
            })

        await db.commit()
        return new_neighbors
    except Exception as e:
        await db.rollback()
        print(f"Ошибка при обновлении соседей: {e}")
        # Возвращаем пустой список вместо выброса ошибки,
        # чтобы не ронять сервис (по аналогии с вашим кодом).
        return []

async def get_district_locations(session: AsyncSession, district_id: int):
    """Получает все локации района"""
    stmt = select(Location).where(Location.district_id == district_id)
    result = await session.execute(stmt)
    return result.scalars().all()

async def delete_location_recursively(
    session: AsyncSession,
    location_id: int,
    commit: bool = False
):
    """
    Рекурсивно удаляет локацию вместе с её дочерними локациями
    и всеми записями в LocationNeighbor.
    Если commit=False, то коммит не выполняется внутри этой функции
    (это удобно при массовых удалениях).
    """
    # Сначала получаем саму локацию
    loc = await get_location_by_id(session, location_id)
    if not loc:
        # Локация уже не существует — просто возвращаем
        return

    # 1) Удаляем все связи с соседями (в обе стороны)
    await session.execute(
        delete(LocationNeighbor).where(
            (LocationNeighbor.location_id == location_id) |
            (LocationNeighbor.neighbor_id == location_id)
        )
    )

    # 2) Получаем всех дочерних локаций
    children_result = await session.execute(
        select(Location).where(Location.parent_id == location_id)
    )
    children = children_result.scalars().all()

    # Рекурсивно удаляем каждого потомка
    for child in children:
        await delete_location_recursively(session, child.id, commit=False)

    # 3) Удаляем саму локацию
    await session.execute(
        delete(Location).where(Location.id == location_id)
    )

    if commit:
        await session.commit()


async def delete_district(
    session: AsyncSession,
    district_id: int,
    commit: bool = True
):
    """
    Удаляет район вместе со всеми его локациями.
    Если commit=False, то коммит не выполняется,
    что может быть нужно для транзакций на более высоком уровне (напр. удаление региона).
    """
    # Проверяем существование района
    district_result = await session.execute(
        select(District).where(District.id == district_id)
    )
    district = district_result.scalars().first()
    if not district:
        raise HTTPException(status_code=404, detail="District not found")

    # Получаем все локации этого района
    locations_result = await session.execute(
        select(Location).where(Location.district_id == district_id)
    )
    locations = locations_result.scalars().all()

    # Удаляем все локации (рекурсивно)
    for loc in locations:
        await delete_location_recursively(session, loc.id, commit=False)

    # Удаляем сам район
    await session.execute(
        delete(District).where(District.id == district_id)
    )

    if commit:
        await session.commit()

async def delete_region(session: AsyncSession, region_id: int):
    """
    Удаляет регион вместе со всеми его районами и локациями.
    """
    # Проверяем существование региона
    region_result = await session.execute(
        select(Region).where(Region.id == region_id)
    )
    region = region_result.scalars().first()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")

    # Получаем все районы этого региона
    districts_result = await session.execute(
        select(District).where(District.region_id == region_id)
    )
    districts = districts_result.scalars().all()

    # Для каждого района — удаляем
    for d in districts:
        await delete_district(session, d.id, commit=False)

    # Удаляем сам регион
    await session.execute(
        delete(Region).where(Region.id == region_id)
    )

logger = logging.getLogger("location-service.crud")
async def get_client_location_details(session: AsyncSession, location_id: int) -> Optional[dict]:
    """
    Собирает детальную информацию о локации для клиентской части:
      - Извлекает базовые данные локации (без children)
      - Собирает список соседей из БД
      - Вызывает Character‑service для получения списка персонажей, находящихся в локации
      - Получает посты локации и для каждого поста дополняет данные профиля персонажа через Character‑service
    """
    # 1. Получаем базовые данные локации
    result = await session.execute(select(Location).where(Location.id == location_id))
    loc = result.scalars().first()
    if not loc:
        return None

    # 2. Извлекаем соседей
    neighbors_result = await session.execute(
        select(LocationNeighbor).where(LocationNeighbor.location_id == location_id)
    )
    neighbors = neighbors_result.scalars().all()
    detailed_neighbors = []
    for n in neighbors:
        neighbor_res = await session.execute(select(Location).where(Location.id == n.neighbor_id))
        neighbor_loc = neighbor_res.scalars().first()
        if neighbor_loc:
            detailed_neighbors.append({
                "neighbor_id": neighbor_loc.id,
                "name": neighbor_loc.name,
                "recommended_level": neighbor_loc.recommended_level,
                "image_url": neighbor_loc.image_url,
                "energy_cost": n.energy_cost
            })

    # 3. Получаем список персонажей для локации через новый эндпоинт Character‑service
    players = await get_players_in_location(location_id)

    # 4. Получаем посты для локации
    posts_db = await get_posts_by_location(session, location_id)
    detailed_posts = []
    for post in posts_db:
        detailed_post = await get_post_details(post)
        detailed_posts.append(detailed_post)

    return {
        "id": loc.id,
        "name": loc.name,
        "type": loc.type,
        "parent_id": loc.parent_id,
        "description": loc.description,
        "image_url": loc.image_url,
        "recommended_level": loc.recommended_level,
        "quick_travel_marker": loc.quick_travel_marker,
        "district_id": loc.district_id,
        "region_id": loc.region_id,
        "neighbors": detailed_neighbors,
        "players": players,
        "posts": detailed_posts
    }

async def get_post_details(post: Post) -> dict:
    """
    Дополняет данные поста, получая профиль автора (персонажа) через Character‑service.
    Ожидается, что по эндпоинту:
      GET {settings.CHARACTER_SERVICE_URL}/characters/{character_id}/profile
    возвращается JSON с ключами:
      - character_photo
      - character_title
      - user_id
      - user_nickname
    Если вызов завершится ошибкой, используются пустые значения.
    """
    profile_url = f"{settings.CHARACTER_SERVICE_URL}/characters/{post.character_id}/profile"
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(profile_url)
            resp.raise_for_status()
            profile_data = resp.json()
        except Exception as e:
            logger.error(f"Ошибка при получении профиля персонажа {post.character_id}: {e}")
            profile_data = {
                "character_photo": "",
                "character_title": "",
                "user_id": None,
                "user_nickname": "",
                "character_name": ""
            }
    return {
        "character_id": post.character_id,
        "character_photo": profile_data.get("character_photo", ""),
        "character_title": profile_data.get("character_title", ""),
        "user_id": profile_data.get("user_id"),
        "user_nickname": profile_data.get("user_nickname", ""),
        "character_name": profile_data.get("character_name", ""),
        "content": post.content,
        "length": len(post.content)
    }

async def get_players_in_location(location_id: int) -> List[dict]:
    """
    Получает список персонажей (игроков), находящихся в заданной локации, через Character‑service.
    Используется новый эндпоинт:
      GET {settings.CHARACTER_SERVICE_URL}/characters/by_location?location_id={location_id}
    Ожидается, что сервис вернет список объектов с полями:
      - character_name
      - character_title
      - character_photo
    """
    url = f"{settings.CHARACTER_SERVICE_URL}/characters/by_location?location_id={location_id}"
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            players_data = response.json()
            return players_data
        except Exception as e:
            logger.error(f"Ошибка при получении персонажей для локации {location_id}: {e}")
            return []


# -------------------------------
#   AREA
# -------------------------------
async def create_area(session: AsyncSession, data: AreaCreate) -> Area:
    new_area = Area(
        name=data.name,
        description=data.description,
        sort_order=data.sort_order,
    )
    session.add(new_area)
    await session.commit()
    await session.refresh(new_area)
    return new_area


async def update_area(session: AsyncSession, area_id: int, data: AreaUpdate) -> Area:
    result = await session.execute(select(Area).where(Area.id == area_id))
    db_area = result.scalars().first()
    if not db_area:
        raise HTTPException(status_code=404, detail="Area not found")

    for field, value in data.dict(exclude_unset=True).items():
        setattr(db_area, field, value)

    await session.commit()
    await session.refresh(db_area)
    return db_area


async def get_area_details(session: AsyncSession, area_id: int) -> Optional[dict]:
    """Returns area details with its countries."""
    result = await session.execute(
        select(Area)
        .options(selectinload(Area.countries))
        .where(Area.id == area_id)
    )
    area = result.scalars().first()
    if not area:
        return None

    return {
        "id": area.id,
        "name": area.name,
        "description": area.description,
        "map_image_url": area.map_image_url,
        "sort_order": area.sort_order,
        "countries": [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "leader_id": c.leader_id,
                "map_image_url": c.map_image_url,
                "emblem_url": c.emblem_url,
                "area_id": c.area_id,
                "x": c.x,
                "y": c.y,
            }
            for c in area.countries
        ],
    }


async def get_areas_list(session: AsyncSession) -> List[Area]:
    result = await session.execute(
        select(Area).order_by(Area.sort_order.asc(), Area.id.asc())
    )
    return result.scalars().all()


async def delete_area(session: AsyncSession, area_id: int) -> None:
    result = await session.execute(select(Area).where(Area.id == area_id))
    db_area = result.scalars().first()
    if not db_area:
        raise HTTPException(status_code=404, detail="Area not found")

    await session.execute(delete(Area).where(Area.id == area_id))
    await session.commit()


# -------------------------------
#   CLICKABLE ZONES
# -------------------------------
async def create_clickable_zone(session: AsyncSession, data: ClickableZoneCreate) -> ClickableZone:
    zone_data_dicts = [point.dict() for point in data.zone_data]
    new_zone = ClickableZone(
        parent_type=data.parent_type,
        parent_id=data.parent_id,
        target_type=data.target_type,
        target_id=data.target_id,
        zone_data=zone_data_dicts,
        label=data.label,
        stroke_color=data.stroke_color,
    )
    session.add(new_zone)
    await session.commit()
    await session.refresh(new_zone)
    return new_zone


async def update_clickable_zone(session: AsyncSession, zone_id: int, data: ClickableZoneUpdate) -> ClickableZone:
    result = await session.execute(select(ClickableZone).where(ClickableZone.id == zone_id))
    db_zone = result.scalars().first()
    if not db_zone:
        raise HTTPException(status_code=404, detail="ClickableZone not found")

    update_data = data.dict(exclude_unset=True)
    if "zone_data" in update_data and update_data["zone_data"] is not None:
        update_data["zone_data"] = [point.dict() for point in data.zone_data]

    for field, value in update_data.items():
        setattr(db_zone, field, value)

    await session.commit()
    await session.refresh(db_zone)
    return db_zone


async def delete_clickable_zone(session: AsyncSession, zone_id: int) -> None:
    result = await session.execute(select(ClickableZone).where(ClickableZone.id == zone_id))
    db_zone = result.scalars().first()
    if not db_zone:
        raise HTTPException(status_code=404, detail="ClickableZone not found")

    await session.execute(delete(ClickableZone).where(ClickableZone.id == zone_id))
    await session.commit()


async def get_clickable_zones_by_parent(session: AsyncSession, parent_type: str, parent_id: int) -> List[ClickableZone]:
    result = await session.execute(
        select(ClickableZone).where(
            ClickableZone.parent_type == parent_type,
            ClickableZone.parent_id == parent_id,
        )
    )
    return result.scalars().all()


# -------------------------------
#   HIERARCHY TREE
# -------------------------------
async def get_hierarchy_tree(session: AsyncSession) -> List[dict]:
    """
    Returns the full hierarchy tree: Area -> Country -> Region -> District -> Location.
    Countries without an area_id are included at the root level as type='country' nodes.
    Uses eager loading to avoid N+1 queries.
    """
    # Load all data in bulk to avoid N+1
    areas_result = await session.execute(
        select(Area).order_by(Area.sort_order.asc(), Area.id.asc())
    )
    areas = areas_result.scalars().all()

    countries_result = await session.execute(select(Country))
    countries = countries_result.scalars().all()

    regions_result = await session.execute(select(Region))
    regions = regions_result.scalars().all()

    districts_result = await session.execute(select(District))
    districts = districts_result.scalars().all()

    locations_result = await session.execute(select(Location))
    locations = locations_result.scalars().all()

    # Build location tree (handle parent_id hierarchy)
    locations_by_id = {}
    for loc in locations:
        locations_by_id[loc.id] = {
            "id": loc.id,
            "name": loc.name,
            "type": "location",
            "marker_type": loc.marker_type if loc.marker_type else "safe",
            "children": [],
        }

    # Assign child locations to parents
    root_locations_by_district = {}  # district_id -> list of root locations
    root_locations_by_region = {}    # region_id -> list of standalone root locations
    for loc in locations:
        if loc.parent_id and loc.parent_id in locations_by_id:
            locations_by_id[loc.parent_id]["children"].append(locations_by_id[loc.id])
        elif loc.district_id:
            root_locations_by_district.setdefault(loc.district_id, []).append(
                locations_by_id[loc.id]
            )
        elif loc.region_id:
            root_locations_by_region.setdefault(loc.region_id, []).append(
                locations_by_id[loc.id]
            )

    # Build district nodes
    districts_by_region = {}
    for district in districts:
        district_node = {
            "id": district.id,
            "name": district.name,
            "type": "district",
            "children": root_locations_by_district.get(district.id, []),
        }
        districts_by_region.setdefault(district.region_id, []).append(district_node)

    # Build region nodes (districts + standalone locations)
    regions_by_country = {}
    for region in regions:
        region_children = districts_by_region.get(region.id, []) + root_locations_by_region.get(region.id, [])
        region_node = {
            "id": region.id,
            "name": region.name,
            "type": "region",
            "children": region_children,
        }
        regions_by_country.setdefault(region.country_id, []).append(region_node)

    # Build country nodes
    countries_by_area = {}
    orphan_countries = []  # countries without area_id
    for country in countries:
        country_node = {
            "id": country.id,
            "name": country.name,
            "type": "country",
            "children": regions_by_country.get(country.id, []),
        }
        if country.area_id:
            countries_by_area.setdefault(country.area_id, []).append(country_node)
        else:
            orphan_countries.append(country_node)

    # Build area nodes
    tree = []
    for area in areas:
        area_node = {
            "id": area.id,
            "name": area.name,
            "type": "area",
            "children": countries_by_area.get(area.id, []),
        }
        tree.append(area_node)

    # Add orphan countries at root level
    tree.extend(orphan_countries)

    return tree


# -------------------------------
#   GAME RULES
# -------------------------------
async def get_all_rules(session: AsyncSession) -> List[GameRule]:
    """Возвращает все правила, отсортированные по sort_order ASC, id ASC."""
    result = await session.execute(
        select(GameRule).order_by(GameRule.sort_order.asc(), GameRule.id.asc())
    )
    return result.scalars().all()


async def get_rule_by_id(session: AsyncSession, rule_id: int) -> Optional[GameRule]:
    """Возвращает правило по ID или None."""
    result = await session.execute(
        select(GameRule).where(GameRule.id == rule_id)
    )
    return result.scalars().first()


async def create_rule(session: AsyncSession, data: GameRuleCreate) -> GameRule:
    """Создаёт новое правило."""
    new_rule = GameRule(
        title=data.title,
        content=data.content,
        sort_order=data.sort_order,
    )
    session.add(new_rule)
    await session.commit()
    await session.refresh(new_rule)
    return new_rule


async def update_rule(session: AsyncSession, rule_id: int, data: GameRuleUpdate) -> GameRule:
    """Частично обновляет правило (exclude_unset)."""
    result = await session.execute(
        select(GameRule).where(GameRule.id == rule_id)
    )
    db_rule = result.scalars().first()
    if not db_rule:
        raise HTTPException(status_code=404, detail="Правило не найдено")

    for field, value in data.dict(exclude_unset=True).items():
        setattr(db_rule, field, value)

    await session.commit()
    await session.refresh(db_rule)
    return db_rule


async def delete_rule(session: AsyncSession, rule_id: int) -> None:
    """Удаляет правило по ID."""
    result = await session.execute(
        select(GameRule).where(GameRule.id == rule_id)
    )
    db_rule = result.scalars().first()
    if not db_rule:
        raise HTTPException(status_code=404, detail="Правило не найдено")

    await session.execute(
        delete(GameRule).where(GameRule.id == rule_id)
    )
    await session.commit()


async def reorder_rules(session: AsyncSession, order_items: List[GameRuleReorderItem]) -> None:
    """Массово обновляет sort_order для списка правил."""
    for item in order_items:
        result = await session.execute(
            select(GameRule).where(GameRule.id == item.id)
        )
        db_rule = result.scalars().first()
        if db_rule:
            db_rule.sort_order = item.sort_order
    await session.commit()


# -------------------------------
#   GAME TIME
# -------------------------------
import math
from datetime import datetime

YEAR_SEGMENTS = [
    {"name": "spring",    "type": "season",     "real_days": 39},
    {"name": "beltane",   "type": "transition",  "real_days": 10},
    {"name": "summer",    "type": "season",     "real_days": 39},
    {"name": "lughnasad", "type": "transition",  "real_days": 10},
    {"name": "autumn",    "type": "season",     "real_days": 39},
    {"name": "samhain",   "type": "transition",  "real_days": 10},
    {"name": "winter",    "type": "season",     "real_days": 39},
    {"name": "imbolc",    "type": "transition",  "real_days": 10},
]
DAYS_PER_YEAR = 196
DAYS_PER_WEEK = 3

VALID_SEGMENT_NAMES = [s["name"] for s in YEAR_SEGMENTS]


def compute_game_time(epoch: datetime, offset_days: int, now: datetime) -> dict:
    """
    Pure function: computes the current in-game time based on epoch, offset, and real time.
    Returns dict with year, segment_name, segment_type, week, is_transition.
    """
    elapsed_seconds = (now - epoch).total_seconds()
    elapsed_real_days = math.floor(elapsed_seconds / 86400) + offset_days

    if elapsed_real_days < 0:
        elapsed_real_days = 0

    year = elapsed_real_days // DAYS_PER_YEAR + 1
    day_in_year = elapsed_real_days % DAYS_PER_YEAR

    current_segment = YEAR_SEGMENTS[0]
    day_in_segment = day_in_year
    cumulative = 0
    for segment in YEAR_SEGMENTS:
        if day_in_year < cumulative + segment["real_days"]:
            current_segment = segment
            day_in_segment = day_in_year - cumulative
            break
        cumulative += segment["real_days"]

    if current_segment["type"] == "season":
        week = day_in_segment // DAYS_PER_WEEK + 1
        is_transition = False
    else:
        week = None
        is_transition = True

    return {
        "year": year,
        "segment_name": current_segment["name"],
        "segment_type": current_segment["type"],
        "week": week,
        "is_transition": is_transition,
    }


async def get_game_time_config(session: AsyncSession) -> Optional[GameTimeConfig]:
    """Returns the singleton game time config row, or None if not found."""
    result = await session.execute(select(GameTimeConfig))
    return result.scalars().first()


async def update_game_time_config(
    session: AsyncSession, data: dict
) -> GameTimeConfig:
    """
    Updates the singleton game time config row.
    Creates a default row if none exists.
    data keys: epoch (datetime), offset_days (int)
    """
    result = await session.execute(select(GameTimeConfig))
    config = result.scalars().first()

    if not config:
        config = GameTimeConfig()
        session.add(config)
        await session.flush()

    if "epoch" in data and data["epoch"] is not None:
        config.epoch = data["epoch"]
    if "offset_days" in data and data["offset_days"] is not None:
        config.offset_days = data["offset_days"]

    await session.commit()
    await session.refresh(config)
    return config
