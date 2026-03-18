"""
Tests for photo-service CRUD functions after ORM migration (FEAT-034).

Verifies that all crud.py functions correctly interact with SQLAlchemy
Session objects — querying, filtering, updating, and committing.
"""

from unittest.mock import MagicMock, patch, PropertyMock
from sqlalchemy.orm import Session

import crud
from models import (
    User, Character, Country, Region, District,
    Location, Skill, SkillRank, Item, GameRule,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db_with_result(model_instance):
    """Create a mock Session where .query(...).filter(...).first() returns model_instance."""
    db = MagicMock(spec=Session)
    query = MagicMock()
    db.query.return_value = query
    query.filter.return_value = query
    query.first.return_value = model_instance
    return db


def _mock_db_not_found():
    """Create a mock Session where .query(...).filter(...).first() returns None."""
    return _mock_db_with_result(None)


# ===========================================================================
# 1. get_character_owner_id
# ===========================================================================

class TestGetCharacterOwnerId:

    def test_returns_user_id_when_found(self):
        char = MagicMock(spec=Character)
        char.user_id = 42
        db = _mock_db_with_result(char)

        result = crud.get_character_owner_id(db, character_id=7)

        assert result == 42
        db.query.assert_called_once_with(Character)

    def test_returns_none_when_not_found(self):
        db = _mock_db_not_found()

        result = crud.get_character_owner_id(db, character_id=9999)

        assert result is None


# ===========================================================================
# 2. update_user_avatar / get_user_avatar
# ===========================================================================

class TestUserAvatar:

    def test_update_user_avatar_sets_field_and_commits(self):
        user = MagicMock(spec=User)
        db = _mock_db_with_result(user)

        crud.update_user_avatar(db, user_id=1, avatar_url="https://s3.example.com/avatar.webp")

        assert user.avatar == "https://s3.example.com/avatar.webp"
        db.commit.assert_called_once()

    def test_update_user_avatar_no_commit_when_not_found(self):
        db = _mock_db_not_found()

        crud.update_user_avatar(db, user_id=9999, avatar_url="https://s3.example.com/avatar.webp")

        db.commit.assert_not_called()

    def test_get_user_avatar_returns_url(self):
        user = MagicMock(spec=User)
        user.avatar = "https://s3.example.com/avatar.webp"
        db = _mock_db_with_result(user)

        result = crud.get_user_avatar(db, user_id=1)

        assert result == "https://s3.example.com/avatar.webp"

    def test_get_user_avatar_returns_none_when_not_found(self):
        db = _mock_db_not_found()

        result = crud.get_user_avatar(db, user_id=9999)

        assert result is None


# ===========================================================================
# 3. update_character_avatar / get_character_avatar
# ===========================================================================

class TestCharacterAvatar:

    def test_update_character_avatar_sets_field_and_commits(self):
        char = MagicMock(spec=Character)
        db = _mock_db_with_result(char)

        crud.update_character_avatar(db, character_id=5, avatar_url="https://s3.example.com/char.webp", user_id=42)

        assert char.avatar == "https://s3.example.com/char.webp"
        db.commit.assert_called_once()

    def test_update_character_avatar_no_commit_when_not_found(self):
        db = _mock_db_not_found()

        crud.update_character_avatar(db, character_id=9999, avatar_url="url", user_id=1)

        db.commit.assert_not_called()

    def test_get_character_avatar_returns_url(self):
        char = MagicMock(spec=Character)
        char.avatar = "https://s3.example.com/char.webp"
        db = _mock_db_with_result(char)

        result = crud.get_character_avatar(db, character_id=5)

        assert result == "https://s3.example.com/char.webp"

    def test_get_character_avatar_returns_none_when_not_found(self):
        db = _mock_db_not_found()

        result = crud.get_character_avatar(db, character_id=9999)

        assert result is None


# ===========================================================================
# 4. Location-related updates (country, region, district, location)
# ===========================================================================

class TestLocationUpdates:

    def test_update_country_map_image(self):
        country = MagicMock(spec=Country)
        db = _mock_db_with_result(country)

        crud.update_country_map_image(db, country_id=1, map_url="https://s3.example.com/map.webp")

        assert country.map_image_url == "https://s3.example.com/map.webp"
        db.commit.assert_called_once()

    def test_update_country_map_image_not_found(self):
        db = _mock_db_not_found()
        crud.update_country_map_image(db, country_id=999, map_url="url")
        db.commit.assert_not_called()

    def test_update_region_map_image(self):
        region = MagicMock(spec=Region)
        db = _mock_db_with_result(region)

        crud.update_region_map_image(db, region_id=2, map_url="https://s3.example.com/rmap.webp")

        assert region.map_image_url == "https://s3.example.com/rmap.webp"
        db.commit.assert_called_once()

    def test_update_region_image(self):
        region = MagicMock(spec=Region)
        db = _mock_db_with_result(region)

        crud.update_region_image(db, region_id=3, image_url="https://s3.example.com/rimg.webp")

        assert region.image_url == "https://s3.example.com/rimg.webp"
        db.commit.assert_called_once()

    def test_update_district_image(self):
        district = MagicMock(spec=District)
        db = _mock_db_with_result(district)

        crud.update_district_image(db, district_id=4, image_url="https://s3.example.com/dist.webp")

        assert district.image_url == "https://s3.example.com/dist.webp"
        db.commit.assert_called_once()

    def test_update_location_image(self):
        location = MagicMock(spec=Location)
        db = _mock_db_with_result(location)

        crud.update_location_image(db, location_id=5, image_url="https://s3.example.com/loc.webp")

        assert location.image_url == "https://s3.example.com/loc.webp"
        db.commit.assert_called_once()


# ===========================================================================
# 5. Skill / SkillRank / Item / GameRule updates
# ===========================================================================

class TestSkillAndItemUpdates:

    def test_update_skill_image(self):
        skill = MagicMock(spec=Skill)
        db = _mock_db_with_result(skill)

        crud.update_skill_image(db, skill_id=10, image_url="https://s3.example.com/skill.webp")

        assert skill.skill_image == "https://s3.example.com/skill.webp"
        db.commit.assert_called_once()

    def test_update_skill_image_not_found(self):
        db = _mock_db_not_found()
        crud.update_skill_image(db, skill_id=999, image_url="url")
        db.commit.assert_not_called()

    def test_update_skill_rank_image(self):
        rank = MagicMock(spec=SkillRank)
        db = _mock_db_with_result(rank)

        crud.update_skill_rank_image(db, skill_rank_id=20, image_url="https://s3.example.com/rank.webp")

        assert rank.rank_image == "https://s3.example.com/rank.webp"
        db.commit.assert_called_once()

    def test_update_item_image(self):
        item = MagicMock(spec=Item)
        db = _mock_db_with_result(item)

        crud.update_item_image(db, item_id=30, image_url="https://s3.example.com/item.webp")

        assert item.image == "https://s3.example.com/item.webp"
        db.commit.assert_called_once()

    def test_update_rule_image(self):
        rule = MagicMock(spec=GameRule)
        db = _mock_db_with_result(rule)

        crud.update_rule_image(db, rule_id=5, image_url="https://s3.example.com/rule.webp")

        assert rule.image_url == "https://s3.example.com/rule.webp"
        db.commit.assert_called_once()


# ===========================================================================
# 6. Profile background
# ===========================================================================

class TestProfileBackground:

    def test_update_profile_bg_image(self):
        user = MagicMock(spec=User)
        db = _mock_db_with_result(user)

        crud.update_profile_bg_image(db, user_id=1, image_url="https://s3.example.com/bg.webp")

        assert user.profile_bg_image == "https://s3.example.com/bg.webp"
        db.commit.assert_called_once()

    def test_update_profile_bg_image_to_none(self):
        user = MagicMock(spec=User)
        user.profile_bg_image = "https://s3.example.com/old.webp"
        db = _mock_db_with_result(user)

        crud.update_profile_bg_image(db, user_id=1, image_url=None)

        assert user.profile_bg_image is None
        db.commit.assert_called_once()

    def test_get_profile_bg_image_returns_url(self):
        user = MagicMock(spec=User)
        user.profile_bg_image = "https://s3.example.com/bg.webp"
        db = _mock_db_with_result(user)

        result = crud.get_profile_bg_image(db, user_id=1)

        assert result == "https://s3.example.com/bg.webp"

    def test_get_profile_bg_image_returns_none_when_not_found(self):
        db = _mock_db_not_found()

        result = crud.get_profile_bg_image(db, user_id=9999)

        assert result is None
