from sqlalchemy.orm import Session
from models import (
    User, Character, Area, Country, Region, District,
    Location, Skill, SkillRank, Item, GameRule, Race, Subrace,
)


def get_character_owner_id(db: Session, character_id: int):
    """Returns user_id of character owner, or None if not found."""
    character = db.query(Character).filter(Character.id == character_id).first()
    return character.user_id if character else None


def update_user_avatar(db: Session, user_id: int, avatar_url: str):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.avatar = avatar_url
        db.commit()


def get_user_avatar(db: Session, user_id: int):
    user = db.query(User).filter(User.id == user_id).first()
    return user.avatar if user else None


def update_character_avatar(db: Session, character_id: int, avatar_url: str, user_id: int):
    character = db.query(Character).filter(Character.id == character_id).first()
    if character:
        character.avatar = avatar_url
        db.commit()


def get_character_avatar(db: Session, character_id: int):
    character = db.query(Character).filter(Character.id == character_id).first()
    return character.avatar if character else None


def update_area_map_image(db: Session, area_id: int, map_url: str):
    area = db.query(Area).filter(Area.id == area_id).first()
    if area:
        area.map_image_url = map_url
        db.commit()


# 1) Обновляем map_image_url в таблице Countries
def update_country_map_image(db: Session, country_id: int, map_url: str):
    country = db.query(Country).filter(Country.id == country_id).first()
    if country:
        country.map_image_url = map_url
        db.commit()


def update_country_emblem(db: Session, country_id: int, emblem_url: str):
    country = db.query(Country).filter(Country.id == country_id).first()
    if country:
        country.emblem_url = emblem_url
        db.commit()


# 2) Обновляем map_image_url в таблице Regions
def update_region_map_image(db: Session, region_id: int, map_url: str):
    region = db.query(Region).filter(Region.id == region_id).first()
    if region:
        region.map_image_url = map_url
        db.commit()


# 3) Обновляем image_url в таблице Regions
def update_region_image(db: Session, region_id: int, image_url: str):
    region = db.query(Region).filter(Region.id == region_id).first()
    if region:
        region.image_url = image_url
        db.commit()


# 4) Обновляем image_url в таблице Districts
def update_district_image(db: Session, district_id: int, image_url: str):
    district = db.query(District).filter(District.id == district_id).first()
    if district:
        district.image_url = image_url
        db.commit()


# 4b) Обновляем map_icon_url в таблице Districts
def update_district_icon(db: Session, district_id: int, icon_url: str):
    district = db.query(District).filter(District.id == district_id).first()
    if district:
        district.map_icon_url = icon_url
        db.commit()


# 4c) Обновляем map_image_url в таблице Districts
def update_district_map_image(db: Session, district_id: int, map_url: str):
    district = db.query(District).filter(District.id == district_id).first()
    if district:
        district.map_image_url = map_url
        db.commit()


# 5) Обновляем image_url в таблице Locations
def update_location_image(db: Session, location_id: int, image_url: str):
    location = db.query(Location).filter(Location.id == location_id).first()
    if location:
        location.image_url = image_url
        db.commit()


# 6) Обновляем map_icon_url в таблице Locations
def update_location_icon(db: Session, location_id: int, icon_url: str):
    location = db.query(Location).filter(Location.id == location_id).first()
    if location:
        location.map_icon_url = icon_url
        db.commit()


def update_skill_image(db: Session, skill_id: int, image_url: str):
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if skill:
        skill.skill_image = image_url
        db.commit()


def update_skill_rank_image(db: Session, skill_rank_id: int, image_url: str):
    rank = db.query(SkillRank).filter(SkillRank.id == skill_rank_id).first()
    if rank:
        rank.rank_image = image_url
        db.commit()


def update_item_image(db: Session, item_id: int, image_url: str):
    item = db.query(Item).filter(Item.id == item_id).first()
    if item:
        item.image = image_url
        db.commit()


def update_rule_image(db: Session, rule_id: int, image_url: str):
    rule = db.query(GameRule).filter(GameRule.id == rule_id).first()
    if rule:
        rule.image_url = image_url
        db.commit()


def update_profile_bg_image(db: Session, user_id: int, image_url):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.profile_bg_image = image_url
        db.commit()


def get_profile_bg_image(db: Session, user_id: int):
    user = db.query(User).filter(User.id == user_id).first()
    return user.profile_bg_image if user else None


def update_race_image(db: Session, race_id: int, image_url: str):
    race = db.query(Race).filter(Race.id_race == race_id).first()
    if race:
        race.image = image_url
        db.commit()


def update_subrace_image(db: Session, subrace_id: int, image_url: str):
    subrace = db.query(Subrace).filter(Subrace.id_subrace == subrace_id).first()
    if subrace:
        subrace.image = image_url
        db.commit()
