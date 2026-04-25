import json
import logging
import random
import re
import math
import httpx
from datetime import datetime, timedelta, timezone
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
    RegionTransitionArrow, ArrowNeighbor, FloatingStructure,
    GatheringNode, GatheringSession,
)
from schemas import (
    DistrictCreate, LocationCreate, PostCreate, LocationNeighborCreate,
    GameRuleCreate, GameRuleUpdate, GameRuleReorderItem,
    AreaCreate, AreaUpdate, ClickableZoneCreate, ClickableZoneUpdate,
    ArchiveCategoryCreate, ArchiveCategoryUpdate,
    ArchiveArticleCreate, ArchiveArticleUpdate,
    TransitionArrowCreate, TransitionArrowUpdate, ArrowNeighborCreate,
    GatheringNodeAdminCreate, GatheringNodeAdminUpdate,
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
            "no_quick_move": getattr(location, 'no_quick_move', False),
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
            "no_quick_move": getattr(location, 'no_quick_move', False),
            "description": location.description,
            "parent_id": location.parent_id,
            "children": []
        }

# -------------------------------
#   LOOKUP
# -------------------------------
async def get_locations_lookup(session: AsyncSession, q: Optional[str] = None) -> List[dict]:
    from sqlalchemy import or_
    stmt = select(Location)
    if q is not None:
        q_stripped = q.strip()
        if q_stripped:
            if q_stripped.isdigit():
                stmt = stmt.where(
                    or_(
                        Location.id == int(q_stripped),
                        sa_func.lower(Location.name).like(f"%{q_stripped.lower()}%"),
                    )
                )
            else:
                stmt = stmt.where(
                    sa_func.lower(Location.name).like(f"%{q_stripped.lower()}%")
                )
    result = await session.execute(stmt)
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
                       emblem_url: Optional[str] = None,
                       is_hidden: bool = False) -> Country:
    new_country = Country(
        name=name,
        description=description,
        leader_id=leader_id,
        map_image_url=map_image_url,
        emblem_url=emblem_url,
        area_id=area_id,
        x=x,
        y=y,
        is_hidden=is_hidden,
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
        "no_quick_move": getattr(loc, 'no_quick_move', False),
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
        location_dict['no_quick_move'] = location_dict.get('no_quick_move', False)
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
        "no_quick_move": getattr(loc, 'no_quick_move', False),
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
                "is_hidden": country.is_hidden,
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
            "is_hidden": country.is_hidden,
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

    # 8. (FEAT-128 task #11) Lazy-restore depleted gathering nodes whose
    #    24h cooldown has elapsed, then build the surfaced gathering_nodes
    #    payload. The lazy-finalize step happens in the route handler before
    #    this function is invoked so the active-sessions list reflects the
    #    just-finalized state.
    try:
        await lazy_restore_depleted_nodes(session, location_id)
        gathering_nodes = await fetch_gathering_nodes_with_active_sessions(
            session, location_id, players_at_location=players,
        )
        # Commit the lazy-restore mutations (UPDATE only — idempotent and
        # safe to commit independently from the rest of the read).
        await session.commit()
    except Exception as exc:
        logger.warning(
            "Failed to surface gathering_nodes for location %s: %s",
            location_id, exc,
        )
        try:
            await session.rollback()
        except Exception:
            pass
        gathering_nodes = []

    return {
        "id": loc.id,
        "name": loc.name,
        "type": loc.type,
        "parent_id": loc.parent_id,
        "description": loc.description,
        "image_url": loc.image_url,
        "recommended_level": loc.recommended_level,
        "quick_travel_marker": loc.quick_travel_marker,
        "no_quick_move": getattr(loc, 'no_quick_move', False),
        "marker_type": loc.marker_type,
        "district_id": loc.district_id,
        "region_id": loc.region_id,
        "is_favorited": favorited,
        "neighbors": detailed_neighbors,
        "players": players,
        "npcs": npcs,
        "posts": detailed_posts,
        "loot": loot_items,
        "gathering_nodes": gathering_nodes,
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
            if not c.is_hidden
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

    countries_result = await session.execute(
        select(Country).where(Country.is_hidden == False)  # noqa: E712
    )
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


async def auto_progress_quests(
    session: AsyncSession,
    character_id: int,
    event_type: str,
    increment: int = 1,
    target_id: int | None = None,
    meta: dict | None = None,
) -> list[dict]:
    """
    Automatically update quest progress for a character based on a game event.

    Finds all active quest objectives matching the event_type (as objective_type)
    and optionally target_id, then increments their progress.

    Event types map directly to objective_type values:
      - kill_mob          (target_id = mob_template_id)
      - kill_mob_any      (no target_id)
      - kill_mob_tier     (meta.tier = 'normal'/'elite'/'boss')
      - defeat_npc        (target_id = character_id of NPC)
      - defeat_any        (no target_id)
      - visit_location    (target_id = location_id)
      - write_posts       (no target_id)
      - write_post_in_location (target_id = location_id)
      - write_chars       (increment = char_count)
      - write_chars_in_location (target_id = location_id, increment = char_count)
      - talk_to           (target_id = npc_id)
      - collect           (target_id = item_id)
      - complete_quest    (target_id = quest_id)

    Returns list of updated objectives.
    """
    meta = meta or {}

    # Build query to find matching active objectives
    # Join: character_quests (active) -> quest_objectives (by type) -> character_quest_progress (not completed)
    base_query = """
        SELECT cqp.id AS progress_id,
               cqp.character_quest_id,
               qo.id AS objective_id,
               qo.objective_type,
               qo.target_id,
               qo.target_count,
               cqp.current_count
        FROM character_quest_progress cqp
        JOIN character_quests cq ON cq.id = cqp.character_quest_id
        JOIN quest_objectives qo ON qo.id = cqp.objective_id
        WHERE cq.character_id = :cid
          AND cq.status = 'active'
          AND cqp.is_completed = 0
    """
    params: dict = {"cid": character_id}

    # Determine which objective_types to match
    # Some events can match multiple objective_types
    matching_types: list[str] = []

    if event_type == "kill_mob":
        matching_types = ["kill_mob", "kill_mob_any", "defeat_any"]
        # Also check kill_mob_tier if we have tier info
        if meta.get("tier"):
            matching_types.append("kill_mob_tier")
    elif event_type == "defeat_npc":
        matching_types = ["defeat_npc", "defeat_any"]
    elif event_type in (
        "visit_location", "write_posts", "write_post_in_location",
        "write_chars", "write_chars_in_location", "talk_to",
        "collect", "complete_quest", "kill_mob_any", "defeat_any",
    ):
        matching_types = [event_type]
    else:
        return []

    # Filter by objective_type
    type_placeholders = ", ".join(f":ot{i}" for i in range(len(matching_types)))
    base_query += f" AND qo.objective_type IN ({type_placeholders})"
    for i, t in enumerate(matching_types):
        params[f"ot{i}"] = t

    rows = (await session.execute(text(base_query), params)).fetchall()

    if not rows:
        return []

    updated = []

    for row in rows:
        progress_id = row[0]
        objective_type = row[3]
        obj_target_id = row[4]
        obj_target_count = row[5]
        current_count = row[6]
        objective_id = row[2]

        # Check target_id matching for types that require it
        if objective_type == "kill_mob":
            if obj_target_id is not None and target_id != obj_target_id:
                continue
        elif objective_type == "kill_mob_tier":
            # target_id in DB stores tier as int mapping or string;
            # we compare meta.tier with target_id
            tier = meta.get("tier")
            tier_map = {"normal": 1, "elite": 2, "boss": 3}
            if obj_target_id is not None and tier_map.get(tier) != obj_target_id:
                continue
        elif objective_type == "defeat_npc":
            if obj_target_id is not None and target_id != obj_target_id:
                continue
        elif objective_type in ("visit_location", "write_post_in_location", "write_chars_in_location"):
            if obj_target_id is not None and target_id != obj_target_id:
                continue
        elif objective_type == "talk_to":
            if obj_target_id is not None and target_id != obj_target_id:
                continue
        elif objective_type == "collect":
            if obj_target_id is not None and target_id != obj_target_id:
                continue
        elif objective_type == "complete_quest":
            if obj_target_id is not None and target_id != obj_target_id:
                continue
        # kill_mob_any, defeat_any, write_posts, write_chars — no target check

        # Update progress
        await session.execute(
            text("""
                UPDATE character_quest_progress
                SET current_count = LEAST(current_count + :inc, :target),
                    is_completed = CASE WHEN current_count + :inc >= :target THEN 1 ELSE 0 END
                WHERE id = :pid
            """),
            {"inc": increment, "target": obj_target_count, "pid": progress_id},
        )

        new_count = min(current_count + increment, obj_target_count)
        updated.append({
            "objective_id": objective_id,
            "objective_type": objective_type,
            "current_count": new_count,
            "target_count": obj_target_count,
            "is_completed": new_count >= obj_target_count,
        })

    if updated:
        await session.commit()

    return updated


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
    """Add passive experience to a character via direct SQL on shared DB."""
    await session.execute(
        text("""
            UPDATE character_attributes
            SET passive_experience = passive_experience + :amount
            WHERE character_id = :cid
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


# -------------------------------
#   FLOATING STRUCTURES (FEAT-123)
# -------------------------------
async def _ensure_district_exists(session: AsyncSession, district_id: Optional[int]) -> None:
    if district_id is None:
        return
    result = await session.execute(select(District).where(District.id == district_id))
    if result.scalars().first() is None:
        raise HTTPException(
            status_code=404,
            detail=f"Район с id={district_id} не найден",
        )


async def list_floating_structures(
    session: AsyncSession, area_id: Optional[int] = None
) -> List[FloatingStructure]:
    query = select(FloatingStructure)
    if area_id is not None:
        query = query.where(FloatingStructure.area_id == area_id)
    result = await session.execute(query.order_by(FloatingStructure.id.asc()))
    return result.scalars().all()


async def get_floating_structure(
    session: AsyncSession, structure_id: int
) -> Optional[FloatingStructure]:
    result = await session.execute(
        select(FloatingStructure).where(FloatingStructure.id == structure_id)
    )
    return result.scalars().first()


async def create_floating_structure(session: AsyncSession, data) -> FloatingStructure:
    await _ensure_district_exists(session, data.internal_district_id)
    obj = FloatingStructure(
        name=data.name,
        description=data.description,
        icon_url=data.icon_url,
        route_json=data.route_json,
        speed=data.speed,
        started_at=data.started_at,
        internal_district_id=data.internal_district_id,
        area_id=data.area_id,
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


async def update_floating_structure(
    session: AsyncSession, structure_id: int, data
) -> FloatingStructure:
    obj = await get_floating_structure(session, structure_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Плавающая структура не найдена")

    payload = data.dict(exclude_unset=True)
    if 'internal_district_id' in payload:
        await _ensure_district_exists(session, payload['internal_district_id'])

    for field, value in payload.items():
        setattr(obj, field, value)

    await session.commit()
    await session.refresh(obj)
    return obj


async def delete_floating_structure(session: AsyncSession, structure_id: int) -> None:
    obj = await get_floating_structure(session, structure_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Плавающая структура не найдена")
    await session.delete(obj)
    await session.commit()


# -----------------------------------------------------------------------------
# GATHERING NODE — ADMIN CRUD (FEAT-128)
# -----------------------------------------------------------------------------
async def _ensure_location_exists(session: AsyncSession, location_id: int) -> None:
    """Raise 404 if Locations.id does not exist."""
    result = await session.execute(
        select(Location.id).where(Location.id == location_id)
    )
    if result.scalars().first() is None:
        raise HTTPException(status_code=404, detail="Локация не найдена")


async def _ensure_item_exists(session: AsyncSession, item_id: int) -> None:
    """Cross-service existence check on the shared `items` table.

    The `items` table is owned by inventory-service. We use a raw SELECT
    (no FK by codebase convention 2.5#6).
    """
    result = await session.execute(
        text("SELECT id FROM items WHERE id = :iid"),
        {"iid": item_id},
    )
    if result.fetchone() is None:
        raise HTTPException(status_code=422, detail="Предмет не найден")


async def _fetch_item_brief(
    session: AsyncSession, item_ids: List[int]
) -> Dict[int, Dict[str, Optional[str]]]:
    """Batch-fetch name/image/item_type from items table for a list of ids."""
    if not item_ids:
        return {}
    # SQLAlchemy text() with `expanding` bindparam for IN clause
    from sqlalchemy import bindparam
    stmt = text(
        "SELECT id, name, image, item_type FROM items WHERE id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    result = await session.execute(stmt, {"ids": list(item_ids)})
    out: Dict[int, Dict[str, Optional[str]]] = {}
    for row in result.fetchall():
        out[int(row[0])] = {
            "name": row[1],
            "image": row[2],
            "item_type": row[3],
        }
    return out


def _serialize_gathering_node(
    node: GatheringNode, item_brief: Optional[Dict[str, Optional[str]]] = None
) -> dict:
    """Convert a GatheringNode ORM row + optional item brief into a dict suitable
    for `GatheringNodeAdmin` response (works with `orm_mode`-style validation
    when wrapped via `parse_obj`)."""
    return {
        "id": node.id,
        "location_id": node.location_id,
        "node_name": node.node_name,
        "category": node.category,
        "result_item_id": node.result_item_id,
        "result_quantity_per_gather": node.result_quantity_per_gather,
        "stamina_per_gather": node.stamina_per_gather,
        "daily_bank_max": node.daily_bank_max,
        "current_bank": node.current_bank,
        "allow_concurrent_gather": bool(node.allow_concurrent_gather),
        "depleted_at": _ensure_aware_utc(node.depleted_at),
        "restore_at": _ensure_aware_utc(node.restore_at),
        "is_enabled": bool(node.is_enabled),
        "created_at": _ensure_aware_utc(node.created_at),
        "updated_at": _ensure_aware_utc(node.updated_at),
        "result_item_name": (item_brief or {}).get("name"),
        "result_item_image": (item_brief or {}).get("image"),
        "result_item_type": (item_brief or {}).get("item_type"),
    }


async def list_gathering_nodes_admin(
    session: AsyncSession, location_id: int
) -> List[dict]:
    """List all gathering nodes for a location (admin view, includes disabled)."""
    await _ensure_location_exists(session, location_id)
    result = await session.execute(
        select(GatheringNode)
        .where(GatheringNode.location_id == location_id)
        .order_by(GatheringNode.id.asc())
    )
    nodes: List[GatheringNode] = list(result.scalars().all())
    item_ids = {n.result_item_id for n in nodes if n.result_item_id is not None}
    items_brief = await _fetch_item_brief(session, list(item_ids))
    return [_serialize_gathering_node(n, items_brief.get(n.result_item_id)) for n in nodes]


async def create_gathering_node_admin(
    session: AsyncSession, location_id: int, data: GatheringNodeAdminCreate
) -> dict:
    """Create a new gathering node for a location.

    - Verifies location exists (404 if not).
    - Verifies result_item_id exists in items table (422 with Russian message if not).
    - Initializes current_bank = daily_bank_max, depleted_at = NULL, restore_at = NULL.
    """
    await _ensure_location_exists(session, location_id)
    await _ensure_item_exists(session, data.result_item_id)

    node = GatheringNode(
        location_id=location_id,
        node_name=data.node_name,
        category=data.category,
        result_item_id=data.result_item_id,
        result_quantity_per_gather=data.result_quantity_per_gather,
        stamina_per_gather=data.stamina_per_gather,
        daily_bank_max=data.daily_bank_max,
        current_bank=data.daily_bank_max,
        allow_concurrent_gather=bool(data.allow_concurrent_gather),
        depleted_at=None,
        restore_at=None,
        is_enabled=bool(data.is_enabled),
    )
    session.add(node)
    await session.commit()
    await session.refresh(node)

    items_brief = await _fetch_item_brief(session, [node.result_item_id])
    return _serialize_gathering_node(node, items_brief.get(node.result_item_id))


async def update_gathering_node_admin(
    session: AsyncSession,
    node_id: int,
    data: GatheringNodeAdminUpdate,
) -> dict:
    """Partial-update a gathering node.

    Active sessions are NOT affected: their `effective_*` snapshots ensure
    they finish with the bonuses they started with.
    `current_bank` is left unchanged here — admins use the dedicated
    `restore` endpoint to top it up. If `daily_bank_max` is set lower than
    `current_bank`, we clamp `current_bank` down to the new max (per spec
    decision in 3.1.2).
    """
    result = await session.execute(
        select(GatheringNode).where(GatheringNode.id == node_id)
    )
    node: Optional[GatheringNode] = result.scalars().first()
    if node is None:
        raise HTTPException(status_code=404, detail="Нода добычи не найдена")

    payload = data.dict(exclude_unset=True)

    # Cross-service item existence check if result_item_id is being changed
    if "result_item_id" in payload and payload["result_item_id"] != node.result_item_id:
        await _ensure_item_exists(session, payload["result_item_id"])

    for field, value in payload.items():
        setattr(node, field, value)

    # Clamp current_bank if daily_bank_max was lowered below it.
    if "daily_bank_max" in payload and node.current_bank > node.daily_bank_max:
        node.current_bank = node.daily_bank_max

    await session.commit()
    await session.refresh(node)

    items_brief = await _fetch_item_brief(session, [node.result_item_id])
    return _serialize_gathering_node(node, items_brief.get(node.result_item_id))


async def delete_gathering_node_admin(
    session: AsyncSession, node_id: int
) -> None:
    """Delete a gathering node. FK ON DELETE CASCADE removes its sessions."""
    result = await session.execute(
        select(GatheringNode).where(GatheringNode.id == node_id)
    )
    node: Optional[GatheringNode] = result.scalars().first()
    if node is None:
        raise HTTPException(status_code=404, detail="Нода добычи не найдена")

    await session.execute(
        delete(GatheringNode).where(GatheringNode.id == node_id)
    )
    await session.commit()


async def restore_gathering_node_admin(
    session: AsyncSession, node_id: int
) -> dict:
    """Manual full restore: current_bank=daily_bank_max, clear depleted_at/restore_at."""
    result = await session.execute(
        select(GatheringNode).where(GatheringNode.id == node_id)
    )
    node: Optional[GatheringNode] = result.scalars().first()
    if node is None:
        raise HTTPException(status_code=404, detail="Нода добычи не найдена")

    node.current_bank = node.daily_bank_max
    node.depleted_at = None
    node.restore_at = None

    await session.commit()
    await session.refresh(node)

    items_brief = await _fetch_item_brief(session, [node.result_item_id])
    return _serialize_gathering_node(node, items_brief.get(node.result_item_id))
    await session.commit()


# -----------------------------------------------------------------------------
# GATHERING — CLIENT-FACING HELPERS (FEAT-128 task #11)
# -----------------------------------------------------------------------------
#
# This block adds the lazy-restore + lazy-finalize machinery surfaced from
# `GET /locations/{id}/client/details`. See FEAT-128 sections 3.5.2 and 3.6.
#
# Key invariants:
#   - Lazy-restore: when a node's `restore_at` is in the past, refill the bank
#     and clear depletion timestamps before returning data. Idempotent.
#   - Lazy-finalize: any active session whose `complete_at` is past is closed
#     (status -> completed | inventory_full) and the resource is awarded via
#     inventory-service. Bank is decremented atomically; on inventory_full we
#     re-credit the unused portion back to the bank.
#   - Both helpers use SELECT ... FOR UPDATE on the row level so a manual cancel
#     racing with the lazy finalize sees a consistent state.
#   - Cross-service inventory call is best-effort: a 5xx/timeout leaves the
#     session as `active` so the next poll retries. We never break the calling
#     `client/details` request because of an inventory hiccup.


def _ensure_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Treat naive timestamps coming from MySQL as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def lazy_restore_depleted_nodes(
    session: AsyncSession, location_id: int
) -> None:
    """Refill any depleted gathering nodes on the location whose restore_at
    has passed.

    Atomically sets `current_bank = daily_bank_max`, `depleted_at = NULL`,
    `restore_at = NULL`. Driven by a single UPDATE so it remains race-safe
    against concurrent gather-finalize hits.
    """
    await session.execute(
        text(
            "UPDATE gathering_nodes "
            "SET current_bank = daily_bank_max, "
            "    depleted_at = NULL, "
            "    restore_at = NULL "
            "WHERE location_id = :lid "
            "  AND restore_at IS NOT NULL "
            "  AND restore_at <= NOW()"
        ),
        {"lid": location_id},
    )
    # Commit happens at the boundary (caller). We don't commit here so that
    # the lazy-restore + lazy-finalize sequence inside `client/details` shares
    # a single transaction.


def _roll_double_units(base_quantity: int, double_chance_pct: float) -> int:
    """Per-base-unit double-roll. Returns the number of EXTRA units rolled.

    Per FEAT-128 section 3.6: for each base unit, roll uniform 0..100 and add
    one if the roll succeeds. Sum of extras is returned (clamping happens at
    the caller).
    """
    if base_quantity <= 0 or double_chance_pct <= 0:
        return 0
    extras = 0
    threshold = double_chance_pct
    for _ in range(base_quantity):
        if random.random() * 100.0 < threshold:
            extras += 1
    return extras


async def _award_via_inventory(
    character_id: int,
    skill_slug: str,
    result_item_id: int,
    granted_quantity: int,
    tool_inventory_item_id: Optional[int],
) -> Optional[Dict]:
    """Best-effort POST to inventory-service /internal/.../gathering/award.

    Returns the parsed JSON on success, None on any transport / 5xx failure.
    The caller must treat None as "leave the session active and retry next
    poll" — never propagate the error to the client/details handler.
    """
    payload = {
        "skill_slug": skill_slug,
        "result_item_id": int(result_item_id),
        "result_quantity": int(granted_quantity),
        "xp_to_add": int(granted_quantity),  # 1 XP per unit gathered, FEAT-128 §1
        "tool_inventory_item_id": (
            int(tool_inventory_item_id)
            if tool_inventory_item_id is not None
            else None
        ),
        "tool_durability_to_consume": (
            int(granted_quantity) if tool_inventory_item_id is not None else 0
        ),
    }
    url = (
        f"{settings.INVENTORY_SERVICE_URL}"
        f"/inventory/internal/characters/{character_id}/gathering/award"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            logger.warning(
                "gathering award returned status %s for char %s: %s",
                resp.status_code, character_id, resp.text,
            )
            # 4xx is a permanent input error — surface as non-success so the
            # session retries (in case of transient validation drift). For
            # 5xx/timeouts we also retry. Either way, return None.
            return None
        return resp.json()
    except Exception as exc:
        logger.warning(
            "gathering award call failed for char %s: %s", character_id, exc,
        )
        return None


async def _get_tool_current_durability(
    session: AsyncSession, tool_inventory_item_id: int
) -> Optional[int]:
    """Read `character_inventory.current_durability` for a tool slot from the
    shared DB. Returns None if the row is missing or has NULL durability
    (NULL = full per inventory-service convention).

    Per FEAT-128 §3.5.4: the durability cap on awarded units is
    `current_durability_now + 1` (one grace unit on the very last point).
    """
    try:
        result = await session.execute(
            text(
                "SELECT current_durability FROM character_inventory "
                "WHERE id = :iid LIMIT 1"
            ),
            {"iid": tool_inventory_item_id},
        )
        row = result.fetchone()
    except Exception as exc:
        logger.warning(
            "Failed to read tool durability for inventory_item_id %s: %s",
            tool_inventory_item_id, exc,
        )
        return None
    if row is None:
        return None
    val = row[0]
    if val is None:
        # NULL = full — no cap from durability is meaningful here, return a
        # sentinel large value so the caller's `min(...)` is a no-op.
        return None
    return int(val)


# Snapshot of node category -> skill slug used by the inventory award call.
_CATEGORY_TO_SKILL_SLUG = {
    "ore": "mining",
    "herb": "herbalism",
    "wood": "woodcutting",
}


async def finalize_due_sessions(
    db: AsyncSession, character_id: Optional[int] = None
) -> List[Dict]:
    """Lazy-finalize active gathering sessions whose `complete_at <= NOW()`.

    Reusable from both `client/details` (no character filter — finalizes any
    overdue session globally so the location surface stays consistent) and
    the per-character poll endpoint (filtered to one character).

    For each due session:
      1. SELECT FOR UPDATE the session row + parent node row.
      2. Roll the base + per-unit double-chance to compute desired quantity.
      3. Cap by `tool_durability_at_start + 1` per FEAT-128 §3.5.4. Since we
         do not snapshot starting durability, we read the tool's current
         durability now (i.e. what's left after any prior partial spends) and
         use `current_durability_now + 1` as the cap. Without a tool, no cap.
      4. Cap by `current_bank` of the node (the pool can't go negative).
      5. Decrement bank atomically; if it hits 0, mark depleted and start the
         24h restore timer.
      6. Call inventory-service award (best-effort). If it fails, leave the
         session active for retry on the next poll.
      7. Apply the response: status=completed | inventory_full,
         finished_at=NOW(), result_quantity=actual_quantity_added,
         xp_awarded=response.xp_awarded.
      8. If inventory was full and only part of the granted units was
         accepted, re-credit the unused portion back to the bank (which may
         also resurrect the node from `depleted` back to live).

    Returns the list of finalize summary dicts (one per finalized session).
    The list is currently used by callers for logging / future extension; the
    poll endpoint will instead read the session row back to build its own
    response shape.
    """
    # 1. Find due active sessions (optionally scoped to a single character).
    sql = (
        "SELECT id FROM gathering_sessions "
        "WHERE status = 'active' AND complete_at <= NOW() "
    )
    params: Dict[str, int] = {}
    if character_id is not None:
        sql += "AND character_id = :cid "
        params["cid"] = int(character_id)
    sql += "ORDER BY complete_at ASC LIMIT 50 FOR UPDATE"

    try:
        due_rows = (await db.execute(text(sql), params)).fetchall()
    except Exception as exc:
        # Never break the calling endpoint because of a finalize SELECT
        # failure — the next poll will retry.
        logger.warning("finalize_due_sessions select failed: %s", exc)
        return []

    summaries: List[Dict] = []

    for (sess_id,) in due_rows:
        try:
            summary = await _finalize_one_session(db, int(sess_id))
            if summary is not None:
                summaries.append(summary)
        except Exception as exc:
            # Per session: log and continue. Don't poison the rest of the
            # batch and don't propagate to the calling endpoint.
            logger.exception(
                "finalize_due_sessions: failure on session %s: %s",
                sess_id, exc,
            )

    # Caller controls the outer commit (e.g. client/details handler), but if
    # there were finalizations we flush them now so subsequent reads in the
    # same transaction see updated state.
    if summaries:
        try:
            await db.commit()
        except Exception as exc:
            logger.warning("finalize_due_sessions commit failed: %s", exc)
            try:
                await db.rollback()
            except Exception:
                pass

    return summaries


async def _finalize_one_session(
    db: AsyncSession, session_id: int
) -> Optional[Dict]:
    """Finalize a single overdue gathering session. Returns a summary dict on
    success, None if the session was no longer active by the time we locked
    it (raced with manual cancel)."""
    # Re-lock the row with FOR UPDATE so a concurrent cancel can't slip in.
    sess_row = (
        await db.execute(
            text(
                "SELECT id, node_id, character_id, tool_inventory_item_id, "
                "       complete_at, effective_double_chance_pct, "
                "       stamina_paid, status "
                "FROM gathering_sessions "
                "WHERE id = :sid FOR UPDATE"
            ),
            {"sid": session_id},
        )
    ).fetchone()
    if sess_row is None:
        return None
    if sess_row.status != "active":
        # Already cancelled/finalized between the outer SELECT and this lock.
        return None

    node_id = int(sess_row.node_id)
    character_id = int(sess_row.character_id)
    tool_inv_id = (
        int(sess_row.tool_inventory_item_id)
        if sess_row.tool_inventory_item_id is not None
        else None
    )
    double_chance_pct = float(sess_row.effective_double_chance_pct or 0.0)

    # Lock the parent node so concurrent finalizers serialize on the bank.
    node_row = (
        await db.execute(
            text(
                "SELECT id, location_id, node_name, category, result_item_id, "
                "       result_quantity_per_gather, current_bank, "
                "       daily_bank_max "
                "FROM gathering_nodes WHERE id = :nid FOR UPDATE"
            ),
            {"nid": node_id},
        )
    ).fetchone()
    if node_row is None:
        # Node was deleted — close the session as cancelled to keep the table
        # clean.
        await db.execute(
            text(
                "UPDATE gathering_sessions "
                "SET status = 'cancelled', finished_at = NOW(), "
                "    result_quantity = 0, xp_awarded = 0 "
                "WHERE id = :sid"
            ),
            {"sid": session_id},
        )
        return {
            "session_id": session_id,
            "node_id": node_id,
            "character_id": character_id,
            "tool_inventory_item_id": tool_inv_id,
            "status": "cancelled",
            "result_quantity": 0,
            "xp_gained": 0,
            "rank_up_to": None,
            "skill_slug": None,
            "tool_durability_remaining": None,
            "tool_broke": False,
            "node_name": None,
            "result_item_id": None,
            "result_item_name": None,
        }

    base_quantity = int(node_row.result_quantity_per_gather or 0)
    current_bank = int(node_row.current_bank or 0)
    daily_bank_max = int(node_row.daily_bank_max or 0)

    # Step 2: per-base-unit double-chance roll
    extras = _roll_double_units(base_quantity, double_chance_pct)
    desired = base_quantity + extras

    # Step 3: tool-durability cap (FEAT-128 §3.5.4)
    if tool_inv_id is not None:
        cur_dur = await _get_tool_current_durability(db, tool_inv_id)
        if cur_dur is not None:
            cap = max(0, cur_dur) + 1
            if desired > cap:
                desired = cap
    # else: no tool, no durability cap

    # Step 4: cap by available bank
    granted = max(0, min(desired, current_bank))

    # Step 5: decrement the bank atomically. We compute the new value here
    # because we already hold the row lock; a single UPDATE covers it.
    new_bank = current_bank - granted
    bank_was_depleted_now = new_bank <= 0
    if bank_was_depleted_now:
        await db.execute(
            text(
                "UPDATE gathering_nodes "
                "SET current_bank = 0, "
                "    depleted_at = NOW(), "
                "    restore_at = DATE_ADD(NOW(), INTERVAL 24 HOUR) "
                "WHERE id = :nid"
            ),
            {"nid": node_id},
        )
        new_bank = 0
    else:
        await db.execute(
            text(
                "UPDATE gathering_nodes "
                "SET current_bank = :nb "
                "WHERE id = :nid"
            ),
            {"nb": new_bank, "nid": node_id},
        )

    # Step 6: best-effort inventory-service award
    skill_slug = _CATEGORY_TO_SKILL_SLUG.get(
        str(node_row.category), "mining"
    )

    if granted == 0:
        # Nothing to award (bank empty or durability was 0 from the cap).
        # Close as completed with zeros — no inventory call needed.
        await db.execute(
            text(
                "UPDATE gathering_sessions "
                "SET status = 'completed', finished_at = NOW(), "
                "    result_quantity = 0, xp_awarded = 0 "
                "WHERE id = :sid"
            ),
            {"sid": session_id},
        )
        # No inventory call -> tool durability is whatever it currently is on
        # the row (we already read it above for the cap, may be None).
        tool_durability_now: Optional[int] = None
        if tool_inv_id is not None:
            try:
                tool_durability_now = await _get_tool_current_durability(
                    db, tool_inv_id
                )
            except Exception:
                tool_durability_now = None
        return {
            "session_id": session_id,
            "node_id": node_id,
            "character_id": character_id,
            "tool_inventory_item_id": tool_inv_id,
            "status": "completed",
            "result_quantity": 0,
            "xp_gained": 0,
            "rank_up_to": None,
            "skill_slug": skill_slug,
            "tool_durability_remaining": tool_durability_now,
            "tool_broke": False,
            "node_name": str(node_row.node_name or ""),
            "result_item_id": int(node_row.result_item_id),
            "result_item_name": None,
        }

    award_resp = await _award_via_inventory(
        character_id=character_id,
        skill_slug=skill_slug,
        result_item_id=int(node_row.result_item_id),
        granted_quantity=granted,
        tool_inventory_item_id=tool_inv_id,
    )

    if award_resp is None:
        # Inventory-service is unavailable. Roll back our bank decrement and
        # leave the session as `active` so the next poll retries.
        rollback_bank = current_bank  # original value before decrement
        await db.execute(
            text(
                "UPDATE gathering_nodes "
                "SET current_bank = :nb, "
                "    depleted_at = NULL, "
                "    restore_at = NULL "
                "WHERE id = :nid"
            ),
            {"nb": rollback_bank, "nid": node_id},
        )
        return None

    actual_added = int(award_resp.get("actual_quantity_added", 0) or 0)
    inv_full = bool(award_resp.get("inventory_full", False))
    xp_gained = int(award_resp.get("xp_awarded", 0) or 0)
    rank_up = bool(award_resp.get("rank_up", False))
    new_rank_val = award_resp.get("current_rank")
    new_rank_int = int(new_rank_val) if new_rank_val is not None else None
    # rank_up_to is the new rank number IFF a rank-up actually happened this
    # session. Otherwise None — frontend uses truthiness to detect rank-up.
    rank_up_to = new_rank_int if rank_up else None
    tool_broke = bool(award_resp.get("tool_broke", False))
    tool_durability_remaining_val = award_resp.get("tool_durability_remaining")
    tool_durability_remaining = (
        int(tool_durability_remaining_val)
        if tool_durability_remaining_val is not None
        else None
    )

    if inv_full or actual_added < granted:
        # Inventory could not absorb everything — re-credit the unused
        # portion back to the bank. If this re-credit pulls the bank back
        # above zero, undo the depletion timestamps we just set.
        unused = granted - actual_added
        new_status = "inventory_full"
        if unused > 0:
            await db.execute(
                text(
                    "UPDATE gathering_nodes "
                    "SET current_bank = LEAST(current_bank + :inc, :cap), "
                    "    depleted_at = CASE "
                    "        WHEN (current_bank + :inc) > 0 "
                    "        THEN NULL ELSE depleted_at END, "
                    "    restore_at = CASE "
                    "        WHEN (current_bank + :inc) > 0 "
                    "        THEN NULL ELSE restore_at END "
                    "WHERE id = :nid"
                ),
                {"inc": unused, "cap": daily_bank_max, "nid": node_id},
            )
    else:
        new_status = "completed"

    await db.execute(
        text(
            "UPDATE gathering_sessions "
            "SET status = :st, finished_at = NOW(), "
            "    result_quantity = :rq, xp_awarded = :xp "
            "WHERE id = :sid"
        ),
        {
            "st": new_status,
            "rq": actual_added,
            "xp": xp_gained,
            "sid": session_id,
        },
    )

    # Resolve item name for the toast (best-effort, single SELECT on items).
    result_item_name: Optional[str] = None
    try:
        items_brief = await _fetch_item_brief(db, [int(node_row.result_item_id)])
        result_item_name = (
            (items_brief.get(int(node_row.result_item_id)) or {}).get("name")
        )
    except Exception:
        result_item_name = None

    return {
        "session_id": session_id,
        "node_id": node_id,
        "character_id": character_id,
        "tool_inventory_item_id": tool_inv_id,
        "status": new_status,
        "result_quantity": actual_added,
        "xp_gained": xp_gained,
        "rank_up_to": rank_up_to,
        "skill_slug": skill_slug,
        "tool_durability_remaining": tool_durability_remaining,
        "tool_broke": tool_broke,
        "node_name": str(node_row.node_name or ""),
        "result_item_id": int(node_row.result_item_id),
        "result_item_name": result_item_name,
    }


async def _fetch_active_sessions_for_nodes(
    session: AsyncSession, node_ids: List[int]
) -> Dict[int, List[Dict]]:
    """Return active (non-overdue) sessions grouped by node_id.

    Uses a single SQL query and is callable after `finalize_due_sessions` has
    closed any overdue rows, so the listing reflects only sessions still in
    progress (`status='active' AND complete_at > NOW()`).
    """
    if not node_ids:
        return {}
    from sqlalchemy import bindparam
    stmt = text(
        "SELECT id, node_id, character_id, started_at, complete_at "
        "FROM gathering_sessions "
        "WHERE node_id IN :nids "
        "  AND status = 'active' "
        "  AND complete_at > NOW() "
        "ORDER BY complete_at ASC"
    ).bindparams(bindparam("nids", expanding=True))
    rows = (await session.execute(stmt, {"nids": list(node_ids)})).fetchall()
    out: Dict[int, List[Dict]] = {}
    for row in rows:
        out.setdefault(int(row.node_id), []).append({
            "session_id": int(row.id),
            "character_id": int(row.character_id),
            "started_at": _ensure_aware_utc(row.started_at),
            "complete_at": _ensure_aware_utc(row.complete_at),
        })
    return out


async def _fetch_character_brief_map(
    character_ids: List[int]
) -> Dict[int, Dict[str, Optional[str]]]:
    """Batch-fetch `{id: {name, avatar}}` from character-service.

    Calls `/{cid}/short_info` for each id (the service has no explicit batch
    endpoint — see analyst notes 2.2). Failures are non-fatal: we return an
    empty entry for that id so the surface still renders.
    """
    if not character_ids:
        return {}
    out: Dict[int, Dict[str, Optional[str]]] = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for cid in set(character_ids):
            try:
                resp = await client.get(
                    f"{settings.CHARACTER_SERVICE_URL}/characters/{cid}/short_info"
                )
                if resp.status_code == 200:
                    data = resp.json() or {}
                    out[int(cid)] = {
                        "name": data.get("name", ""),
                        "avatar": data.get("avatar"),
                    }
                else:
                    out[int(cid)] = {"name": "", "avatar": None}
            except Exception as exc:
                logger.warning(
                    "short_info lookup failed for character %s: %s", cid, exc,
                )
                out[int(cid)] = {"name": "", "avatar": None}
    return out


async def fetch_gathering_nodes_with_active_sessions(
    session: AsyncSession,
    location_id: int,
    players_at_location: Optional[List[Dict]] = None,
) -> List[Dict]:
    """Build the `gathering_nodes[]` payload for `LocationClientDetails`.

    - Pulls all enabled-or-disabled nodes on the location (admins surface
      both; clients see them all and the frontend filters by `is_enabled`).
    - JOINs `result_item_*` from the shared `items` table in batch.
    - Lists each node's currently-active sessions (status='active',
      complete_at > NOW()) with character_name / avatar enriched in batch.
    - Falls back to `players_at_location` (already loaded by the
      `client/details` handler) before reaching out to character-service to
      avoid duplicate HTTP calls when the gatherer is the player viewing.
    """
    result = await session.execute(
        select(GatheringNode)
        .where(GatheringNode.location_id == location_id)
        .order_by(GatheringNode.id.asc())
    )
    nodes: List[GatheringNode] = list(result.scalars().all())
    if not nodes:
        return []

    # Batch item lookup
    item_ids = {n.result_item_id for n in nodes if n.result_item_id is not None}
    items_brief = await _fetch_item_brief(session, list(item_ids))

    # Batch active-sessions per node
    sessions_by_node = await _fetch_active_sessions_for_nodes(
        session, [n.id for n in nodes]
    )

    # Collect all character_ids needing name/avatar enrichment
    needed_cids: set = set()
    for sess_list in sessions_by_node.values():
        for sess in sess_list:
            needed_cids.add(sess["character_id"])

    # Use already-loaded players list as a no-cost lookup map first.
    player_map: Dict[int, Dict[str, Optional[str]]] = {}
    if players_at_location:
        for p in players_at_location:
            try:
                pid = int(p.get("id"))
            except (TypeError, ValueError):
                continue
            player_map[pid] = {
                "name": p.get("name") or p.get("character_name") or "",
                "avatar": p.get("avatar") or p.get("character_photo"),
            }

    missing_cids = [cid for cid in needed_cids if cid not in player_map]
    fetched_map = await _fetch_character_brief_map(missing_cids)
    char_map: Dict[int, Dict[str, Optional[str]]] = {}
    char_map.update(player_map)
    char_map.update(fetched_map)

    out: List[Dict] = []
    for n in nodes:
        item_brief = items_brief.get(n.result_item_id) or {}
        active_payload: List[Dict] = []
        for sess in sessions_by_node.get(n.id, []):
            cid = sess["character_id"]
            cdata = char_map.get(cid) or {}
            active_payload.append({
                "session_id": sess["session_id"],
                "character_id": cid,
                "character_name": cdata.get("name") or "",
                "character_avatar_url": cdata.get("avatar"),
                "started_at": sess["started_at"],
                "complete_at": sess["complete_at"],
            })

        out.append({
            "id": int(n.id),
            "node_name": n.node_name,
            "category": str(n.category),
            "result_item_id": int(n.result_item_id),
            "result_item_name": item_brief.get("name"),
            "result_item_image": item_brief.get("image"),
            "result_item_type": item_brief.get("item_type"),
            "result_quantity_per_gather": int(n.result_quantity_per_gather or 0),
            "stamina_per_gather": int(n.stamina_per_gather or 0),
            # Per spec 3.6: base_seconds = stamina_per_gather * 5 * 60
            "base_seconds": int((n.stamina_per_gather or 0) * 5 * 60),
            "current_bank": int(n.current_bank or 0),
            "daily_bank_max": int(n.daily_bank_max or 0),
            "allow_concurrent_gather": bool(n.allow_concurrent_gather),
            "depleted_at": _ensure_aware_utc(n.depleted_at),
            "restore_at": _ensure_aware_utc(n.restore_at),
            "is_enabled": bool(n.is_enabled),
            "active_sessions": active_payload,
        })

    return out


# -----------------------------------------------------------------------------
# GATHERING — START SESSION (FEAT-128 task #14)
# -----------------------------------------------------------------------------
#
# Implements POST /locations/{lid}/gathering-nodes/{nid}/start per FEAT-128
# section 3.5.1. The route handler in main.py is a thin wrapper; this helper
# does the bulk of validation + cross-service orchestration.
#
# Key invariants:
#   - SELECT ... FOR UPDATE on the gathering_nodes row is held from the bank /
#     concurrency check through to the gathering_sessions INSERT and final
#     COMMIT. Concurrent starts on the same node block here and re-evaluate
#     bank / occupancy on resume.
#   - Stamina is consumed via attributes-service BEFORE the session row is
#     inserted; on cross-service failure the route returns 502 and the
#     session is never created (stamina untouched per the receiving service).
#   - Auto-post creation is best-effort. If posting fails, we log and ignore;
#     the gathering session is still committed (the player has already paid
#     stamina and we don't want to roll that back over a cosmetic post).


# Mapping from gathering node category to required tool category and the
# inventory-service skill slug. Single source of truth for FEAT-128 §3.6.
_GATHER_NODE_CATEGORY_TO_TOOL_CATEGORY = {
    "ore": "pickaxe",
    "herb": "sickle",
    "wood": "axe",
}
_GATHER_NODE_CATEGORY_TO_SKILL_SLUG = {
    "ore": "mining",
    "herb": "herbalism",
    "wood": "woodcutting",
}

# Caps from FEAT-128 §3.6.
_GATHER_SPEED_CAP_PCT = 60.0
_GATHER_STAMINA_CAP_PCT = 50.0
_GATHER_DOUBLE_CHANCE_CAP_PCT = 80.0
_GATHER_MIN_SECONDS = 30
_GATHER_MIN_STAMINA = 1


async def _load_gathering_node_for_update(
    session: AsyncSession, node_id: int, location_id: int
):
    """Load a gathering node by id with FOR UPDATE row lock.

    Raises 404 if missing or if its `location_id` does not match the path
    (so requests like `/locations/5/gathering-nodes/12/start` referring to
    a node that belongs to location 7 fail cleanly).
    """
    stmt = (
        select(GatheringNode)
        .where(GatheringNode.id == node_id)
        .with_for_update()
    )
    result = await session.execute(stmt)
    node: Optional[GatheringNode] = result.scalars().first()
    if node is None:
        raise HTTPException(status_code=404, detail="Нода добычи не найдена")
    if int(node.location_id) != int(location_id):
        raise HTTPException(status_code=404, detail="Нода добычи не найдена")
    return node


async def _count_active_sessions_on_node(
    session: AsyncSession, node_id: int
) -> int:
    """Count sessions on a node that are still in-flight (active and not
    overdue). Sessions whose `complete_at` is past are excluded — they are
    effectively closed pending lazy finalize and shouldn't count for the
    `allow_concurrent_gather=False` guard.
    """
    result = await session.execute(
        text(
            "SELECT COUNT(*) FROM gathering_sessions "
            "WHERE node_id = :nid AND status = 'active' AND complete_at > NOW()"
        ),
        {"nid": node_id},
    )
    val = result.scalar()
    return int(val or 0)


async def _load_tool_for_gathering(
    session: AsyncSession,
    tool_inventory_item_id: int,
    character_id: int,
    node_category: str,
) -> Dict:
    """Validate a tool selection against a gathering node category.

    Performs a single raw-SQL JOIN against the shared `character_inventory`
    + `items` tables (both owned by inventory-service). All validation errors
    raise HTTPException with Russian messages and the proper status codes.

    Returns a dict with the tool's gather_* bonuses (ready to feed into the
    formula in FEAT-128 §3.6).
    """
    expected_tool_category = _GATHER_NODE_CATEGORY_TO_TOOL_CATEGORY.get(node_category)
    if expected_tool_category is None:
        # Defensive: should be impossible since node.category is constrained.
        raise HTTPException(
            status_code=422,
            detail="Неизвестная категория ноды добычи",
        )

    result = await session.execute(
        text(
            "SELECT ci.character_id, ci.current_durability, "
            "       i.item_type, i.tool_category, "
            "       COALESCE(i.gather_double_chance_bonus, 0) AS dbl, "
            "       COALESCE(i.gather_speed_bonus_pct, 0) AS spd, "
            "       COALESCE(i.gather_stamina_bonus_pct, 0) AS stm "
            "FROM character_inventory ci "
            "JOIN items i ON i.id = ci.item_id "
            "WHERE ci.id = :iid"
        ),
        {"iid": tool_inventory_item_id},
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Инструмент не найден")

    if int(row[0]) != int(character_id):
        raise HTTPException(
            status_code=403,
            detail="Этот инструмент не принадлежит вашему персонажу",
        )

    item_type = row[2]
    tool_category_actual = row[3]

    if item_type != "gathering_tool":
        raise HTTPException(
            status_code=422,
            detail="Предмет не является инструментом сбора",
        )

    if tool_category_actual != expected_tool_category:
        raise HTTPException(
            status_code=422,
            detail="Инструмент не подходит для этого ресурса",
        )

    durability = row[1]
    # NULL durability == full per inventory-service convention; only treat
    # explicit 0 as "broken".
    if durability is not None and int(durability) <= 0:
        raise HTTPException(status_code=422, detail="Инструмент сломан")

    return {
        "gather_double_chance_bonus": float(row[4] or 0.0),
        "gather_speed_bonus_pct": float(row[5] or 0.0),
        "gather_stamina_bonus_pct": float(row[6] or 0.0),
    }


async def _fetch_rank_bonuses_for_category(
    character_id: int, node_category: str
) -> Dict[str, float]:
    """Cross-service GET to inventory-service to read the character's current
    gathering-skill rank bonuses for the matching skill (mining/herbalism/
    woodcutting). Returns a dict with `S_speed`, `S_stamina`, `S_double` keys.

    On any cross-service failure we degrade gracefully: rank bonuses default
    to zero. This matches the lazy-create behaviour on the inventory side
    (any new character starts at rank 1 with all bonuses = 0 anyway).
    """
    skill_slug = _GATHER_NODE_CATEGORY_TO_SKILL_SLUG.get(node_category)
    if skill_slug is None:
        return {"speed_pct": 0.0, "stamina_pct": 0.0, "double_chance_pct": 0.0}

    url = (
        f"{settings.INVENTORY_SERVICE_URL}"
        f"/inventory/characters/{character_id}/gathering-skills"
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            logger.warning(
                "gathering-skills lookup returned %s for char %s: %s",
                resp.status_code, character_id, resp.text,
            )
            return {"speed_pct": 0.0, "stamina_pct": 0.0, "double_chance_pct": 0.0}
        data = resp.json() or {}
    except Exception as exc:
        logger.warning(
            "gathering-skills lookup failed for char %s: %s", character_id, exc,
        )
        return {"speed_pct": 0.0, "stamina_pct": 0.0, "double_chance_pct": 0.0}

    for skill in (data.get("skills") or []):
        if skill.get("slug") == skill_slug:
            cur = skill.get("current_rank_bonuses") or {}
            return {
                "speed_pct": float(cur.get("speed_bonus_pct", 0.0) or 0.0),
                "stamina_pct": float(cur.get("stamina_bonus_pct", 0.0) or 0.0),
                "double_chance_pct": float(cur.get("double_chance_bonus", 0.0) or 0.0),
            }

    return {"speed_pct": 0.0, "stamina_pct": 0.0, "double_chance_pct": 0.0}


def _compute_effective_gather_params(
    base_stamina: int,
    has_tool: bool,
    rank_bonuses: Dict[str, float],
    tool_bonuses: Dict[str, float],
) -> Dict[str, float]:
    """Apply the FEAT-128 §3.6 formulas (lenient no-tool variant).

    Returns a dict with effective_seconds (int), effective_stamina_paid (int),
    effective_speed_bonus_pct (float, capped), effective_double_chance_pct
    (float, gated on tool), effective_stamina_bonus_pct (float, capped).
    """
    base_seconds = int(base_stamina) * 5 * 60  # 1 stamina = 5 min

    s_speed = float(rank_bonuses.get("speed_pct", 0.0) or 0.0)
    s_stamina = float(rank_bonuses.get("stamina_pct", 0.0) or 0.0)
    s_double = float(rank_bonuses.get("double_chance_pct", 0.0) or 0.0)

    if has_tool:
        t_speed = float(tool_bonuses.get("gather_speed_bonus_pct", 0.0) or 0.0)
        t_stamina = float(tool_bonuses.get("gather_stamina_bonus_pct", 0.0) or 0.0)
        t_double = float(tool_bonuses.get("gather_double_chance_bonus", 0.0) or 0.0)
    else:
        t_speed = 0.0
        t_stamina = 0.0
        t_double = 0.0

    speed_total_pct = min(s_speed + t_speed, _GATHER_SPEED_CAP_PCT)
    seconds = math.floor(base_seconds * (1.0 - speed_total_pct / 100.0))
    if not has_tool:
        seconds = seconds * 2  # ×2 penalty AFTER rank speed bonus
    seconds = max(int(seconds), _GATHER_MIN_SECONDS)

    stamina_total_pct = min(s_stamina + t_stamina, _GATHER_STAMINA_CAP_PCT)
    paid = math.ceil(int(base_stamina) * (1.0 - stamina_total_pct / 100.0))
    paid = max(int(paid), _GATHER_MIN_STAMINA)

    if has_tool:
        double_chance = min(s_double + t_double, _GATHER_DOUBLE_CHANCE_CAP_PCT)
    else:
        double_chance = 0.0

    return {
        "effective_seconds": int(seconds),
        "effective_stamina_paid": int(paid),
        "effective_speed_bonus_pct": float(speed_total_pct),
        "effective_double_chance_pct": float(double_chance),
        "effective_stamina_bonus_pct": float(stamina_total_pct),
    }


async def _consume_stamina_via_attributes(
    character_id: int, amount: int
) -> bool:
    """Cross-service POST to attributes-service /consume_stamina.

    Returns True on a 200 OK, False on any other outcome (4xx/5xx/transport).
    On False the caller MUST return a 502 to the player without inserting a
    session row — we do not want to create a session that was never paid for.
    """
    url = (
        f"{settings.ATTRIBUTES_SERVICE_URL}"
        f"/attributes/{character_id}/consume_stamina"
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json={"amount": int(amount)})
        if resp.status_code != 200:
            logger.warning(
                "consume_stamina returned %s for char %s: %s",
                resp.status_code, character_id, resp.text,
            )
            return False
        return True
    except Exception as exc:
        logger.warning(
            "consume_stamina call failed for char %s: %s", character_id, exc,
        )
        return False


async def _read_current_stamina(character_id: int) -> Optional[int]:
    """Cross-service GET to attributes-service /attributes/{cid}.
    Returns current_stamina (int) on success, None on failure.
    """
    url = f"{settings.ATTRIBUTES_SERVICE_URL}/attributes/{character_id}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return None
        data = resp.json() or {}
        val = data.get("current_stamina")
        if val is None:
            return None
        return int(val)
    except Exception as exc:
        logger.warning(
            "attributes lookup failed for char %s: %s", character_id, exc,
        )
        return None


async def _check_inventory_has_free_slot(character_id: int) -> bool:
    """Cross-service POST to inventory-service /internal/free_slots_check.

    Returns True if the character has at least one free slot, False if full
    OR if the cross-service call fails (fail-safe: blocking is the right
    behaviour rather than letting the player start a session whose award
    might bounce). The caller surfaces this as 400 to the player.
    """
    url = (
        f"{settings.INVENTORY_SERVICE_URL}"
        f"/inventory/internal/characters/{character_id}/free_slots_check"
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json={})
        if resp.status_code != 200:
            logger.warning(
                "free_slots_check returned %s for char %s: %s",
                resp.status_code, character_id, resp.text,
            )
            return False
        data = resp.json() or {}
        return not bool(data.get("is_full", True))
    except Exception as exc:
        logger.warning(
            "free_slots_check call failed for char %s: %s", character_id, exc,
        )
        return False


async def _read_character_for_start(
    session: AsyncSession, character_id: int
) -> Tuple[int, Optional[int], str]:
    """Read the minimal character fields needed by the start endpoint from
    the shared `characters` table: (user_id, current_location_id, name).

    Raises 404 if the character does not exist. Owner-check is performed by
    the caller, not here.
    """
    result = await session.execute(
        text(
            "SELECT user_id, current_location_id, name "
            "FROM characters WHERE id = :cid LIMIT 1"
        ),
        {"cid": character_id},
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Персонаж не найден")
    return (
        int(row[0]) if row[0] is not None else None,
        int(row[1]) if row[1] is not None else None,
        row[2] or "",
    )


async def start_gathering(
    db: AsyncSession,
    *,
    location_id: int,
    node_id: int,
    character_id: int,
    tool_inventory_item_id: Optional[int],
    current_user_id: int,
) -> Dict:
    """Start a gathering session on a node. Implements FEAT-128 §3.5.1.

    Holds a SELECT FOR UPDATE on the node row from the validation block all
    the way through to the final commit, so concurrent calls on the same
    node serialize cleanly.

    Returns a dict suitable for `StartGatheringResponse.parse_obj`.
    """
    # 1. Load character + ownership check.
    user_id, current_loc, character_name = await _read_character_for_start(
        db, character_id
    )
    if user_id != int(current_user_id):
        raise HTTPException(
            status_code=403,
            detail="Вы можете управлять только своими персонажами",
        )

    # 2. Same-location check.
    if current_loc is None or int(current_loc) != int(location_id):
        raise HTTPException(
            status_code=400,
            detail="Персонаж не находится на этой локации",
        )

    # 3. Reap any stale completed sessions for THIS character before proceeding.
    # If finalize commits inside the helper we just lost any FOR UPDATE we
    # were holding — but we haven't taken any locks yet, so this is fine.
    try:
        await finalize_due_sessions(db, character_id=character_id)
    except Exception as exc:
        logger.warning(
            "finalize_due_sessions(%s) failed pre-start, continuing: %s",
            character_id, exc,
        )

    # 4. Battle-lock + already-gathering-lock checks. Late import keeps the
    # main->crud import direction one-way (no module-level cycle).
    from main import check_not_in_battle, check_not_gathering  # noqa: WPS433
    await check_not_in_battle(
        db, character_id, "Нельзя начать добычу во время боя"
    )
    await check_not_gathering(db, character_id, "Уже идёт добыча")

    # 5. Lock the node row. From here on we hold the lock until commit.
    node = await _load_gathering_node_for_update(db, node_id, location_id)

    # 6. Enabled?
    if not bool(node.is_enabled):
        raise HTTPException(status_code=400, detail="Нода отключена")

    # 7. Bank not exhausted? A node with current_bank=0 OR a future restore_at
    # is depleted.
    now = datetime.now(timezone.utc)
    restore_at = _ensure_aware_utc(node.restore_at)
    is_depleted = (
        int(node.current_bank or 0) <= 0
        or (restore_at is not None and restore_at > now)
    )
    if is_depleted:
        raise HTTPException(status_code=400, detail="Нода истощена")

    # 8. Concurrency guard: if the node disallows concurrent gathering, refuse
    # if any other active (non-overdue) session exists.
    if not bool(node.allow_concurrent_gather):
        active_count = await _count_active_sessions_on_node(db, int(node.id))
        if active_count > 0:
            raise HTTPException(
                status_code=409,
                detail="Нода занята другим персонажем",
            )

    # 9. Tool validation (if provided). Reads from shared DB inside the same
    # transaction as the FOR UPDATE on the node.
    has_tool = tool_inventory_item_id is not None
    tool_bonuses: Dict[str, float] = {
        "gather_double_chance_bonus": 0.0,
        "gather_speed_bonus_pct": 0.0,
        "gather_stamina_bonus_pct": 0.0,
    }
    if has_tool:
        tool_bonuses = await _load_tool_for_gathering(
            db, int(tool_inventory_item_id), character_id, str(node.category),
        )

    # 10. Compute effective parameters.
    rank_bonuses = await _fetch_rank_bonuses_for_category(
        character_id, str(node.category)
    )
    eff = _compute_effective_gather_params(
        base_stamina=int(node.stamina_per_gather),
        has_tool=has_tool,
        rank_bonuses=rank_bonuses,
        tool_bonuses=tool_bonuses,
    )

    # 11. Stamina sufficiency check (read first, consume after pre-flight).
    current_stamina = await _read_current_stamina(character_id)
    if current_stamina is None or current_stamina < eff["effective_stamina_paid"]:
        raise HTTPException(status_code=400, detail="Недостаточно стамины")

    # 12. Pre-flight inventory check (no point spending stamina if there's no
    # room for the result item even before we factor doubles).
    has_free = await _check_inventory_has_free_slot(character_id)
    if not has_free:
        raise HTTPException(
            status_code=400,
            detail="Инвентарь полон — освободите слот",
        )

    # 13. Spend stamina via attributes-service. On failure we abort BEFORE
    # creating the session.
    spent = await _consume_stamina_via_attributes(
        character_id, int(eff["effective_stamina_paid"])
    )
    if not spent:
        # Don't leak a session; lock on node will be released by rollback.
        await db.rollback()
        raise HTTPException(status_code=502, detail="Не удалось списать стамину")

    # 14. Insert the session row. Times are computed server-side using NOW()
    # for `started_at` (so the row matches the DB's clock used in lazy queries
    # like `complete_at <= NOW()`); we mirror them in Python for the response.
    # `tool_durability_at_start` is read here as a snapshot so the response can
    # surface it (FEAT-128 §3.1.1, fix Review #1 issue #3). The actual cap on
    # awarded units at finalize uses `current_durability_now + 1` (§3.5.4),
    # not this snapshot — the field is informational for the frontend.
    tool_durability_at_start: Optional[int] = None
    if tool_inventory_item_id is not None:
        try:
            tool_durability_at_start = await _get_tool_current_durability(
                db, int(tool_inventory_item_id)
            )
        except Exception:
            tool_durability_at_start = None
    started_at_py = datetime.now(timezone.utc)
    complete_at_py = started_at_py + timedelta(seconds=int(eff["effective_seconds"]))
    new_session = GatheringSession(
        node_id=int(node.id),
        character_id=int(character_id),
        tool_inventory_item_id=(
            int(tool_inventory_item_id) if tool_inventory_item_id is not None else None
        ),
        started_at=started_at_py,
        complete_at=complete_at_py,
        effective_speed_bonus_pct=float(eff["effective_speed_bonus_pct"]),
        effective_double_chance_pct=float(eff["effective_double_chance_pct"]),
        effective_stamina_bonus_pct=float(eff["effective_stamina_bonus_pct"]),
        stamina_paid=int(eff["effective_stamina_paid"]),
        status="active",
    )
    db.add(new_session)
    await db.flush()  # populate new_session.id without releasing locks

    # 15. Auto-post on the location (mirror the quick_move pattern). Best-
    # effort: a failure here MUST NOT roll back the gathering session.
    # `crud.create_post` calls `await session.commit()` internally, so this
    # commit also flushes our gathering_session insert and releases the FOR
    # UPDATE lock on the node row. That's intentional — we want both writes
    # to land atomically before responding.
    result_item_name = ""
    try:
        items_brief = await _fetch_item_brief(db, [int(node.result_item_id)])
        result_item_name = (
            (items_brief.get(int(node.result_item_id)) or {}).get("name") or ""
        )
    except Exception:
        result_item_name = ""

    auto_content = (
        f"<em>*{character_name} начинает добычу: {result_item_name}*</em>"
        if result_item_name
        else f"<em>*{character_name} начинает добычу*</em>"
    )
    auto_post_committed = False
    auto_post_id: Optional[int] = None
    try:
        post_in = PostCreate(
            character_id=int(character_id),
            location_id=int(location_id),
            content=auto_content,
        )
        new_post_obj = await create_post(db, post_in)
        auto_post_committed = True
        if new_post_obj is not None and getattr(new_post_obj, "id", None) is not None:
            auto_post_id = int(new_post_obj.id)
    except Exception as exc:
        logger.warning(
            "Auto-post on gathering start failed for char %s, node %s: %s",
            character_id, node.id, exc,
        )

    # 16. If create_post did NOT commit (because it raised), we still need to
    # commit our gathering_session row + locked node so the player sees the
    # session and the stamina charge isn't a black hole.
    if not auto_post_committed:
        try:
            await db.commit()
        except Exception as exc:
            logger.error(
                "Failed to commit gathering_session after post failure for "
                "char %s, node %s: %s. Stamina was already consumed.",
                character_id, node.id, exc,
            )
            await db.rollback()
            raise HTTPException(
                status_code=500,
                detail="Не удалось сохранить сессию добычи",
            )

    # 17. Re-read state for the response. The session is committed, so a
    # plain SELECT (no FOR UPDATE) is fine here.
    refreshed_active = await _count_active_sessions_on_node(db, int(node.id))
    return {
        "session_id": int(new_session.id),
        "node_id": int(node.id),
        "character_id": int(character_id),
        "started_at": started_at_py,
        "complete_at": complete_at_py,
        "effective_seconds": int(eff["effective_seconds"]),
        "effective_stamina_paid": int(eff["effective_stamina_paid"]),
        "effective_speed_bonus_pct": float(eff["effective_speed_bonus_pct"]),
        "effective_double_chance_pct": float(eff["effective_double_chance_pct"]),
        "effective_stamina_bonus_pct": float(eff["effective_stamina_bonus_pct"]),
        "tool_inventory_item_id": (
            int(tool_inventory_item_id) if tool_inventory_item_id is not None else None
        ),
        "tool_durability_at_start": tool_durability_at_start,
        "status": "active",
        "auto_post_id": auto_post_id,
        "node_state_after": {
            # Bank only decrements at finalize per FEAT-128 §3.5.1 step 15;
            # we expose the unchanged value so the frontend can refresh
            # without a second round-trip.
            "current_bank": int(node.current_bank or 0),
            "active_sessions_count": int(refreshed_active),
        },
    }


# ---------------------------------------------------------------------------
# FEAT-128 task #15 — cancel gathering (player-facing manual + internal)
# ---------------------------------------------------------------------------
# Both flows share the bulk of the logic: row-locked SELECT of the active
# session, ceil(stamina_paid/2) refund via attributes-service (best-effort —
# we do not roll back the cancel if the refund call fails), then a status
# update. The two flows differ only in:
#   * how the active session is located (node_id known for manual, any node
#     for internal),
#   * the final `status` value ('cancelled' vs 'interrupted_by_battle'),
#   * the auth/ownership checks (manual = owner-only, internal = trusted
#     internal token, performed by the route handler).
# Per FEAT-128 §3.6 the refund formula is `ceil(stamina_paid * 0.5)` —
# player-friendly rounding decided in §3.7.

async def _refund_stamina_via_attributes(
    character_id: int, amount: int
) -> bool:
    """Best-effort POST to attributes-service /attributes/{cid}/refund_stamina.

    Returns True on a 200 OK, False on any other outcome. Per spec, the
    caller MUST tolerate a False here (the cancel still proceeds — the
    refund failure is a recoverable accounting bug, not a blocker).
    """
    if amount <= 0:
        return True
    url = (
        f"{settings.ATTRIBUTES_SERVICE_URL}"
        f"/attributes/{character_id}/refund_stamina"
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json={"amount": int(amount)})
        if resp.status_code != 200:
            logger.warning(
                "refund_stamina returned %s for char %s: %s",
                resp.status_code, character_id, resp.text,
            )
            return False
        return True
    except Exception as exc:
        logger.warning(
            "refund_stamina call failed for char %s: %s", character_id, exc,
        )
        return False


def _compute_refund(stamina_paid: int) -> int:
    """ceil(stamina_paid * 0.5) — see FEAT-128 §3.6.

    Implemented via integer arithmetic (no float) so paid=0 -> 0, paid=1 -> 1,
    paid=5 -> 3.
    """
    if stamina_paid is None or stamina_paid <= 0:
        return 0
    return (int(stamina_paid) + 1) // 2


async def _lock_active_session_for_character(
    db: AsyncSession,
    character_id: int,
    node_id: Optional[int] = None,
) -> Optional[Dict]:
    """SELECT ... FOR UPDATE the active session row for `character_id` (and
    optionally constrained to a specific `node_id` for the manual cancel
    path). Returns a dict with the columns we need, or None if no active
    session exists.

    The FOR UPDATE serializes simultaneous cancel attempts: the second
    caller will see `status != 'active'` (or no row, if the row has just
    been updated) and short-circuit.
    """
    sql = (
        "SELECT id, node_id, character_id, stamina_paid, status "
        "FROM gathering_sessions "
        "WHERE character_id = :cid AND status = 'active' "
    )
    params: Dict[str, int] = {"cid": int(character_id)}
    if node_id is not None:
        sql += "AND node_id = :nid "
        params["nid"] = int(node_id)
    sql += "ORDER BY started_at DESC LIMIT 1 FOR UPDATE"
    row = (await db.execute(text(sql), params)).fetchone()
    if row is None:
        return None
    return {
        "id": int(row.id),
        "node_id": int(row.node_id),
        "character_id": int(row.character_id),
        "stamina_paid": int(row.stamina_paid or 0),
        "status": str(row.status),
    }


async def cancel_gathering_manual(
    db: AsyncSession,
    *,
    location_id: int,
    node_id: int,
    character_id: int,
    current_user_id: int,
) -> Dict:
    """Player-facing manual cancel. Implements FEAT-128 §3.5.4.

    Errors raised:
      * 403 if the character is not owned by `current_user_id`.
      * 400 if the character is not on `location_id`.
      * 404 if the node does not exist or belongs to a different location.
      * 400 "Активная добыча не найдена" if no row matches the node + char
        with status='active'.
    """
    # 1. Load character + ownership + same-location check.
    user_id, current_loc, _name = await _read_character_for_start(
        db, character_id
    )
    if user_id != int(current_user_id):
        raise HTTPException(
            status_code=403,
            detail="Вы можете управлять только своими персонажами",
        )
    if current_loc is None or int(current_loc) != int(location_id):
        raise HTTPException(
            status_code=400,
            detail="Персонаж не находится на этой локации",
        )

    # 2. Verify the node exists on this location (404 otherwise — keeps the
    # error mode consistent with the start endpoint).
    node_row = (
        await db.execute(
            text(
                "SELECT id, location_id FROM gathering_nodes "
                "WHERE id = :nid LIMIT 1"
            ),
            {"nid": int(node_id)},
        )
    ).fetchone()
    if node_row is None:
        raise HTTPException(status_code=404, detail="Нода не найдена")
    if int(node_row.location_id) != int(location_id):
        raise HTTPException(status_code=404, detail="Нода не найдена на этой локации")

    # 3. Lock the active session row for this (node, character).
    sess = await _lock_active_session_for_character(
        db, character_id=character_id, node_id=node_id,
    )
    if sess is None:
        raise HTTPException(
            status_code=400,
            detail="Активная добыча не найдена",
        )

    # 4. Compute refund and call attributes-service. Failures are tolerated.
    refund = _compute_refund(sess["stamina_paid"])
    refund_ok = await _refund_stamina_via_attributes(
        character_id=character_id, amount=refund,
    )
    if not refund_ok:
        logger.warning(
            "Stamina refund failed for char %s session %s — cancel proceeding",
            character_id, sess["id"],
        )

    # 5. Update session row. If the refund call failed we still record the
    # nominal refund amount in the response — the session is closed; the
    # accounting drift is logged for ops follow-up.
    await db.execute(
        text(
            "UPDATE gathering_sessions "
            "SET status = 'cancelled', finished_at = NOW(), "
            "    result_quantity = 0, xp_awarded = 0 "
            "WHERE id = :sid AND status = 'active'"
        ),
        {"sid": sess["id"]},
    )
    await db.commit()

    return {
        "cancelled": True,
        "session_id": sess["id"],
        "stamina_refunded": int(refund),
    }


async def cancel_gathering_internal(
    db: AsyncSession,
    *,
    character_id: int,
) -> Dict:
    """Internal cancel — called by battle-service when a battle starts.

    Idempotent: if no active session exists, returns
    `{cancelled: False, reason: 'no_active_session'}` rather than raising.
    """
    sess = await _lock_active_session_for_character(
        db, character_id=character_id, node_id=None,
    )
    if sess is None:
        return {"cancelled": False, "reason": "no_active_session"}

    refund = _compute_refund(sess["stamina_paid"])
    refund_ok = await _refund_stamina_via_attributes(
        character_id=character_id, amount=refund,
    )
    if not refund_ok:
        logger.warning(
            "Stamina refund failed for char %s session %s "
            "(internal cancel) — cancel proceeding",
            character_id, sess["id"],
        )

    await db.execute(
        text(
            "UPDATE gathering_sessions "
            "SET status = 'interrupted_by_battle', finished_at = NOW(), "
            "    result_quantity = 0, xp_awarded = 0 "
            "WHERE id = :sid AND status = 'active'"
        ),
        {"sid": sess["id"]},
    )
    await db.commit()

    return {
        "cancelled": True,
        "session_id": sess["id"],
        "stamina_refunded": int(refund),
    }


# ---------------------------------------------------------------------------
# FEAT-128 task #16 — poll active gathering for a character
# ---------------------------------------------------------------------------
# Strategy for `last_finished_session`: when `finalize_due_sessions` finalizes
# any sessions for THIS character during this very request, we surface the
# most recent one as `last_finished_session`. On subsequent polls,
# `finalize_due_sessions` is a no-op (no due sessions remain) so the field
# returns null — the client only ever sees a completion toast once.

async def get_active_gathering_for_character(
    db: AsyncSession,
    character_id: int,
) -> Dict:
    """Fetch the active (or just-finalized) gathering session for a character.

    Flow:
      1. Run `finalize_due_sessions` filtered to this character. Capture any
         summaries it produced — those are sessions that finished during
         THIS request and should be surfaced as `last_finished_session`.
      2. SELECT the most recent active session for the character (if any).
      3. Build the response shape per FEAT-128 §3.1.1.
    """
    # 1. Lazy-finalize any due sessions for this character. May commit.
    finalized: List[Dict] = []
    try:
        finalized = await finalize_due_sessions(
            db, character_id=character_id,
        )
    except Exception as exc:
        logger.warning(
            "finalize_due_sessions(%s) failed during poll, continuing: %s",
            character_id, exc,
        )
        finalized = []

    # 2. Query the most-recent active session (if any).
    row = (
        await db.execute(
            text(
                "SELECT s.id, s.node_id, s.started_at, s.complete_at, "
                "       s.stamina_paid, s.tool_inventory_item_id, "
                "       s.effective_speed_bonus_pct, "
                "       s.effective_double_chance_pct, "
                "       s.effective_stamina_bonus_pct, "
                "       n.node_name, n.location_id "
                "FROM gathering_sessions s "
                "JOIN gathering_nodes n ON n.id = s.node_id "
                "WHERE s.character_id = :cid AND s.status = 'active' "
                "ORDER BY s.started_at DESC LIMIT 1"
            ),
            {"cid": int(character_id)},
        )
    ).fetchone()

    # Flat top-level payload (FEAT-128 §3.1.1, fix Review #1 issue #1).
    # Active-only fields are populated only when there's an active session;
    # otherwise they are absent from the dict and Pydantic will default them
    # to None on the response model.
    active_fields: Dict = {}
    if row is not None:
        complete_at = _ensure_aware_utc(row.complete_at)
        now = datetime.now(timezone.utc)
        if complete_at is not None:
            remaining_seconds = max(
                0, int((complete_at - now).total_seconds())
            )
        else:
            remaining_seconds = 0
        active_fields = {
            "session_id": int(row.id),
            "node_id": int(row.node_id),
            "node_name": str(row.node_name or ""),
            "location_id": (
                int(row.location_id) if row.location_id is not None else None
            ),
            "started_at": _ensure_aware_utc(row.started_at),
            "complete_at": _ensure_aware_utc(row.complete_at),
            "remaining_seconds": int(remaining_seconds),
            "stamina_paid": int(row.stamina_paid or 0),
            "tool_inventory_item_id": (
                int(row.tool_inventory_item_id)
                if row.tool_inventory_item_id is not None
                else None
            ),
            "effective_speed_bonus_pct": float(
                row.effective_speed_bonus_pct or 0.0
            ),
            "effective_double_chance_pct": float(
                row.effective_double_chance_pct or 0.0
            ),
            "effective_stamina_bonus_pct": float(
                row.effective_stamina_bonus_pct or 0.0
            ),
        }

    # Build last_finished_session from the in-request finalize summaries
    # (if any). Pick the most recent by session_id (later id == later start
    # in practice for a single character). Field names match
    # `LastFinishedSessionInfo` schema and frontend `FinishedGatheringSummary`.
    last_finished_payload: Optional[Dict] = None
    if finalized:
        # Some entries (e.g. node-deleted branch) may have status='cancelled'
        # but still belong to this character — surface them too. Filter to
        # this character to be defensive (finalize_due_sessions was already
        # filtered, but the helper is shared with other callers).
        my_finals = [
            s for s in finalized
            if s.get("character_id") == int(character_id)
        ]
        if my_finals:
            latest = max(my_finals, key=lambda s: int(s.get("session_id", 0)))
            rank_up_to_val = latest.get("rank_up_to")
            tdr_val = latest.get("tool_durability_remaining")
            last_finished_payload = {
                "session_id": int(latest.get("session_id")),
                "node_id": (
                    int(latest["node_id"])
                    if latest.get("node_id") is not None
                    else None
                ),
                "node_name": latest.get("node_name") or "",
                "result_item_id": latest.get("result_item_id"),
                "result_item_name": latest.get("result_item_name"),
                "result_quantity": int(latest.get("result_quantity") or 0),
                "xp_gained": int(latest.get("xp_gained") or 0),
                "skill_slug": latest.get("skill_slug"),
                "rank_up_to": (
                    int(rank_up_to_val) if rank_up_to_val is not None else None
                ),
                "tool_durability_remaining": (
                    int(tdr_val) if tdr_val is not None else None
                ),
                "tool_broke": bool(latest.get("tool_broke") or False),
                "status": str(latest.get("status") or "completed"),
            }

    return {
        "active": row is not None,
        **active_fields,
        "last_finished_session": last_finished_payload,
    }


