import json
import logging
import re
import math
import httpx
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional, Dict, Tuple
from sqlalchemy.orm import selectinload
from sqlalchemy import text, delete, func as sa_func
from sqlalchemy.exc import IntegrityError
from config import settings

logger = logging.getLogger(__name__)

MIN_POST_LENGTH = 300  # characters after stripping HTML


def strip_html_tags(html: str) -> str:
    """Remove HTML tags, returning plain text."""
    return re.sub(r'<[^>]*>', '', html).strip()


def calculate_post_xp(content: str) -> Tuple[int, int]:
    """
    Calculate XP from post content.
    Returns (char_count, xp_earned).
    char_count is the number of characters after HTML stripping.
    xp_earned = round(char_count / 100) using standard math rounding.
    """
    plain_text = strip_html_tags(content)
    char_count = len(plain_text)
    if char_count < MIN_POST_LENGTH:
        return (char_count, 0)
    # Standard rounding: 340/100=3.4 -> 3, 350/100=3.5 -> 4
    xp = math.floor(char_count / 100 + 0.5)
    return (char_count, xp)


async def award_post_xp_and_log(
    character_id: int,
    post_id: int,
    location_id: int,
    location_name: str,
    char_count: int,
    xp: int,
):
    """Fire-and-forget: award passive XP and create a character log entry."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if xp > 0:
                await client.put(
                    f"{settings.ATTRIBUTES_SERVICE_URL}/attributes/{character_id}/passive_experience",
                    json={"amount": xp},
                )
            description = f"Написал пост в {location_name}, получил {xp} XP"
            await client.post(
                f"{settings.CHARACTER_SERVICE_URL}/characters/{character_id}/logs",
                json={
                    "event_type": "rp_post",
                    "description": description,
                    "metadata": {
                        "post_id": post_id,
                        "location_id": location_id,
                        "xp_earned": xp,
                        "char_count": char_count,
                    },
                },
            )
    except Exception as e:
        logger.error(f"Failed to award XP/log for post {post_id}: {e}")
import models
from models import (
    Country, Region, District, Location, LocationNeighbor, Post, PostLike, GameRule,
    Area, ClickableZone, GameTimeConfig, LocationLoot, LocationFavorite,
    PostDeletionRequest, PostReport, DialogueTree, DialogueNode, DialogueOption,
    NpcShopItem, Quest, QuestObjective, CharacterQuest, CharacterQuestProgress,
    ArchiveCategory, ArchiveArticle, ArchiveArticleCategory,
    RegionTransitionArrow, ArrowNeighbor
)
from schemas import (
    DistrictCreate, LocationCreate, PostCreate, LocationNeighborCreate,
    GameRuleCreate, GameRuleUpdate, GameRuleReorderItem,
    AreaCreate, AreaUpdate, ClickableZoneCreate, ClickableZoneUpdate,
    ArchiveCategoryCreate, ArchiveCategoryUpdate,
    ArchiveArticleCreate, ArchiveArticleUpdate,
    TransitionArrowCreate, TransitionArrowUpdate, ArrowNeighborCreate
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
        "sort_order": loc.sort_order,
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
    for district in sorted(region.districts, key=lambda d: d.sort_order):
        district_root_locations = sorted(
            [
                loc for loc in root_locations
                if loc["id"] in [l.id for l in all_locations if l.district_id == district.id]
            ],
            key=lambda loc: loc["sort_order"],
        )
        entrance_location = None
        if district.entrance_location_id:
            entrance_location = locations_by_id.get(district.entrance_location_id)

        districts_data.append({
            "id": district.id,
            "name": district.name,
            "description": district.description,
            "parent_district_id": district.parent_district_id,
            "entrance_location": entrance_location,
            "recommended_level": district.recommended_level,
            "marker_type": district.marker_type,
            "x": district.x,
            "y": district.y,
            "image_url": district.image_url,
            "map_icon_url": district.map_icon_url,
            "map_image_url": district.map_image_url,
            "sort_order": district.sort_order,
            "locations": district_root_locations
        })

    # Build unified map_items list combining ALL locations and districts
    # (including those without coordinates — the frontend handles placed/unplaced separation)
    map_items = []
    for loc in all_locations:
        map_items.append({
            "id": loc.id,
            "name": loc.name,
            "type": "location",
            "map_icon_url": loc.map_icon_url,
            "map_x": loc.map_x,
            "map_y": loc.map_y,
            "marker_type": loc.marker_type,
            "image_url": loc.image_url,
            "district_id": loc.district_id,
            "sort_order": loc.sort_order,
            "recommended_level": loc.recommended_level,
        })
    for district in sorted(region.districts, key=lambda d: d.sort_order):
        map_items.append({
            "id": district.id,
            "name": district.name,
            "type": "district",
            "map_icon_url": district.map_icon_url,
            "map_x": district.x,
            "map_y": district.y,
            "marker_type": district.marker_type,
            "image_url": district.image_url,
            "map_image_url": district.map_image_url,
            "parent_district_id": district.parent_district_id,
            "sort_order": district.sort_order,
            "recommended_level": district.recommended_level,
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
                # If the row is reversed relative to normalized (min,max) direction,
                # reverse the waypoints so they match from_id→to_id order
                pd = n.path_data
                if pd and n.location_id > n.neighbor_id:
                    pd = list(reversed(pd))
                neighbor_edges.append({
                    "from_id": edge[0],
                    "to_id": edge[1],
                    "energy_cost": n.energy_cost,
                    "path_data": pd,
                })

    # Получаем стрелки переходов для региона
    arrows_result = await session.execute(
        select(RegionTransitionArrow).where(RegionTransitionArrow.region_id == region_id)
    )
    arrows = arrows_result.scalars().all()

    # Получаем имена целевых регионов для стрелок
    target_region_ids = [a.target_region_id for a in arrows]
    target_region_names = {}
    if target_region_ids:
        target_regions_result = await session.execute(
            select(Region.id, Region.name).where(Region.id.in_(target_region_ids))
        )
        for row in target_regions_result:
            target_region_names[row[0]] = row[1]

    # Batch-query paired arrow neighbors for cross-region highlighting
    paired_arrow_ids = [a.paired_arrow_id for a in arrows if a.paired_arrow_id]
    paired_arrow_location_map: Dict[int, list] = {}  # paired_arrow_id -> [location_id, ...]
    if paired_arrow_ids:
        paired_an_result = await session.execute(
            select(ArrowNeighbor).where(ArrowNeighbor.arrow_id.in_(paired_arrow_ids))
        )
        for pan in paired_an_result.scalars().all():
            paired_arrow_location_map.setdefault(pan.arrow_id, []).append(pan.location_id)

    # Добавляем стрелки в map_items
    arrow_ids = []
    for arrow in arrows:
        target_name = target_region_names.get(arrow.target_region_id, "")
        display_name = arrow.label if arrow.label else f"\u2192 {target_name}"
        paired_location_ids = paired_arrow_location_map.get(arrow.paired_arrow_id, []) if arrow.paired_arrow_id else []
        map_items.append({
            "id": arrow.id,
            "name": display_name,
            "type": "arrow",
            "map_icon_url": None,
            "map_x": arrow.x,
            "map_y": arrow.y,
            "marker_type": None,
            "image_url": None,
            "target_region_id": arrow.target_region_id,
            "target_region_name": target_name,
            "paired_arrow_id": arrow.paired_arrow_id,
            "paired_location_ids": paired_location_ids,
            "rotation": arrow.rotation,
        })
        arrow_ids.append(arrow.id)

    # Получаем arrow_edges
    arrow_edges = []
    if arrow_ids:
        arrow_neighbors_result = await session.execute(
            select(ArrowNeighbor).where(ArrowNeighbor.arrow_id.in_(arrow_ids))
        )
        for an in arrow_neighbors_result.scalars().all():
            arrow_edges.append({
                "location_id": an.location_id,
                "arrow_id": an.arrow_id,
                "energy_cost": an.energy_cost,
                "path_data": an.path_data,
            })

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
        "arrow_edges": arrow_edges,
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
        marker_type=district.marker_type or "safe",
        x=district.x,
        y=district.y,
        image_url=district.image_url or "",  # Используем пустую строку вместо None
        map_icon_url=district.map_icon_url,
        parent_district_id=district.parent_district_id,
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
    
    # Обновление полей — используем exclude_unset чтобы отличить "не передано" от "передано как null"
    update_fields = data.dict(exclude_unset=True) if hasattr(data, 'dict') else {}
    for field in ('name', 'description', 'image_url', 'recommended_level',
                  'entrance_location_id', 'x', 'y', 'map_icon_url',
                  'parent_district_id', 'marker_type', 'map_image_url'):
        if field in update_fields:
            setattr(db_district, field, update_fields[field])

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
async def add_neighbor(session: AsyncSession, location_id: int, neighbor_id: int, energy_cost: int, path_data=None) -> dict:
    """Добавляет соседа к локации"""
    # Сериализуем path_data в формат для JSON-колонки
    path_data_json = [{"x": wp["x"], "y": wp["y"]} for wp in path_data] if path_data else None

    # Проверяем, существует ли уже такая связь
    forward_result = await session.execute(
        select(LocationNeighbor).where(
            LocationNeighbor.location_id == location_id,
            LocationNeighbor.neighbor_id == neighbor_id
        )
    )
    existing_forward = forward_result.scalars().first()

    if existing_forward:
        # Если связь уже существует, обновляем energy_cost и path_data
        existing_forward.energy_cost = energy_cost
        existing_forward.path_data = path_data_json
    else:
        # Иначе создаем новую связь
        forward = LocationNeighbor(
            location_id=location_id,
            neighbor_id=neighbor_id,
            energy_cost=energy_cost,
            path_data=path_data_json
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
        existing_reverse.path_data = path_data_json
    else:
        reverse = LocationNeighbor(
            location_id=neighbor_id,
            neighbor_id=location_id,
            energy_cost=energy_cost,
            path_data=path_data_json
        )
        session.add(reverse)

    # Сохраняем изменения
    await session.commit()

    # Возвращаем информацию о созданной связи
    return {
        "location_id": location_id,
        "neighbor_id": neighbor_id,
        "energy_cost": energy_cost,
        "path_data": path_data_json
    }


async def update_neighbor_path(session: AsyncSession, from_id: int, to_id: int, path_data: list) -> Optional[dict]:
    """Обновляет path_data на обоих направлениях связи соседей"""
    path_data_json = [{"x": wp["x"], "y": wp["y"]} for wp in path_data] if path_data is not None else None

    # Ищем прямую связь
    forward_result = await session.execute(
        select(LocationNeighbor).where(
            LocationNeighbor.location_id == from_id,
            LocationNeighbor.neighbor_id == to_id
        )
    )
    forward = forward_result.scalars().first()

    # Ищем обратную связь
    reverse_result = await session.execute(
        select(LocationNeighbor).where(
            LocationNeighbor.location_id == to_id,
            LocationNeighbor.neighbor_id == from_id
        )
    )
    reverse = reverse_result.scalars().first()

    # Если нет ни одной связи — соседства не существует
    if not forward and not reverse:
        return None

    # Обновляем path_data на обоих направлениях
    if forward:
        forward.path_data = path_data_json
    if reverse:
        reverse.path_data = path_data_json

    await session.commit()

    energy_cost = forward.energy_cost if forward else reverse.energy_cost
    return {
        "from_id": from_id,
        "to_id": to_id,
        "energy_cost": energy_cost,
        "path_data": path_data_json,
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
        "marker_type": loc.marker_type,
        "map_icon_url": loc.map_icon_url,
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


async def get_character_post_stats(session: AsyncSession, character_ids: List[int]) -> Dict[str, dict]:
    """Batch-fetch post count and last post date per character_id."""
    if not character_ids:
        return {}
    result = await session.execute(
        select(
            Post.character_id,
            sa_func.count().label("count"),
            sa_func.max(Post.created_at).label("last_date"),
        )
        .where(Post.character_id.in_(character_ids))
        .group_by(Post.character_id)
    )
    rows = result.all()
    stats: Dict[str, dict] = {}
    for row in rows:
        stats[str(row.character_id)] = {
            "count": row.count,
            "last_date": row.last_date,
        }
    return stats


async def like_post(session: AsyncSession, post_id: int, character_id: int) -> PostLike:
    """Add a like to a post. Raises 404 if post not found, 409 if already liked."""
    # Verify the post exists
    result = await session.execute(select(Post).where(Post.id == post_id))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Post not found")

    new_like = PostLike(post_id=post_id, character_id=character_id)
    session.add(new_like)
    try:
        await session.commit()
        await session.refresh(new_like)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Post already liked by this character")
    return new_like


async def unlike_post(session: AsyncSession, post_id: int, character_id: int) -> None:
    """Remove a like from a post. Raises 404 if like not found."""
    result = await session.execute(
        select(PostLike).where(
            PostLike.post_id == post_id,
            PostLike.character_id == character_id
        )
    )
    like = result.scalars().first()
    if not like:
        raise HTTPException(status_code=404, detail="Like not found")
    await session.delete(like)
    await session.commit()


async def get_likes_for_posts(session: AsyncSession, post_ids: List[int]) -> Dict[int, dict]:
    """Batch-fetch likes for a list of post IDs.
    Returns: {post_id: {"likes_count": int, "liked_by": [character_id, ...]}}
    """
    if not post_ids:
        return {}

    result = await session.execute(
        select(PostLike).where(PostLike.post_id.in_(post_ids))
    )
    likes = result.scalars().all()

    likes_map: Dict[int, dict] = {pid: {"likes_count": 0, "liked_by": []} for pid in post_ids}
    for like in likes:
        if like.post_id in likes_map:
            likes_map[like.post_id]["likes_count"] += 1
            likes_map[like.post_id]["liked_by"].append(like.character_id)

    return likes_map


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
        # 1) Удаляем только ручные связи, где X — одна из сторон
        #    (сохраняем is_auto_arrow=True, созданные системой стрелок)
        await db.execute(
            delete(LocationNeighbor).where(
                ((LocationNeighbor.location_id == location_id)
                 | (LocationNeighbor.neighbor_id == location_id))
                & (LocationNeighbor.is_auto_arrow == False)
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

async def update_items_sort_order(session: AsyncSession, items: list):
    """Batch-update sort_order for districts and locations."""
    import logging
    logger = logging.getLogger(__name__)
    updated = 0
    for item in items:
        if item.type == "district":
            result = await session.execute(
                select(District).where(District.id == item.id)
            )
            obj = result.scalars().first()
            if obj:
                obj.sort_order = item.sort_order
                updated += 1
            else:
                logger.warning(f"District {item.id} not found for sort_order update")
        elif item.type == "location":
            result = await session.execute(
                select(Location).where(Location.id == item.id)
            )
            obj = result.scalars().first()
            if obj:
                obj.sort_order = item.sort_order
                updated += 1
            else:
                logger.warning(f"Location {item.id} not found for sort_order update")
    await session.commit()
    logger.info(f"sort_order: updated {updated}/{len(items)} items")


async def delete_region(session: AsyncSession, region_id: int, commit: bool = True):
    """
    Удаляет регион вместе со всеми его районами и локациями.
    """
    region_result = await session.execute(
        select(Region).where(Region.id == region_id)
    )
    region = region_result.scalars().first()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")

    districts_result = await session.execute(
        select(District).where(District.region_id == region_id)
    )
    districts = districts_result.scalars().all()

    for d in districts:
        await delete_district(session, d.id, commit=False)

    # Удаляем standalone-локации региона
    await session.execute(
        delete(Location).where(Location.region_id == region_id, Location.district_id.is_(None))
    )

    await session.execute(
        delete(Region).where(Region.id == region_id)
    )

    if commit:
        await session.commit()


async def delete_country(session: AsyncSession, country_id: int):
    """Удаляет страну вместе со всеми регионами, районами и локациями."""
    country_result = await session.execute(
        select(Country).where(Country.id == country_id)
    )
    country = country_result.scalars().first()
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")

    # Удаляем все регионы страны
    regions_result = await session.execute(
        select(Region).where(Region.country_id == country_id)
    )
    regions = regions_result.scalars().all()
    for r in regions:
        await delete_region(session, r.id, commit=False)

    # Удаляем страну
    await session.execute(
        delete(Country).where(Country.id == country_id)
    )
    await session.commit()


logger = logging.getLogger("location-service.crud")
async def get_client_location_details(session: AsyncSession, location_id: int, user_id: Optional[int] = None) -> Optional[dict]:
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
                "id": neighbor_loc.id,
                "name": neighbor_loc.name,
                "recommended_level": neighbor_loc.recommended_level,
                "image_url": neighbor_loc.image_url,
                "energy_cost": n.energy_cost
            })

    # 3. Получаем список персонажей для локации через новый эндпоинт Character‑service
    players = await get_players_in_location(location_id)

    # 3b. Получаем список NPC для локации
    npcs = await get_npcs_in_location(location_id)

    # 4. Получаем посты для локации
    posts_db = await get_posts_by_location(session, location_id)
    detailed_posts = []
    for post in posts_db:
        detailed_post = await get_post_details(post)
        detailed_posts.append(detailed_post)

    # 5. Batch-fetch likes for all posts
    post_ids = [p["post_id"] for p in detailed_posts]
    likes_map = await get_likes_for_posts(session, post_ids)
    for post_dict in detailed_posts:
        pid = post_dict["post_id"]
        post_dict["likes_count"] = likes_map.get(pid, {}).get("likes_count", 0)
        post_dict["liked_by"] = likes_map.get(pid, {}).get("liked_by", [])

    # 6. Получаем лут в локации
    loot_items = await get_location_loot(session, location_id)

    # 7. Проверяем, добавлена ли локация в избранное
    favorited = False
    if user_id is not None:
        favorited = await is_favorited(session, user_id, location_id)

    return {
        "id": loc.id,
        "name": loc.name,
        "type": loc.type,
        "parent_id": loc.parent_id,
        "description": loc.description,
        "image_url": loc.image_url,
        "recommended_level": loc.recommended_level,
        "quick_travel_marker": loc.quick_travel_marker,
        "marker_type": loc.marker_type,
        "district_id": loc.district_id,
        "region_id": loc.region_id,
        "is_favorited": favorited,
        "neighbors": detailed_neighbors,
        "players": players,
        "npcs": npcs,
        "posts": detailed_posts,
        "loot": loot_items,
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
        "post_id": post.id,
        "character_id": post.character_id,
        "character_photo": profile_data.get("character_photo", ""),
        "character_title": profile_data.get("character_title", ""),
        "character_title_rarity": profile_data.get("character_title_rarity"),
        "character_level": profile_data.get("character_level"),
        "user_id": profile_data.get("user_id"),
        "user_nickname": profile_data.get("user_nickname", ""),
        "character_name": profile_data.get("character_name", ""),
        "content": post.content,
        "length": len(post.content),
        "created_at": post.created_at,
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


async def get_npcs_in_location(location_id: int) -> List[dict]:
    """
    Получает список NPC, находящихся в заданной локации, через Character-service.
    GET {settings.CHARACTER_SERVICE_URL}/characters/npcs/by_location?location_id={location_id}
    """
    url = f"{settings.CHARACTER_SERVICE_URL}/characters/npcs/by_location?location_id={location_id}"
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка при получении NPC для локации {location_id}: {e}")
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


# -------------------------------
#   LOCATION LOOT
# -------------------------------
async def get_location_loot(session: AsyncSession, location_id: int) -> List[dict]:
    """
    Получает список лута в локации, обогащая данными из таблицы items (shared DB).
    """
    query = text("""
        SELECT ll.id, ll.location_id, ll.item_id, ll.quantity,
               ll.dropped_by_character_id, ll.dropped_at,
               i.name AS item_name, i.image AS item_image,
               i.item_rarity, i.item_type
        FROM location_loot ll
        LEFT JOIN items i ON ll.item_id = i.id
        WHERE ll.location_id = :location_id
        ORDER BY ll.dropped_at DESC
    """)
    result = await session.execute(query, {"location_id": location_id})
    rows = result.fetchall()
    return [
        {
            "id": row[0],
            "location_id": row[1],
            "item_id": row[2],
            "quantity": row[3],
            "dropped_by_character_id": row[4],
            "dropped_at": row[5],
            "item_name": row[6],
            "item_image": row[7],
            "item_rarity": row[8],
            "item_type": row[9],
        }
        for row in rows
    ]


async def create_location_loot(
    session: AsyncSession,
    location_id: int,
    item_id: int,
    quantity: int,
    character_id: Optional[int] = None,
) -> LocationLoot:
    """Создаёт запись лута в локации."""
    loot = LocationLoot(
        location_id=location_id,
        item_id=item_id,
        quantity=quantity,
        dropped_by_character_id=character_id,
    )
    session.add(loot)
    await session.commit()
    await session.refresh(loot)
    return loot


async def pickup_location_loot(session: AsyncSession, loot_id: int) -> Optional[dict]:
    """
    Забирает лут: SELECT FOR UPDATE + удаление.
    Возвращает данные лута или None, если не найден.
    """
    stmt = select(LocationLoot).where(LocationLoot.id == loot_id).with_for_update()
    result = await session.execute(stmt)
    loot = result.scalars().first()
    if not loot:
        return None

    loot_data = {
        "id": loot.id,
        "location_id": loot.location_id,
        "item_id": loot.item_id,
        "quantity": loot.quantity,
        "dropped_by_character_id": loot.dropped_by_character_id,
        "dropped_at": loot.dropped_at,
    }

    await session.delete(loot)
    await session.commit()
    return loot_data


# -------------------------------
#   LOCATION FAVORITES
# -------------------------------
async def add_favorite(session: AsyncSession, user_id: int, location_id: int) -> LocationFavorite:
    """Add a location to user's favorites. Raises 409 if already favorited."""
    fav = LocationFavorite(user_id=user_id, location_id=location_id)
    session.add(fav)
    try:
        await session.commit()
        await session.refresh(fav)
        return fav
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Локация уже в избранном")


async def remove_favorite(session: AsyncSession, user_id: int, location_id: int) -> None:
    """Remove a location from user's favorites. Raises 404 if not found."""
    result = await session.execute(
        select(LocationFavorite).where(
            LocationFavorite.user_id == user_id,
            LocationFavorite.location_id == location_id,
        )
    )
    fav = result.scalars().first()
    if not fav:
        raise HTTPException(status_code=404, detail="Локация не найдена в избранном")
    await session.delete(fav)
    await session.commit()


async def get_favorite_user_ids(session: AsyncSession, location_id: int) -> List[int]:
    """Returns list of user_ids who favorited the given location."""
    result = await session.execute(
        select(LocationFavorite.user_id).where(LocationFavorite.location_id == location_id)
    )
    return [row[0] for row in result.fetchall()]


async def is_favorited(session: AsyncSession, user_id: int, location_id: int) -> bool:
    """Check if a user has favorited a location."""
    result = await session.execute(
        select(LocationFavorite.id).where(
            LocationFavorite.user_id == user_id,
            LocationFavorite.location_id == location_id,
        )
    )
    return result.scalars().first() is not None


# -------------------------------
#   POST MODERATION
# -------------------------------
async def create_deletion_request(
    session: AsyncSession, post_id: int, user_id: int, reason: Optional[str] = None
) -> PostDeletionRequest:
    """Create a deletion request for a post. User must own the post. No duplicate pending requests."""
    # Verify post exists
    result = await session.execute(select(Post).where(Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(status_code=404, detail="Пост не найден")

    # Verify user owns the post (check via character ownership — post has character_id,
    # we need to check that the character belongs to the user)
    char_result = await session.execute(
        text("SELECT user_id FROM characters WHERE id = :cid"),
        {"cid": post.character_id},
    )
    char_row = char_result.fetchone()
    if not char_row or char_row[0] != user_id:
        raise HTTPException(status_code=403, detail="Вы можете запрашивать удаление только своих постов")

    # Check no duplicate pending request
    existing = await session.execute(
        select(PostDeletionRequest).where(
            PostDeletionRequest.post_id == post_id,
            PostDeletionRequest.user_id == user_id,
            PostDeletionRequest.status == "pending",
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Запрос на удаление этого поста уже существует")

    req = PostDeletionRequest(
        post_id=post_id,
        user_id=user_id,
        reason=reason,
        status="pending",
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


async def create_report(
    session: AsyncSession, post_id: int, user_id: int, reason: Optional[str] = None
) -> PostReport:
    """Create a report for a post. One report per user per post (unique constraint)."""
    # Verify post exists
    result = await session.execute(select(Post).where(Post.id == post_id))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Пост не найден")

    report = PostReport(
        post_id=post_id,
        user_id=user_id,
        reason=reason,
        status="pending",
    )
    session.add(report)
    try:
        await session.commit()
        await session.refresh(report)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Вы уже отправляли жалобу на этот пост")
    return report


async def get_pending_deletion_requests(session: AsyncSession) -> List[dict]:
    """List all pending deletion requests with post content."""
    result = await session.execute(
        select(PostDeletionRequest, Post)
        .outerjoin(Post, PostDeletionRequest.post_id == Post.id)
        .where(PostDeletionRequest.status == "pending")
        .order_by(PostDeletionRequest.created_at.desc())
    )
    rows = result.all()
    items = []
    for req, post in rows:
        items.append({
            "id": req.id,
            "post_id": req.post_id,
            "user_id": req.user_id,
            "reason": req.reason,
            "status": req.status,
            "created_at": req.created_at,
            "reviewed_at": req.reviewed_at,
            "post_content": post.content if post else None,
            "post_character_id": post.character_id if post else None,
            "post_location_id": post.location_id if post else None,
        })
    return items


async def get_pending_reports(session: AsyncSession) -> List[dict]:
    """List all pending reports with post content."""
    result = await session.execute(
        select(PostReport, Post)
        .outerjoin(Post, PostReport.post_id == Post.id)
        .where(PostReport.status == "pending")
        .order_by(PostReport.created_at.desc())
    )
    rows = result.all()
    items = []
    for report, post in rows:
        items.append({
            "id": report.id,
            "post_id": report.post_id,
            "user_id": report.user_id,
            "reason": report.reason,
            "status": report.status,
            "created_at": report.created_at,
            "reviewed_at": report.reviewed_at,
            "post_content": post.content if post else None,
            "post_character_id": post.character_id if post else None,
            "post_location_id": post.location_id if post else None,
        })
    return items


async def review_deletion_request(
    session: AsyncSession, request_id: int, action: str, admin_user_id: int
) -> PostDeletionRequest:
    """Review a deletion request. If approved, delete the post."""
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Действие должно быть 'approve' или 'reject'")

    result = await session.execute(
        select(PostDeletionRequest).where(PostDeletionRequest.id == request_id)
    )
    req = result.scalars().first()
    if not req:
        raise HTTPException(status_code=404, detail="Запрос на удаление не найден")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="Запрос уже рассмотрен")

    if action == "approve":
        # Delete the post
        await session.execute(delete(Post).where(Post.id == req.post_id))
        req.status = "approved"
    else:
        req.status = "rejected"

    req.reviewed_by_user_id = admin_user_id
    req.reviewed_at = sa_func.now()
    await session.commit()
    await session.refresh(req)
    return req


async def review_report(
    session: AsyncSession, report_id: int, action: str, admin_user_id: int
) -> PostReport:
    """Review a report. If resolved, optionally delete the post."""
    if action not in ("resolve", "dismiss"):
        raise HTTPException(status_code=400, detail="Действие должно быть 'resolve' или 'dismiss'")

    result = await session.execute(
        select(PostReport).where(PostReport.id == report_id)
    )
    report = result.scalars().first()
    if not report:
        raise HTTPException(status_code=404, detail="Жалоба не найдена")
    if report.status != "pending":
        raise HTTPException(status_code=400, detail="Жалоба уже рассмотрена")

    if action == "resolve":
        # Delete the post when report is resolved
        await session.execute(delete(Post).where(Post.id == report.post_id))
        report.status = "resolved"
    else:
        report.status = "dismissed"

    report.reviewed_by_user_id = admin_user_id
    report.reviewed_at = sa_func.now()
    await session.commit()
    await session.refresh(report)
    return report


# -------------------------------
#   DIALOGUE TREE CRUD
# -------------------------------
async def create_dialogue_tree(session: AsyncSession, data: dict) -> DialogueTree:
    """Create a dialogue tree with nodes and options, resolving index-based links."""
    tree = DialogueTree(
        npc_id=data["npc_id"],
        title=data["title"],
        is_active=data.get("is_active", True),
    )
    session.add(tree)
    await session.flush()  # get tree.id

    nodes_data = data.get("nodes", [])
    db_nodes = []
    for node_data in nodes_data:
        node = DialogueNode(
            tree_id=tree.id,
            npc_text=node_data["npc_text"],
            is_root=node_data.get("is_root", False),
            sort_order=node_data.get("sort_order", 0),
            action_type=node_data.get("action_type"),
            action_data=node_data.get("action_data"),
        )
        session.add(node)
        db_nodes.append(node)

    await session.flush()  # get all node ids

    # Now create options with resolved next_node_id
    for i, node_data in enumerate(nodes_data):
        for opt_data in node_data.get("options", []):
            next_node_id = None
            next_node_index = opt_data.get("next_node_index")
            if next_node_index is not None and 0 <= next_node_index < len(db_nodes):
                next_node_id = db_nodes[next_node_index].id

            option = DialogueOption(
                node_id=db_nodes[i].id,
                text=opt_data["text"],
                next_node_id=next_node_id,
                sort_order=opt_data.get("sort_order", 0),
                condition=opt_data.get("condition"),
            )
            session.add(option)

    await session.commit()

    # Reload with relationships
    return await get_dialogue_tree(session, tree.id)


async def get_dialogue_tree(session: AsyncSession, tree_id: int) -> Optional[DialogueTree]:
    """Get a single dialogue tree with all nodes and options."""
    result = await session.execute(
        select(DialogueTree)
        .options(
            selectinload(DialogueTree.nodes).selectinload(DialogueNode.options)
        )
        .where(DialogueTree.id == tree_id)
    )
    return result.scalars().first()


async def list_dialogue_trees(session: AsyncSession, npc_id: Optional[int] = None) -> List[DialogueTree]:
    """List dialogue trees, optionally filtered by npc_id."""
    stmt = select(DialogueTree)
    if npc_id is not None:
        stmt = stmt.where(DialogueTree.npc_id == npc_id)
    stmt = stmt.order_by(DialogueTree.id.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_dialogue_tree(session: AsyncSession, tree_id: int, data: dict) -> Optional[DialogueTree]:
    """Update a dialogue tree. If nodes are provided, replace all nodes and options."""
    result = await session.execute(
        select(DialogueTree).where(DialogueTree.id == tree_id)
    )
    tree = result.scalars().first()
    if not tree:
        return None

    if data.get("title") is not None:
        tree.title = data["title"]
    if data.get("is_active") is not None:
        tree.is_active = data["is_active"]

    if data.get("nodes") is not None:
        # Delete existing nodes (cascade deletes options too)
        await session.execute(
            delete(DialogueNode).where(DialogueNode.tree_id == tree_id)
        )
        await session.flush()

        nodes_data = data["nodes"]
        db_nodes = []
        for node_data in nodes_data:
            node = DialogueNode(
                tree_id=tree.id,
                npc_text=node_data["npc_text"],
                is_root=node_data.get("is_root", False),
                sort_order=node_data.get("sort_order", 0),
                action_type=node_data.get("action_type"),
                action_data=node_data.get("action_data"),
            )
            session.add(node)
            db_nodes.append(node)

        await session.flush()

        for i, node_data in enumerate(nodes_data):
            for opt_data in node_data.get("options", []):
                next_node_id = None
                next_node_index = opt_data.get("next_node_index")
                if next_node_index is not None and 0 <= next_node_index < len(db_nodes):
                    next_node_id = db_nodes[next_node_index].id

                option = DialogueOption(
                    node_id=db_nodes[i].id,
                    text=opt_data["text"],
                    next_node_id=next_node_id,
                    sort_order=opt_data.get("sort_order", 0),
                    condition=opt_data.get("condition"),
                )
                session.add(option)

    await session.commit()
    return await get_dialogue_tree(session, tree_id)


async def delete_dialogue_tree(session: AsyncSession, tree_id: int) -> bool:
    """Delete a dialogue tree by id. Returns True if deleted."""
    result = await session.execute(
        select(DialogueTree).where(DialogueTree.id == tree_id)
    )
    tree = result.scalars().first()
    if not tree:
        return False
    await session.delete(tree)
    await session.commit()
    return True


async def get_dialogue_quest_ids(session: AsyncSession, npc_id: int) -> List[int]:
    """Get all quest IDs referenced in dialogue nodes of active trees for an NPC."""
    result = await session.execute(
        select(DialogueTree)
        .options(selectinload(DialogueTree.nodes))
        .where(DialogueTree.npc_id == npc_id, DialogueTree.is_active == True)
    )
    trees = result.scalars().all()
    quest_ids = []
    for tree in trees:
        for node in tree.nodes:
            if node.action_type == 'give_quest' and node.action_data:
                qid = node.action_data.get('quest_id') if isinstance(node.action_data, dict) else None
                if qid:
                    quest_ids.append(int(qid))
    return quest_ids


async def get_active_dialogue_for_npc(session: AsyncSession, npc_id: int) -> Optional[dict]:
    """Get the active dialogue tree root node for a given NPC (player-facing)."""
    result = await session.execute(
        select(DialogueTree)
        .options(
            selectinload(DialogueTree.nodes).selectinload(DialogueNode.options)
        )
        .where(DialogueTree.npc_id == npc_id, DialogueTree.is_active == True)
        .limit(1)
    )
    tree = result.scalars().first()
    if not tree:
        return None

    # Find root node
    root = None
    for node in tree.nodes:
        if node.is_root:
            root = node
            break

    if not root:
        # Fallback: use the first node by sort_order
        sorted_nodes = sorted(tree.nodes, key=lambda n: n.sort_order)
        root = sorted_nodes[0] if sorted_nodes else None

    if not root:
        return None

    return _build_node_response(root)


async def get_dialogue_node(session: AsyncSession, node_id: int) -> Optional[DialogueNode]:
    """Get a single dialogue node with its options."""
    result = await session.execute(
        select(DialogueNode)
        .options(selectinload(DialogueNode.options))
        .where(DialogueNode.id == node_id)
    )
    return result.scalars().first()


def _build_node_response(node: DialogueNode) -> dict:
    """Build player-facing node response dict."""
    sorted_options = sorted(node.options, key=lambda o: o.sort_order)
    options = [
        {
            "id": opt.id,
            "text": opt.text,
            "next_node_id": opt.next_node_id,
        }
        for opt in sorted_options
    ]
    is_end = len(options) == 0 or all(o["next_node_id"] is None for o in options)
    return {
        "id": node.id,
        "npc_text": node.npc_text,
        "action_type": node.action_type,
        "action_data": node.action_data,
        "options": options,
        "is_end": is_end,
    }


# -------------------------------
#   NPC SHOP
# -------------------------------
async def create_npc_shop_item(session: AsyncSession, npc_id: int, data: dict) -> NpcShopItem:
    """Add an item to NPC's shop inventory."""
    shop_item = NpcShopItem(
        npc_id=npc_id,
        item_id=data["item_id"],
        buy_price=data["buy_price"],
        sell_price=data.get("sell_price", 0),
        stock=data.get("stock"),
    )
    session.add(shop_item)
    await session.commit()
    await session.refresh(shop_item)
    return shop_item


async def get_npc_shop_items_admin(session: AsyncSession, npc_id: int) -> List[dict]:
    """Get all shop items for an NPC (admin view, includes inactive)."""
    query = text("""
        SELECT si.id, si.npc_id, si.item_id, si.buy_price, si.sell_price,
               si.stock, si.is_active, si.created_at,
               i.name AS item_name, i.image AS item_image,
               i.item_rarity, i.item_type
        FROM npc_shop_items si
        LEFT JOIN items i ON si.item_id = i.id
        WHERE si.npc_id = :npc_id
        ORDER BY si.id ASC
    """)
    result = await session.execute(query, {"npc_id": npc_id})
    rows = result.fetchall()
    return [
        {
            "id": row[0],
            "npc_id": row[1],
            "item_id": row[2],
            "buy_price": row[3],
            "sell_price": row[4],
            "stock": row[5],
            "is_active": bool(row[6]),
            "created_at": row[7],
            "item_name": row[8],
            "item_image": row[9],
            "item_rarity": row[10],
            "item_type": row[11],
        }
        for row in rows
    ]


async def update_npc_shop_item(session: AsyncSession, shop_item_id: int, data: dict) -> Optional[NpcShopItem]:
    """Update an NPC shop item's price, stock, or active status."""
    result = await session.execute(
        select(NpcShopItem).where(NpcShopItem.id == shop_item_id)
    )
    shop_item = result.scalars().first()
    if not shop_item:
        return None

    if "buy_price" in data and data["buy_price"] is not None:
        shop_item.buy_price = data["buy_price"]
    if "sell_price" in data and data["sell_price"] is not None:
        shop_item.sell_price = data["sell_price"]
    if "stock" in data:
        shop_item.stock = data["stock"]
    if "is_active" in data and data["is_active"] is not None:
        shop_item.is_active = data["is_active"]

    await session.commit()
    await session.refresh(shop_item)
    return shop_item


async def delete_npc_shop_item(session: AsyncSession, shop_item_id: int) -> bool:
    """Remove an item from NPC's shop."""
    result = await session.execute(
        select(NpcShopItem).where(NpcShopItem.id == shop_item_id)
    )
    shop_item = result.scalars().first()
    if not shop_item:
        return False
    await session.delete(shop_item)
    await session.commit()
    return True


async def get_npc_shop_items_player(session: AsyncSession, npc_id: int) -> List[dict]:
    """Get active shop items for an NPC (player view)."""
    query = text("""
        SELECT si.id, si.npc_id, si.item_id, si.buy_price, si.sell_price,
               si.stock, si.is_active, si.created_at,
               i.name AS item_name, i.image AS item_image,
               i.item_rarity, i.item_type
        FROM npc_shop_items si
        LEFT JOIN items i ON si.item_id = i.id
        WHERE si.npc_id = :npc_id AND si.is_active = 1
        ORDER BY si.id ASC
    """)
    result = await session.execute(query, {"npc_id": npc_id})
    rows = result.fetchall()
    return [
        {
            "id": row[0],
            "npc_id": row[1],
            "item_id": row[2],
            "buy_price": row[3],
            "sell_price": row[4],
            "stock": row[5],
            "is_active": bool(row[6]),
            "created_at": row[7],
            "item_name": row[8],
            "item_image": row[9],
            "item_rarity": row[10],
            "item_type": row[11],
        }
        for row in rows
    ]


async def get_shop_item_by_id(session: AsyncSession, shop_item_id: int) -> Optional[NpcShopItem]:
    """Get a single shop item by its ID."""
    result = await session.execute(
        select(NpcShopItem).where(NpcShopItem.id == shop_item_id)
    )
    return result.scalars().first()


async def _log_gold_transaction(
    session: AsyncSession,
    character_id: int,
    amount: int,
    balance_after: int,
    transaction_type: str,
    source: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """
    Insert a row into gold_transactions for audit/tracking.
    Wrapped in try/except so logging never breaks existing functionality.
    """
    try:
        await session.execute(
            text("""
                INSERT INTO gold_transactions
                    (character_id, amount, balance_after, transaction_type, source, metadata)
                VALUES
                    (:character_id, :amount, :balance_after, :transaction_type, :source, :metadata)
            """),
            {
                "character_id": character_id,
                "amount": amount,
                "balance_after": balance_after,
                "transaction_type": transaction_type,
                "source": source,
                "metadata": json.dumps(metadata) if metadata else None,
            },
        )
        await session.commit()
    except Exception:
        logger.exception("Failed to log gold transaction for character %s", character_id)


async def deduct_currency(
    session: AsyncSession,
    character_id: int,
    amount: int,
    transaction_type: str = "shop_purchase",
    source: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[int]:
    """
    Atomically deduct currency from character. Returns new balance or None if insufficient.
    Uses direct SQL UPDATE with WHERE check for atomicity in the shared DB.
    Logs the transaction into gold_transactions.
    """
    result = await session.execute(
        text("""
            UPDATE characters
            SET currency_balance = currency_balance - :amount
            WHERE id = :cid AND currency_balance >= :amount
        """),
        {"cid": character_id, "amount": amount},
    )
    if result.rowcount == 0:
        return None
    await session.commit()

    # Fetch new balance
    bal_result = await session.execute(
        text("SELECT currency_balance FROM characters WHERE id = :cid"),
        {"cid": character_id},
    )
    row = bal_result.fetchone()
    new_balance = row[0] if row else None

    # Log gold transaction (negative amount = spend)
    if new_balance is not None:
        await _log_gold_transaction(
            session,
            character_id=character_id,
            amount=-amount,
            balance_after=new_balance,
            transaction_type=transaction_type,
            source=source,
            metadata=metadata,
        )

    return new_balance


async def add_currency(
    session: AsyncSession,
    character_id: int,
    amount: int,
    transaction_type: str = "shop_sell",
    source: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[int]:
    """Add currency to character. Returns new balance. Logs the transaction."""
    await session.execute(
        text("""
            UPDATE characters
            SET currency_balance = currency_balance + :amount
            WHERE id = :cid
        """),
        {"cid": character_id, "amount": amount},
    )
    await session.commit()

    bal_result = await session.execute(
        text("SELECT currency_balance FROM characters WHERE id = :cid"),
        {"cid": character_id},
    )
    row = bal_result.fetchone()
    new_balance = row[0] if row else None

    # Log gold transaction (positive amount = earn)
    if new_balance is not None:
        await _log_gold_transaction(
            session,
            character_id=character_id,
            amount=amount,
            balance_after=new_balance,
            transaction_type=transaction_type,
            source=source,
            metadata=metadata,
        )

    return new_balance


async def get_character_location(session: AsyncSession, character_id: int) -> Optional[int]:
    """Get the current location ID of a character from shared DB."""
    result = await session.execute(
        text("SELECT current_location_id FROM characters WHERE id = :cid"),
        {"cid": character_id},
    )
    row = result.fetchone()
    if not row:
        return None
    return row[0]


async def get_npc_location(session: AsyncSession, npc_id: int) -> Optional[int]:
    """Get the current location of an NPC from shared DB."""
    result = await session.execute(
        text("SELECT current_location_id FROM characters WHERE id = :cid AND is_npc = 1"),
        {"cid": npc_id},
    )
    row = result.fetchone()
    if not row:
        return None
    return row[0]


async def decrement_stock(session: AsyncSession, shop_item_id: int, quantity: int) -> bool:
    """Decrement stock for a shop item. Returns False if insufficient stock."""
    result = await session.execute(
        text("""
            UPDATE npc_shop_items
            SET stock = stock - :qty
            WHERE id = :sid AND stock >= :qty
        """),
        {"sid": shop_item_id, "qty": quantity},
    )
    if result.rowcount == 0:
        return False
    await session.commit()
    return True


async def get_item_name(session: AsyncSession, item_id: int) -> Optional[str]:
    """Get item name from shared items table."""
    result = await session.execute(
        text("SELECT name FROM items WHERE id = :iid"),
        {"iid": item_id},
    )
    row = result.fetchone()
    return row[0] if row else None


async def find_sell_price_for_item(session: AsyncSession, npc_id: int, item_id: int) -> Optional[int]:
    """Find the sell price for an item in NPC's shop. Returns None if NPC won't buy it."""
    result = await session.execute(
        text("""
            SELECT sell_price FROM npc_shop_items
            WHERE npc_id = :npc_id AND item_id = :item_id
              AND is_active = 1 AND sell_price > 0
            LIMIT 1
        """),
        {"npc_id": npc_id, "item_id": item_id},
    )
    row = result.fetchone()
    return row[0] if row else None


# -------------------------------
#   QUESTS (Admin CRUD)
# -------------------------------
async def create_quest(session: AsyncSession, data: dict) -> Quest:
    """Create a quest with objectives."""
    objectives_data = data.pop("objectives", [])
    quest = Quest(
        npc_id=data["npc_id"],
        title=data["title"],
        description=data.get("description"),
        quest_type=data.get("quest_type", "standard"),
        min_level=data.get("min_level", 1),
        reward_currency=data.get("reward_currency", 0),
        reward_exp=data.get("reward_exp", 0),
        reward_items=data.get("reward_items"),
        is_active=data.get("is_active", True),
    )
    session.add(quest)
    await session.flush()

    for obj_data in objectives_data:
        objective = QuestObjective(
            quest_id=quest.id,
            description=obj_data["description"],
            objective_type=obj_data["objective_type"],
            target_id=obj_data.get("target_id"),
            target_count=obj_data.get("target_count", 1),
            sort_order=obj_data.get("sort_order", 0),
        )
        session.add(objective)

    await session.commit()
    await session.refresh(quest)

    # Eagerly load objectives
    result = await session.execute(
        select(Quest)
        .options(selectinload(Quest.objectives))
        .where(Quest.id == quest.id)
    )
    return result.scalars().first()


async def get_quests_admin(
    session: AsyncSession,
    npc_id: Optional[int] = None,
    quest_type: Optional[str] = None,
) -> List[Quest]:
    """List all quests with optional filters."""
    stmt = select(Quest).options(selectinload(Quest.objectives))
    if npc_id is not None:
        stmt = stmt.where(Quest.npc_id == npc_id)
    if quest_type is not None:
        stmt = stmt.where(Quest.quest_type == quest_type)
    stmt = stmt.order_by(Quest.id.asc())
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_quest_by_id(session: AsyncSession, quest_id: int) -> Optional[Quest]:
    """Get a single quest with objectives."""
    result = await session.execute(
        select(Quest)
        .options(selectinload(Quest.objectives))
        .where(Quest.id == quest_id)
    )
    return result.scalars().first()


async def update_quest(session: AsyncSession, quest_id: int, data: dict) -> Optional[Quest]:
    """Update a quest. If objectives are provided, replace them entirely."""
    result = await session.execute(
        select(Quest)
        .options(selectinload(Quest.objectives))
        .where(Quest.id == quest_id)
    )
    quest = result.scalars().first()
    if not quest:
        return None

    if "title" in data and data["title"] is not None:
        quest.title = data["title"]
    if "description" in data and data["description"] is not None:
        quest.description = data["description"]
    if "quest_type" in data and data["quest_type"] is not None:
        quest.quest_type = data["quest_type"]
    if "min_level" in data and data["min_level"] is not None:
        quest.min_level = data["min_level"]
    if "reward_currency" in data and data["reward_currency"] is not None:
        quest.reward_currency = data["reward_currency"]
    if "reward_exp" in data and data["reward_exp"] is not None:
        quest.reward_exp = data["reward_exp"]
    if "reward_items" in data:
        quest.reward_items = data["reward_items"]
    if "is_active" in data and data["is_active"] is not None:
        quest.is_active = data["is_active"]

    # Replace objectives if provided
    if "objectives" in data and data["objectives"] is not None:
        # Delete old objectives
        await session.execute(
            delete(QuestObjective).where(QuestObjective.quest_id == quest_id)
        )
        for obj_data in data["objectives"]:
            objective = QuestObjective(
                quest_id=quest_id,
                description=obj_data["description"],
                objective_type=obj_data["objective_type"],
                target_id=obj_data.get("target_id"),
                target_count=obj_data.get("target_count", 1),
                sort_order=obj_data.get("sort_order", 0),
            )
            session.add(objective)

    await session.commit()
    # Re-fetch with objectives
    result = await session.execute(
        select(Quest)
        .options(selectinload(Quest.objectives))
        .where(Quest.id == quest_id)
    )
    return result.scalars().first()


async def delete_quest(session: AsyncSession, quest_id: int) -> bool:
    """Delete a quest and its objectives (cascade)."""
    result = await session.execute(
        select(Quest).where(Quest.id == quest_id)
    )
    quest = result.scalars().first()
    if not quest:
        return False
    await session.delete(quest)
    await session.commit()
    return True


# -------------------------------
#   QUESTS (Player)
# -------------------------------
async def get_available_quests_for_npc(
    session: AsyncSession, npc_id: int, character_id: int
) -> List[Quest]:
    """
    Get quests from an NPC that are:
    - active
    - character meets min_level
    - character hasn't already accepted (unless repeatable and completed)
    """
    # Get character level
    char_result = await session.execute(
        text("SELECT level FROM characters WHERE id = :cid"),
        {"cid": character_id},
    )
    char_row = char_result.fetchone()
    char_level = char_row[0] if char_row else 1

    # Get IDs of quests this character currently has active
    active_result = await session.execute(
        text("""
            SELECT quest_id FROM character_quests
            WHERE character_id = :cid AND status = 'active'
        """),
        {"cid": character_id},
    )
    active_quest_ids = {row[0] for row in active_result.fetchall()}

    # Get IDs of quests this character has completed (for non-repeatable)
    completed_result = await session.execute(
        text("""
            SELECT quest_id FROM character_quests
            WHERE character_id = :cid AND status = 'completed'
        """),
        {"cid": character_id},
    )
    completed_quest_ids = {row[0] for row in completed_result.fetchall()}

    # Get all active quests for this NPC
    stmt = (
        select(Quest)
        .options(selectinload(Quest.objectives))
        .where(Quest.npc_id == npc_id, Quest.is_active == True, Quest.min_level <= char_level)
        .order_by(Quest.id.asc())
    )
    result = await session.execute(stmt)
    all_quests = result.scalars().all()

    available = []
    for q in all_quests:
        if q.id in active_quest_ids:
            status = 'active'
        elif q.id in completed_quest_ids:
            status = 'completed'
        else:
            status = 'available'
        available.append({
            "id": q.id,
            "title": q.title,
            "description": q.description,
            "quest_type": q.quest_type,
            "min_level": q.min_level,
            "reward_currency": q.reward_currency,
            "reward_exp": q.reward_exp,
            "reward_items": q.reward_items,
            "objectives": [
                {"id": o.id, "description": o.description, "objective_type": o.objective_type, "target_count": o.target_count, "sort_order": o.sort_order}
                for o in sorted(q.objectives, key=lambda x: x.sort_order)
            ],
            "player_status": status,
        })

    return available


async def accept_quest(
    session: AsyncSession, quest_id: int, character_id: int
) -> CharacterQuest:
    """Accept a quest. Creates character_quest and progress entries."""
    # Verify quest exists and is active
    quest = await get_quest_by_id(session, quest_id)
    if not quest or not quest.is_active:
        raise HTTPException(status_code=404, detail="Квест не найден или неактивен")

    # Check character level
    char_result = await session.execute(
        text("SELECT level FROM characters WHERE id = :cid"),
        {"cid": character_id},
    )
    char_row = char_result.fetchone()
    if not char_row:
        raise HTTPException(status_code=404, detail="Персонаж не найден")
    if char_row[0] < quest.min_level:
        raise HTTPException(status_code=400, detail=f"Требуется уровень {quest.min_level}")

    # Check if already has this quest active
    existing = await session.execute(
        text("""
            SELECT id, status FROM character_quests
            WHERE character_id = :cid AND quest_id = :qid
        """),
        {"cid": character_id, "qid": quest_id},
    )
    existing_row = existing.fetchone()
    if existing_row:
        if existing_row[1] == 'active':
            raise HTTPException(status_code=400, detail="Квест уже принят")
        if existing_row[1] == 'completed' and quest.quest_type != 'repeatable':
            raise HTTPException(status_code=400, detail="Квест уже выполнен")
        # For repeatable quests that were completed or abandoned, delete old entry
        await session.execute(
            text("DELETE FROM character_quests WHERE id = :id"),
            {"id": existing_row[0]},
        )
        await session.flush()

    # Create character_quest
    cq = CharacterQuest(
        character_id=character_id,
        quest_id=quest_id,
        status='active',
    )
    session.add(cq)
    await session.flush()

    # Create progress entries for each objective
    for objective in quest.objectives:
        progress = CharacterQuestProgress(
            character_quest_id=cq.id,
            objective_id=objective.id,
            current_count=0,
            is_completed=False,
        )
        session.add(progress)

    await session.commit()
    await session.refresh(cq)
    return cq


async def get_active_quests(session: AsyncSession, character_id: int) -> List[dict]:
    """Get all active quests for a character with progress details."""
    result = await session.execute(
        text("""
            SELECT cq.id, cq.quest_id, cq.status, cq.accepted_at,
                   q.title, q.description, q.quest_type, q.npc_id,
                   q.reward_currency, q.reward_exp, q.reward_items
            FROM character_quests cq
            JOIN quests q ON cq.quest_id = q.id
            WHERE cq.character_id = :cid AND cq.status = 'active'
            ORDER BY cq.accepted_at DESC
        """),
        {"cid": character_id},
    )
    rows = result.fetchall()

    quests = []
    for row in rows:
        cq_id = row[0]
        # Get progress for this character_quest
        prog_result = await session.execute(
            text("""
                SELECT cqp.objective_id, cqp.current_count, cqp.is_completed,
                       qo.description, qo.objective_type, qo.target_id, qo.target_count
                FROM character_quest_progress cqp
                JOIN quest_objectives qo ON cqp.objective_id = qo.id
                WHERE cqp.character_quest_id = :cqid
                ORDER BY qo.sort_order ASC
            """),
            {"cqid": cq_id},
        )
        prog_rows = prog_result.fetchall()

        import json
        reward_items_raw = row[10]
        if isinstance(reward_items_raw, str):
            try:
                reward_items_raw = json.loads(reward_items_raw)
            except (json.JSONDecodeError, TypeError):
                reward_items_raw = None

        objectives = [
            {
                "objective_id": p[0],
                "description": p[3],
                "objective_type": p[4],
                "target_id": p[5],
                "target_count": p[6],
                "current_count": p[1],
                "is_completed": bool(p[2]),
            }
            for p in prog_rows
        ]

        quests.append({
            "id": cq_id,
            "quest_id": row[1],
            "status": row[2],
            "accepted_at": row[3],
            "title": row[4],
            "description": row[5],
            "quest_type": row[6],
            "npc_id": row[7],
            "reward_currency": row[8],
            "reward_exp": row[9],
            "reward_items": reward_items_raw,
            "objectives": objectives,
        })

    return quests


async def update_quest_progress(
    session: AsyncSession,
    character_id: int,
    quest_id: int,
    objective_id: int,
    increment: int = 1,
) -> Optional[dict]:
    """
    Update progress on a quest objective.
    Returns updated progress info or None if not found.
    """
    # Find the character_quest
    cq_result = await session.execute(
        text("""
            SELECT cq.id FROM character_quests cq
            WHERE cq.character_id = :cid AND cq.quest_id = :qid AND cq.status = 'active'
        """),
        {"cid": character_id, "qid": quest_id},
    )
    cq_row = cq_result.fetchone()
    if not cq_row:
        return None
    cq_id = cq_row[0]

    # Get objective target_count
    obj_result = await session.execute(
        text("SELECT target_count FROM quest_objectives WHERE id = :oid"),
        {"oid": objective_id},
    )
    obj_row = obj_result.fetchone()
    if not obj_row:
        return None
    target_count = obj_row[0]

    # Update progress
    await session.execute(
        text("""
            UPDATE character_quest_progress
            SET current_count = LEAST(current_count + :inc, :target),
                is_completed = CASE WHEN current_count + :inc >= :target THEN 1 ELSE 0 END
            WHERE character_quest_id = :cqid AND objective_id = :oid
        """),
        {"inc": increment, "target": target_count, "cqid": cq_id, "oid": objective_id},
    )
    await session.commit()

    # Fetch updated progress
    prog_result = await session.execute(
        text("""
            SELECT current_count, is_completed
            FROM character_quest_progress
            WHERE character_quest_id = :cqid AND objective_id = :oid
        """),
        {"cqid": cq_id, "oid": objective_id},
    )
    prog_row = prog_result.fetchone()
    if not prog_row:
        return None

    return {
        "objective_id": objective_id,
        "current_count": prog_row[0],
        "is_completed": bool(prog_row[1]),
        "target_count": target_count,
    }


async def check_quest_completable(session: AsyncSession, character_id: int, quest_id: int) -> Optional[dict]:
    """
    Check if all objectives are completed for a quest.
    Returns dict with character_quest info or None.
    """
    cq_result = await session.execute(
        text("""
            SELECT cq.id FROM character_quests cq
            WHERE cq.character_id = :cid AND cq.quest_id = :qid AND cq.status = 'active'
        """),
        {"cid": character_id, "qid": quest_id},
    )
    cq_row = cq_result.fetchone()
    if not cq_row:
        return None
    cq_id = cq_row[0]

    # Check if all objectives are completed
    incomplete = await session.execute(
        text("""
            SELECT COUNT(*) FROM character_quest_progress
            WHERE character_quest_id = :cqid AND is_completed = 0
        """),
        {"cqid": cq_id},
    )
    incomplete_count = incomplete.fetchone()[0]

    return {
        "character_quest_id": cq_id,
        "all_completed": incomplete_count == 0,
    }


async def complete_quest_record(session: AsyncSession, character_quest_id: int) -> None:
    """Mark a character_quest as completed."""
    await session.execute(
        text("""
            UPDATE character_quests
            SET status = 'completed', completed_at = NOW()
            WHERE id = :cqid
        """),
        {"cqid": character_quest_id},
    )
    await session.commit()


async def abandon_quest(session: AsyncSession, character_id: int, quest_id: int) -> bool:
    """Abandon a quest. Returns True if found and abandoned."""
    result = await session.execute(
        text("""
            UPDATE character_quests
            SET status = 'abandoned'
            WHERE character_id = :cid AND quest_id = :qid AND status = 'active'
        """),
        {"cid": character_id, "qid": quest_id},
    )
    await session.commit()
    return result.rowcount > 0


async def add_experience(session: AsyncSession, character_id: int, amount: int) -> None:
    """Add experience to a character via direct SQL on shared DB."""
    await session.execute(
        text("""
            UPDATE characters
            SET experience = experience + :amount
            WHERE id = :cid
        """),
        {"cid": character_id, "amount": amount},
    )
    await session.commit()


# -------------------------------
#   ARCHIVE CATEGORIES
# -------------------------------
async def get_all_categories(session: AsyncSession):
    """Get all archive categories ordered by sort_order, with article_count."""
    # Subquery for article count per category
    count_subq = (
        select(
            ArchiveArticleCategory.category_id,
            sa_func.count(ArchiveArticleCategory.article_id).label("article_count"),
        )
        .group_by(ArchiveArticleCategory.category_id)
        .subquery()
    )

    stmt = (
        select(ArchiveCategory, sa_func.coalesce(count_subq.c.article_count, 0).label("article_count"))
        .outerjoin(count_subq, ArchiveCategory.id == count_subq.c.category_id)
        .order_by(ArchiveCategory.sort_order.asc(), ArchiveCategory.id.asc())
    )
    result = await session.execute(stmt)
    rows = result.all()

    categories = []
    for row in rows:
        cat = row[0]
        cat.article_count = row[1]
        categories.append(cat)
    return categories


async def create_category(session: AsyncSession, data: ArchiveCategoryCreate) -> ArchiveCategory:
    """Create a new archive category. Raises 409 if slug already exists."""
    existing = await session.execute(
        select(ArchiveCategory).where(ArchiveCategory.slug == data.slug)
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Категория с таким slug уже существует")

    new_cat = ArchiveCategory(
        name=data.name,
        slug=data.slug,
        description=data.description,
        sort_order=data.sort_order,
    )
    session.add(new_cat)
    await session.commit()
    await session.refresh(new_cat)
    return new_cat


async def update_category(session: AsyncSession, category_id: int, data: ArchiveCategoryUpdate) -> ArchiveCategory:
    """Partial update of archive category. Raises 404 if not found, 409 if slug duplicate."""
    result = await session.execute(
        select(ArchiveCategory).where(ArchiveCategory.id == category_id)
    )
    db_cat = result.scalars().first()
    if not db_cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    update_data = data.dict(exclude_unset=True)

    # Validate slug uniqueness if slug is being changed
    if "slug" in update_data and update_data["slug"] != db_cat.slug:
        dup = await session.execute(
            select(ArchiveCategory).where(ArchiveCategory.slug == update_data["slug"])
        )
        if dup.scalars().first():
            raise HTTPException(status_code=409, detail="Категория с таким slug уже существует")

    for field, value in update_data.items():
        setattr(db_cat, field, value)

    await session.commit()
    await session.refresh(db_cat)
    return db_cat


async def delete_category(session: AsyncSession, category_id: int) -> None:
    """Delete archive category by ID. Raises 404 if not found. CASCADE handles join table."""
    result = await session.execute(
        select(ArchiveCategory).where(ArchiveCategory.id == category_id)
    )
    db_cat = result.scalars().first()
    if not db_cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    await session.execute(
        delete(ArchiveCategory).where(ArchiveCategory.id == category_id)
    )
    await session.commit()


async def reorder_categories(session: AsyncSession, items: list) -> None:
    """Bulk update sort_order for archive categories. items = [{id, sort_order}, ...]."""
    for item in items:
        result = await session.execute(
            select(ArchiveCategory).where(ArchiveCategory.id == item["id"])
        )
        db_cat = result.scalars().first()
        if db_cat:
            db_cat.sort_order = item["sort_order"]
    await session.commit()


# -------------------------------
#   ARCHIVE ARTICLES
# -------------------------------
async def get_articles(
    session: AsyncSession,
    category_slug: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
):
    """List articles with pagination, optional category filter and search.
    Returns (articles_list, total_count). Does not load content field."""
    # Base query — select specific columns to avoid loading content
    base_stmt = select(ArchiveArticle).options(selectinload(ArchiveArticle.categories))

    # Category filter via join table
    if category_slug:
        base_stmt = base_stmt.join(
            ArchiveArticleCategory,
            ArchiveArticle.id == ArchiveArticleCategory.article_id,
        ).join(
            ArchiveCategory,
            ArchiveArticleCategory.category_id == ArchiveCategory.id,
        ).where(ArchiveCategory.slug == category_slug)

    # Search filter
    if search:
        base_stmt = base_stmt.where(ArchiveArticle.title.like(f"%{search}%"))

    # Count total
    count_stmt = select(sa_func.count()).select_from(base_stmt.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # Paginate and order
    offset = (page - 1) * per_page
    data_stmt = base_stmt.order_by(ArchiveArticle.created_at.desc()).offset(offset).limit(per_page)
    result = await session.execute(data_stmt)
    articles = result.scalars().unique().all()

    # Strip content from list results to keep payloads lightweight
    for article in articles:
        article.content = None

    return articles, total


async def get_article_by_slug(session: AsyncSession, slug: str) -> ArchiveArticle:
    """Get single article by slug with full content and categories. Raises 404 if not found."""
    result = await session.execute(
        select(ArchiveArticle)
        .options(selectinload(ArchiveArticle.categories))
        .where(ArchiveArticle.slug == slug)
    )
    article = result.scalars().first()
    if not article:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    return article


async def get_article_preview(session: AsyncSession, slug: str):
    """Get minimal article data for hover preview (id, title, slug, summary, cover_image_url)."""
    result = await session.execute(
        select(
            ArchiveArticle.id,
            ArchiveArticle.title,
            ArchiveArticle.slug,
            ArchiveArticle.summary,
            ArchiveArticle.cover_image_url,
        ).where(ArchiveArticle.slug == slug)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    return {
        "id": row[0],
        "title": row[1],
        "slug": row[2],
        "summary": row[3],
        "cover_image_url": row[4],
    }


async def create_article(session: AsyncSession, data: ArchiveArticleCreate, user_id: int) -> ArchiveArticle:
    """Create article with category assignments. Raises 409 if slug duplicate."""
    existing = await session.execute(
        select(ArchiveArticle).where(ArchiveArticle.slug == data.slug)
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Статья с таким slug уже существует")

    new_article = ArchiveArticle(
        title=data.title,
        slug=data.slug,
        content=data.content,
        summary=data.summary,
        cover_image_url=data.cover_image_url,
        cover_text_color=data.cover_text_color or "#FFFFFF",
        is_featured=data.is_featured,
        featured_sort_order=data.featured_sort_order,
        created_by_user_id=user_id,
    )
    session.add(new_article)
    await session.flush()  # Get the ID before creating join entries

    # Create category assignments
    for cat_id in data.category_ids:
        session.add(ArchiveArticleCategory(article_id=new_article.id, category_id=cat_id))

    await session.commit()
    await session.refresh(new_article)

    # Eagerly load categories for the response
    result = await session.execute(
        select(ArchiveArticle)
        .options(selectinload(ArchiveArticle.categories))
        .where(ArchiveArticle.id == new_article.id)
    )
    return result.scalars().first()


async def update_article(session: AsyncSession, article_id: int, data: ArchiveArticleUpdate) -> ArchiveArticle:
    """Partial update of archive article. Handles category_ids reassignment. Raises 404/409."""
    result = await session.execute(
        select(ArchiveArticle).where(ArchiveArticle.id == article_id)
    )
    db_article = result.scalars().first()
    if not db_article:
        raise HTTPException(status_code=404, detail="Статья не найдена")

    update_data = data.dict(exclude_unset=True)

    # Validate slug uniqueness if slug is being changed
    if "slug" in update_data and update_data["slug"] != db_article.slug:
        dup = await session.execute(
            select(ArchiveArticle).where(ArchiveArticle.slug == update_data["slug"])
        )
        if dup.scalars().first():
            raise HTTPException(status_code=409, detail="Статья с таким slug уже существует")

    # Handle category_ids separately
    category_ids = update_data.pop("category_ids", None)
    if category_ids is not None:
        # Delete existing join entries
        await session.execute(
            delete(ArchiveArticleCategory).where(ArchiveArticleCategory.article_id == article_id)
        )
        # Create new join entries
        for cat_id in category_ids:
            session.add(ArchiveArticleCategory(article_id=article_id, category_id=cat_id))

    # Update scalar fields
    for field, value in update_data.items():
        setattr(db_article, field, value)

    await session.commit()
    await session.refresh(db_article)

    # Eagerly load categories for the response
    result = await session.execute(
        select(ArchiveArticle)
        .options(selectinload(ArchiveArticle.categories))
        .where(ArchiveArticle.id == db_article.id)
    )
    return result.scalars().first()


async def delete_article(session: AsyncSession, article_id: int) -> None:
    """Delete archive article by ID. Raises 404 if not found. CASCADE handles join table."""
    result = await session.execute(
        select(ArchiveArticle).where(ArchiveArticle.id == article_id)
    )
    db_article = result.scalars().first()
    if not db_article:
        raise HTTPException(status_code=404, detail="Статья не найдена")

    await session.execute(
        delete(ArchiveArticle).where(ArchiveArticle.id == article_id)
    )
    await session.commit()


async def get_featured_articles(session: AsyncSession):
    """Get articles where is_featured=True, ordered by featured_sort_order. No content loaded."""
    result = await session.execute(
        select(ArchiveArticle)
        .options(selectinload(ArchiveArticle.categories))
        .where(ArchiveArticle.is_featured == True)
        .order_by(ArchiveArticle.featured_sort_order.asc(), ArchiveArticle.id.asc())
    )
    articles = result.scalars().unique().all()

    # Strip content for list response
    for article in articles:
        article.content = None

    return articles


# -------------------------------
#   TRANSITION ARROWS
# -------------------------------
async def create_transition_arrow(
    session: AsyncSession,
    data: TransitionArrowCreate,
) -> dict:
    """
    Create a transition arrow from region_id to target_region_id.
    Auto-creates a paired arrow in the target region pointing back.
    Returns both arrows with target_region_name populated.
    """
    # Validate regions exist and are different
    if data.region_id == data.target_region_id:
        raise HTTPException(status_code=400, detail="region_id and target_region_id must be different")

    region_result = await session.execute(
        select(Region).where(Region.id == data.region_id)
    )
    region = region_result.scalars().first()
    if not region:
        raise HTTPException(status_code=404, detail=f"Region {data.region_id} not found")

    target_result = await session.execute(
        select(Region).where(Region.id == data.target_region_id)
    )
    target_region = target_result.scalars().first()
    if not target_region:
        raise HTTPException(status_code=404, detail=f"Target region {data.target_region_id} not found")

    # Validate coordinates if provided
    if data.x is not None and not (0 <= data.x <= 100):
        raise HTTPException(status_code=400, detail="x must be between 0 and 100")
    if data.y is not None and not (0 <= data.y <= 100):
        raise HTTPException(status_code=400, detail="y must be between 0 and 100")

    # Create the primary arrow
    arrow = RegionTransitionArrow(
        region_id=data.region_id,
        target_region_id=data.target_region_id,
        x=data.x,
        y=data.y,
        label=data.label,
        rotation=data.rotation or 0,
    )
    session.add(arrow)
    await session.flush()

    # Create the paired arrow (in the target region, pointing back)
    paired_arrow = RegionTransitionArrow(
        region_id=data.target_region_id,
        target_region_id=data.region_id,
        x=None,
        y=None,
        label=None,
        rotation=0,
    )
    session.add(paired_arrow)
    await session.flush()

    # Link them together
    arrow.paired_arrow_id = paired_arrow.id
    paired_arrow.paired_arrow_id = arrow.id
    await session.commit()
    await session.refresh(arrow)
    await session.refresh(paired_arrow)

    return {
        "arrow": {
            "id": arrow.id,
            "region_id": arrow.region_id,
            "target_region_id": arrow.target_region_id,
            "target_region_name": target_region.name,
            "paired_arrow_id": arrow.paired_arrow_id,
            "x": arrow.x,
            "y": arrow.y,
            "label": arrow.label,
            "rotation": arrow.rotation,
        },
        "paired_arrow": {
            "id": paired_arrow.id,
            "region_id": paired_arrow.region_id,
            "target_region_id": paired_arrow.target_region_id,
            "target_region_name": region.name,
            "paired_arrow_id": paired_arrow.paired_arrow_id,
            "x": paired_arrow.x,
            "y": paired_arrow.y,
            "label": paired_arrow.label,
            "rotation": paired_arrow.rotation,
        },
    }


async def update_transition_arrow(
    session: AsyncSession,
    arrow_id: int,
    data: TransitionArrowUpdate,
) -> dict:
    """Update arrow position and/or label."""
    result = await session.execute(
        select(RegionTransitionArrow).where(RegionTransitionArrow.id == arrow_id)
    )
    arrow = result.scalars().first()
    if not arrow:
        raise HTTPException(status_code=404, detail="Arrow not found")

    update_data = data.dict(exclude_unset=True)

    # Validate coordinates if provided
    if "x" in update_data and update_data["x"] is not None:
        if not (0 <= update_data["x"] <= 100):
            raise HTTPException(status_code=400, detail="x must be between 0 and 100")
    if "y" in update_data and update_data["y"] is not None:
        if not (0 <= update_data["y"] <= 100):
            raise HTTPException(status_code=400, detail="y must be between 0 and 100")

    for key, value in update_data.items():
        setattr(arrow, key, value)

    await session.commit()
    await session.refresh(arrow)

    # Get target region name
    target_result = await session.execute(
        select(Region.name).where(Region.id == arrow.target_region_id)
    )
    target_name = target_result.scalar()

    return {
        "id": arrow.id,
        "region_id": arrow.region_id,
        "target_region_id": arrow.target_region_id,
        "target_region_name": target_name,
        "paired_arrow_id": arrow.paired_arrow_id,
        "x": arrow.x,
        "y": arrow.y,
        "label": arrow.label,
        "rotation": arrow.rotation,
    }


async def delete_transition_arrow(
    session: AsyncSession,
    arrow_id: int,
) -> dict:
    """
    Delete an arrow and its paired arrow (if exists).
    Nullifies paired_arrow_id references first to avoid FK constraint issues.
    """
    result = await session.execute(
        select(RegionTransitionArrow).where(RegionTransitionArrow.id == arrow_id)
    )
    arrow = result.scalars().first()
    if not arrow:
        raise HTTPException(status_code=404, detail="Arrow not found")

    deleted_ids = [arrow.id]
    paired_arrow = None

    if arrow.paired_arrow_id:
        paired_result = await session.execute(
            select(RegionTransitionArrow).where(RegionTransitionArrow.id == arrow.paired_arrow_id)
        )
        paired_arrow = paired_result.scalars().first()

    # Clean up cross-region auto-neighbors BEFORE deleting arrows
    # (ArrowNeighbors cascade-delete with arrows, so we must read them first)
    await cleanup_cross_region_neighbors_for_arrow(session, arrow_id)

    # Nullify paired_arrow_id references to avoid FK issues during deletion
    if paired_arrow:
        deleted_ids.append(paired_arrow.id)
        paired_arrow.paired_arrow_id = None
    arrow.paired_arrow_id = None
    await session.flush()

    # Delete both arrows (ArrowNeighbor rows cascade-deleted by FK)
    if paired_arrow:
        await session.delete(paired_arrow)
    await session.delete(arrow)
    await session.commit()

    return {"status": "deleted", "deleted_ids": deleted_ids}


async def sync_cross_region_neighbors(session: AsyncSession, arrow_id: int) -> None:
    """
    Recalculate all cross-region LocationNeighbors for a given arrow pair.
    Creates bidirectional is_auto_arrow=True LocationNeighbor rows
    for each (locA, locB) pair where locA connects to this arrow
    and locB connects to the paired arrow.
    """
    from sqlalchemy import or_, and_

    # Load arrow
    arrow_result = await session.execute(
        select(RegionTransitionArrow).where(RegionTransitionArrow.id == arrow_id)
    )
    arrow = arrow_result.scalars().first()
    if not arrow or not arrow.paired_arrow_id:
        return

    paired_arrow_id = arrow.paired_arrow_id

    # Get ArrowNeighbors for this arrow
    local_result = await session.execute(
        select(ArrowNeighbor).where(ArrowNeighbor.arrow_id == arrow_id)
    )
    local_ans = local_result.scalars().all()

    # Get ArrowNeighbors for paired arrow
    remote_result = await session.execute(
        select(ArrowNeighbor).where(ArrowNeighbor.arrow_id == paired_arrow_id)
    )
    remote_ans = remote_result.scalars().all()

    if not local_ans or not remote_ans:
        return

    local_location_ids = [an.location_id for an in local_ans]
    remote_location_ids = [an.location_id for an in remote_ans]

    # Delete existing auto-arrow LocationNeighbors between these location sets
    await session.execute(
        delete(LocationNeighbor).where(
            and_(
                LocationNeighbor.is_auto_arrow == True,
                or_(
                    and_(
                        LocationNeighbor.location_id.in_(local_location_ids),
                        LocationNeighbor.neighbor_id.in_(remote_location_ids),
                    ),
                    and_(
                        LocationNeighbor.location_id.in_(remote_location_ids),
                        LocationNeighbor.neighbor_id.in_(local_location_ids),
                    ),
                )
            )
        )
    )

    # Create N x M bidirectional LocationNeighbors
    for local_an in local_ans:
        for remote_an in remote_ans:
            total_cost = local_an.energy_cost + remote_an.energy_cost
            # Forward: local -> remote
            session.add(LocationNeighbor(
                location_id=local_an.location_id,
                neighbor_id=remote_an.location_id,
                energy_cost=total_cost,
                path_data=None,
                is_auto_arrow=True,
            ))
            # Reverse: remote -> local
            session.add(LocationNeighbor(
                location_id=remote_an.location_id,
                neighbor_id=local_an.location_id,
                energy_cost=total_cost,
                path_data=None,
                is_auto_arrow=True,
            ))

    await session.flush()


async def cleanup_cross_region_neighbors_for_arrow(session: AsyncSession, arrow_id: int) -> None:
    """
    Delete all auto-arrow LocationNeighbors linked to a specific arrow pair.
    Must be called BEFORE deleting arrows/ArrowNeighbors (since we need to read them).
    """
    from sqlalchemy import or_, and_

    # Load arrow
    arrow_result = await session.execute(
        select(RegionTransitionArrow).where(RegionTransitionArrow.id == arrow_id)
    )
    arrow = arrow_result.scalars().first()
    if not arrow or not arrow.paired_arrow_id:
        return

    paired_arrow_id = arrow.paired_arrow_id

    # Get location_ids from ArrowNeighbors of this arrow
    local_result = await session.execute(
        select(ArrowNeighbor.location_id).where(ArrowNeighbor.arrow_id == arrow_id)
    )
    local_ids = [row[0] for row in local_result.all()]

    # Get location_ids from ArrowNeighbors of paired arrow
    remote_result = await session.execute(
        select(ArrowNeighbor.location_id).where(ArrowNeighbor.arrow_id == paired_arrow_id)
    )
    remote_ids = [row[0] for row in remote_result.all()]

    if not local_ids or not remote_ids:
        return

    # Delete auto-arrow LocationNeighbors between these location sets
    await session.execute(
        delete(LocationNeighbor).where(
            and_(
                LocationNeighbor.is_auto_arrow == True,
                or_(
                    and_(
                        LocationNeighbor.location_id.in_(local_ids),
                        LocationNeighbor.neighbor_id.in_(remote_ids),
                    ),
                    and_(
                        LocationNeighbor.location_id.in_(remote_ids),
                        LocationNeighbor.neighbor_id.in_(local_ids),
                    ),
                )
            )
        )
    )

    await session.flush()


async def create_arrow_neighbor(
    session: AsyncSession,
    arrow_id: int,
    data: ArrowNeighborCreate,
) -> dict:
    """
    Create or update a path between a location and an arrow.
    If a row with the same location_id + arrow_id exists, update it.
    """
    # Validate arrow exists
    arrow_result = await session.execute(
        select(RegionTransitionArrow).where(RegionTransitionArrow.id == arrow_id)
    )
    arrow = arrow_result.scalars().first()
    if not arrow:
        raise HTTPException(status_code=404, detail="Arrow not found")

    # Validate location exists
    loc_result = await session.execute(
        select(Location).where(Location.id == data.location_id)
    )
    if not loc_result.scalars().first():
        raise HTTPException(status_code=404, detail=f"Location {data.location_id} not found")

    # Validate path_data limits
    if data.path_data and len(data.path_data) > 50:
        raise HTTPException(status_code=400, detail="path_data exceeds maximum of 50 waypoints")

    # Check for existing row (upsert)
    existing_result = await session.execute(
        select(ArrowNeighbor).where(
            ArrowNeighbor.location_id == data.location_id,
            ArrowNeighbor.arrow_id == arrow_id,
        )
    )
    existing = existing_result.scalars().first()

    path_data_raw = [{"x": p.x, "y": p.y} for p in data.path_data] if data.path_data else None

    if existing:
        existing.energy_cost = data.energy_cost
        existing.path_data = path_data_raw
        await session.flush()
        await sync_cross_region_neighbors(session, arrow_id)
        await session.commit()
        await session.refresh(existing)
        return {
            "id": existing.id,
            "location_id": existing.location_id,
            "arrow_id": existing.arrow_id,
            "energy_cost": existing.energy_cost,
            "path_data": existing.path_data,
        }

    neighbor = ArrowNeighbor(
        location_id=data.location_id,
        arrow_id=arrow_id,
        energy_cost=data.energy_cost,
        path_data=path_data_raw,
    )
    session.add(neighbor)
    await session.flush()
    await sync_cross_region_neighbors(session, arrow_id)
    await session.commit()
    await session.refresh(neighbor)

    return {
        "id": neighbor.id,
        "location_id": neighbor.location_id,
        "arrow_id": neighbor.arrow_id,
        "energy_cost": neighbor.energy_cost,
        "path_data": neighbor.path_data,
    }


async def update_arrow_neighbor_path(
    session: AsyncSession,
    location_id: int,
    arrow_id: int,
    path_data: list,
) -> dict:
    """Update the path_data on an existing arrow neighbor."""
    result = await session.execute(
        select(ArrowNeighbor).where(
            ArrowNeighbor.location_id == location_id,
            ArrowNeighbor.arrow_id == arrow_id,
        )
    )
    neighbor = result.scalars().first()
    if not neighbor:
        raise HTTPException(status_code=404, detail="Arrow neighbor not found")

    if path_data and len(path_data) > 50:
        raise HTTPException(status_code=400, detail="path_data exceeds maximum of 50 waypoints")

    neighbor.path_data = path_data
    await session.commit()
    await session.refresh(neighbor)

    return {
        "location_id": neighbor.location_id,
        "arrow_id": neighbor.arrow_id,
        "energy_cost": neighbor.energy_cost,
        "path_data": neighbor.path_data,
    }


async def delete_arrow_neighbor(
    session: AsyncSession,
    location_id: int,
    arrow_id: int,
) -> dict:
    """Delete an arrow neighbor path and clean up cross-region auto-neighbors."""
    from sqlalchemy import or_, and_

    result = await session.execute(
        select(ArrowNeighbor).where(
            ArrowNeighbor.location_id == location_id,
            ArrowNeighbor.arrow_id == arrow_id,
        )
    )
    neighbor = result.scalars().first()
    if not neighbor:
        raise HTTPException(status_code=404, detail="Arrow neighbor not found")

    # Clean up cross-region neighbors for this specific location before deleting
    arrow_result = await session.execute(
        select(RegionTransitionArrow).where(RegionTransitionArrow.id == arrow_id)
    )
    arrow = arrow_result.scalars().first()
    if arrow and arrow.paired_arrow_id:
        remote_result = await session.execute(
            select(ArrowNeighbor.location_id).where(
                ArrowNeighbor.arrow_id == arrow.paired_arrow_id
            )
        )
        remote_ids = [row[0] for row in remote_result.all()]
        if remote_ids:
            await session.execute(
                delete(LocationNeighbor).where(
                    and_(
                        LocationNeighbor.is_auto_arrow == True,
                        or_(
                            and_(
                                LocationNeighbor.location_id == location_id,
                                LocationNeighbor.neighbor_id.in_(remote_ids),
                            ),
                            and_(
                                LocationNeighbor.location_id.in_(remote_ids),
                                LocationNeighbor.neighbor_id == location_id,
                            ),
                        )
                    )
                )
            )

    await session.delete(neighbor)
    await session.commit()

    return {"status": "deleted"}
