from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
from sqlalchemy.orm import selectinload
from sqlalchemy import text, delete

from models import (
    Country, Region, District, Location, LocationNeighbor, Post
)
from schemas import (
    DistrictCreate, LocationCreate, PostCreate, LocationNeighborCreate
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

    # Получаем все локации для региона одним запросом
    locations_result = await session.execute(
        select(Location)
        .where(Location.district_id.in_([d.id for d in region.districts]))
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
            "locations": district_root_locations
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
        "districts": districts_data
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
        image_url=district.image_url or ""  # Используем пустую строку вместо None
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