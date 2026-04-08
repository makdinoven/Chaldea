"""
(FEAT-125) Smoke test for the mob_template_skills migration shape.

Verifies the post-FEAT-125 model state:
- character_service.models.MobTemplateSkill exposes a `skill_id` column
  (and no longer `skill_rank_id`)
- The unique constraint pair is `(mob_template_id, skill_id)`
- crud.send_skills_presets_request builds an HTTP body without `rank_number`
"""

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Required env stubs (config.py reads these at import).
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "user")
os.environ.setdefault("DB_PASSWORD", "pass")
os.environ.setdefault("DB_DATABASE", "db")

import models  # noqa: E402
import crud  # noqa: E402


class TestMobTemplateSkillsModelShape:

    def test_model_has_skill_id_column(self):
        cols = {c.name for c in models.MobTemplateSkill.__table__.columns}
        assert "skill_id" in cols
        assert "skill_rank_id" not in cols

    def test_unique_constraint_uses_skill_id(self):
        from sqlalchemy import UniqueConstraint
        uqs = [
            c for c in models.MobTemplateSkill.__table__.constraints
            if isinstance(c, UniqueConstraint)
        ]
        assert uqs, "MobTemplateSkill has no UniqueConstraint"
        cols = {col.name for uq in uqs for col in uq.columns}
        assert "mob_template_id" in cols
        assert "skill_id" in cols
        assert "skill_rank_id" not in cols

    def test_skill_id_is_integer_not_null(self):
        col = models.MobTemplateSkill.__table__.c.skill_id
        assert col.nullable is False
        # FK to skills.id is created at the DB level by Alembic 016 (cross-service
        # table — character-service models do not import the Skill ORM class).


class TestSendSkillsPresetsRequestBody:
    """crud.send_skills_presets_request must omit rank_number after FEAT-125."""

    @pytest.mark.asyncio
    async def test_body_uses_skill_id_only(self):
        import asyncio
        captured = {}

        class _Resp:
            status_code = 200
            def json(self_inner):
                return {}

        class _AsyncClientStub:
            def __init__(self_inner, *a, **kw):
                pass
            async def __aenter__(self_inner):
                return self_inner
            async def __aexit__(self_inner, *a):
                return False
            async def post(self_inner, url, json=None):
                captured["url"] = url
                captured["json"] = json
                return _Resp()

        with patch("crud.httpx.AsyncClient", _AsyncClientStub):
            await crud.send_skills_presets_request(character_id=42, skill_ids=[1, 2, 3])

        body = captured["json"]
        assert body["character_id"] == 42
        assert "skills" in body
        for entry in body["skills"]:
            assert "skill_id" in entry
            assert "rank_number" not in entry
        assert {e["skill_id"] for e in body["skills"]} == {1, 2, 3}
