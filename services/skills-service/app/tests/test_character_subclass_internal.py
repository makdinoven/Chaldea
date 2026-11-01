"""
FEAT-188 #5 (QA) — skills-service: subclass passives foundation.

Covers:
  * ``GET /skills/internal/characters/{character_id}/subclass`` — the official
    "which subclass does this character have" lookup used by battle-service.
      - auth matrix (``X-Internal-Token`` only; Bearer with the same secret is
        rejected; empty env -> 503 per ``verify_internal_token``);
      - REAL data: a test ``characters`` table with ``is_npc`` (as in prod,
        character-service ``models.Character.is_npc``) and real
        ``tree_nodes`` / ``character_tree_progress`` rows with
        ``node_type='subclass_choice'`` — the crud functions are NOT mocked,
        so a wrong column / wrong node_type literal fails these tests;
      - 404 / 422 / route order.
  * ``GET /skills/subclasses`` — every registry entry carries a ``passive``,
    all 21 passives are implemented (FEAT-190 wave 2), class filter.
  * The in-process registry (``subclasses.py``) itself, incl. the FEAT-189
    description fixes (Inquisitor non-physical resists, "duel" wording replaced
    for Gladiator/Mechanic/Sparkmage) and the FEAT-190 description updates
    (Berserk lifesteal below 25%, Trickster redirect to the attacker's ally at
    50%, Necromancer kill = heal 10%, Paladin most recent removable effect,
    «Если союзников нет» for Bard/Etheriad/Auromancer).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ---------------------------------------------------------------------------
# Async SQLite engine, wired in before main is imported
# ---------------------------------------------------------------------------

_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
)
_Session = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)

import database  # noqa: E402

database.engine = _engine
database.async_session = _Session


async def _override_get_db():
    async with _Session() as session:
        yield session


import auth_http  # noqa: E402
import models  # noqa: E402
import subclasses as subclass_registry  # noqa: E402
import main as main_module  # noqa: E402
from main import app  # noqa: E402

app.router.on_startup.clear()

_GET_DB_KEY = main_module.get_db

TOKEN = "test-internal-token-feat188"
GOOD_HEADERS = {"X-Internal-Token": TOKEN}

# Character ids
BERSERKER = 101          # chose a regular node + the berserker subclass_choice node
NO_SUBCLASS = 102        # chose only a regular node
FRESH = 103              # no tree progress at all
NPC = 104                # is_npc = 1, no progress
UNKNOWN_KEY = 105        # chose a subclass_choice node whose key is not in the registry
TWO_CHOICES = 106        # chose two subclass_choice nodes -> latest (max ctp.id) wins
NULL_KEY_CHOICE = 107    # chose a subclass_choice node with subclass_key NULL
KEY_ON_REGULAR = 108     # chose a *regular* node that (wrongly) has a subclass_key
NPC_WITH_SUBCLASS = 109  # NPC that has a subclass_choice row (data is still returned)
MISSING = 99999

# FEAT-190: all 21 passives are live in battle-service — rage (FEAT-188),
# the 13 wave-1 passives (FEAT-189) and the 7 wave-2 passives (FEAT-190).
IMPLEMENTED_PASSIVE_KEYS = {
    "berserker_rage",
    "inquisitor_heresy_seal",
    "saber_monster_hunter",
    "gladiator_arena",
    "agent_weak_spot",
    "lancer_pin",
    "mechanic_shrapnel",
    "archer_first_blood",
    "assassin_from_shadow",
    "trickster_deceit",
    "monk_harmony",
    "salamander_kindling",
    "caster_pure_energy",
    "sparkmage_chain_lightning",
    # FEAT-190 wave 2 (shields / lifesteal / reflect / blood price / ally buffs)
    "paladin_sacred_vow",
    "guardian_retribution",
    "bard_rhythm",
    "necromancer_blood_price",
    "etheriad_spirit_whisper",
    "auromancer_tide",
    "priest_faith",
}


def _path(cid) -> str:
    return f"/skills/internal/characters/{cid}/subclass"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _token_is_configured(monkeypatch):
    # auth_http reads the secret into a module constant at import time.
    monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", TOKEN)


@pytest_asyncio.fixture()
async def seeded():
    async with _engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
        # characters is owned by character-service; mirror the prod columns
        # that matter here, including is_npc (Boolean NOT NULL default 0).
        await conn.execute(text("DROP TABLE IF EXISTS characters"))
        await conn.execute(text(
            "CREATE TABLE characters ("
            "  id INTEGER PRIMARY KEY,"
            "  name VARCHAR(255),"
            "  user_id INTEGER NULL,"
            "  is_npc BOOLEAN NOT NULL DEFAULT 0"
            ")"
        ))
        for cid, is_npc in [
            (BERSERKER, 0), (NO_SUBCLASS, 0), (FRESH, 0), (NPC, 1),
            (UNKNOWN_KEY, 0), (TWO_CHOICES, 0), (NULL_KEY_CHOICE, 0),
            (KEY_ON_REGULAR, 0), (NPC_WITH_SUBCLASS, 1),
        ]:
            await conn.execute(
                text("INSERT INTO characters (id, name, user_id, is_npc) "
                     "VALUES (:i, 'C', :u, :n)"),
                {"i": cid, "u": None if is_npc else 1, "n": is_npc},
            )

    async with _Session() as s:
        tree = models.ClassSkillTree(class_id=1, name="Воин", tree_type="class")
        s.add(tree)
        await s.flush()

        def node(name, node_type, key=None, ring=1):
            return models.TreeNode(tree_id=tree.id, level_ring=ring, name=name,
                                   node_type=node_type, subclass_key=key)

        regular = node("Удар", "regular")
        berserk = node("Берсерк", "subclass_choice", "warrior_berserker", 30)
        paladin = node("Паладин", "subclass_choice", "warrior_paladin", 30)
        bogus = node("???", "subclass_choice", "no_such_subclass", 30)
        null_key = node("Без ключа", "subclass_choice", None, 30)
        regular_with_key = node("Обычный", "regular", "warrior_paladin", 5)
        s.add_all([regular, berserk, paladin, bogus, null_key, regular_with_key])
        await s.flush()

        def prog(cid, n):
            return models.CharacterTreeProgress(character_id=cid, tree_id=tree.id,
                                                node_id=n.id)

        # Insert order matters for TWO_CHOICES: paladin first, berserker later.
        rows = [
            prog(BERSERKER, regular),
            prog(BERSERKER, berserk),
            prog(NO_SUBCLASS, regular),
            prog(UNKNOWN_KEY, bogus),
            prog(TWO_CHOICES, paladin),
        ]
        for r in rows:
            s.add(r)
            await s.flush()
        s.add(prog(TWO_CHOICES, berserk))
        await s.flush()
        s.add_all([
            prog(NULL_KEY_CHOICE, null_key),
            prog(KEY_ON_REGULAR, regular_with_key),
            prog(NPC_WITH_SUBCLASS, berserk),
        ])
        await s.commit()
    yield
    async with _engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS characters"))
        await conn.run_sync(models.Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def client(seeded):
    app.dependency_overrides[_GET_DB_KEY] = _override_get_db
    async with httpx.AsyncClient(transport=ASGITransport(app=app),
                                 base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ══════════════════════════════════════════════════════════════════════════════
# 1. Auth matrix
# ══════════════════════════════════════════════════════════════════════════════


class TestInternalSubclassAuth:
    async def test_correct_internal_token_returns_200(self, client):
        resp = await client.get(_path(BERSERKER), headers=GOOD_HEADERS)
        assert resp.status_code == 200, resp.text

    async def test_no_header_returns_401(self, client):
        resp = await client.get(_path(BERSERKER))
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Недействительный internal token"

    async def test_same_secret_as_bearer_is_rejected(self, client):
        """The trap from §3.2: battle-service must not reuse _service_headers()."""
        resp = await client.get(_path(BERSERKER),
                                headers={"Authorization": f"Bearer {TOKEN}"})
        assert resp.status_code == 401

    async def test_wrong_token_returns_401(self, client):
        resp = await client.get(_path(BERSERKER),
                                headers={"X-Internal-Token": "not-the-token"})
        assert resp.status_code == 401

    async def test_empty_header_value_returns_401(self, client):
        resp = await client.get(_path(BERSERKER), headers={"X-Internal-Token": ""})
        assert resp.status_code == 401

    async def test_token_in_wrong_header_name_returns_401(self, client):
        resp = await client.get(_path(BERSERKER), headers={"X-Service-Token": TOKEN})
        assert resp.status_code == 401

    async def test_empty_env_token_fails_closed_with_503(self, client, monkeypatch):
        monkeypatch.setattr(auth_http, "INTERNAL_SERVICE_TOKEN", "")
        resp = await client.get(_path(BERSERKER), headers={"X-Internal-Token": ""})
        assert resp.status_code == 503
        resp = await client.get(_path(BERSERKER), headers=GOOD_HEADERS)
        assert resp.status_code == 503

    async def test_auth_checked_before_existence(self, client):
        """No header + unknown id -> 401, not 404 (no id probing without token)."""
        resp = await client.get(_path(MISSING))
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# 2. Real returned values
# ══════════════════════════════════════════════════════════════════════════════


async def _get(client, cid):
    resp = await client.get(_path(cid), headers=GOOD_HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestInternalSubclassData:
    async def test_berserker_full_payload(self, client):
        body = await _get(client, BERSERKER)
        assert body["character_id"] == BERSERKER
        assert body["is_npc"] is False
        assert body["subclass_key"] == "warrior_berserker"
        assert body["subclass_name"] == "Берсерк"
        passive = body["passive"]
        assert set(passive) == {"key", "name", "description", "implemented"}
        assert passive["key"] == "berserker_rage"
        assert passive["name"] == "Ярость"
        assert passive["implemented"] is True
        expected = subclass_registry.get_passive_for_subclass("warrior_berserker")
        assert passive["description"] == expected.description
        assert passive["description"].strip()

    async def test_response_has_exact_contract_fields(self, client):
        body = await _get(client, BERSERKER)
        assert set(body) == {"character_id", "is_npc", "subclass_key",
                             "subclass_name", "passive"}

    async def test_only_regular_node_chosen_returns_nulls(self, client):
        body = await _get(client, NO_SUBCLASS)
        assert body == {"character_id": NO_SUBCLASS, "is_npc": False,
                        "subclass_key": None, "subclass_name": None, "passive": None}

    async def test_no_progress_at_all_returns_nulls(self, client):
        body = await _get(client, FRESH)
        assert body["subclass_key"] is None
        assert body["subclass_name"] is None
        assert body["passive"] is None
        assert body["is_npc"] is False

    async def test_npc_flag_true(self, client):
        body = await _get(client, NPC)
        assert body["is_npc"] is True
        assert body["subclass_key"] is None
        assert body["passive"] is None

    async def test_npc_with_subclass_row_still_reports_is_npc(self, client):
        """skills-service reports facts; dropping the passive for NPCs is
        battle-service's job (D6)."""
        body = await _get(client, NPC_WITH_SUBCLASS)
        assert body["is_npc"] is True
        assert body["subclass_key"] == "warrior_berserker"

    async def test_unknown_registry_key_keeps_key_but_no_passive(self, client):
        body = await _get(client, UNKNOWN_KEY)
        assert body["subclass_key"] == "no_such_subclass"
        assert body["subclass_name"] is None
        assert body["passive"] is None

    async def test_latest_subclass_choice_wins(self, client):
        body = await _get(client, TWO_CHOICES)
        assert body["subclass_key"] == "warrior_berserker"
        assert body["passive"]["key"] == "berserker_rage"

    async def test_subclass_choice_with_null_key_is_ignored(self, client):
        body = await _get(client, NULL_KEY_CHOICE)
        assert body["subclass_key"] is None
        assert body["passive"] is None

    async def test_key_on_non_subclass_node_is_ignored(self, client):
        """node_type filter is real: a regular node with a stray key is not a subclass."""
        body = await _get(client, KEY_ON_REGULAR)
        assert body["subclass_key"] is None
        assert body["passive"] is None

    async def test_characters_are_isolated(self, client):
        """Berserker's progress must not leak into another character."""
        assert (await _get(client, NO_SUBCLASS))["subclass_key"] is None
        assert (await _get(client, BERSERKER))["subclass_key"] == "warrior_berserker"


# ══════════════════════════════════════════════════════════════════════════════
# 3. 404 / 422 / route order
# ══════════════════════════════════════════════════════════════════════════════


class TestInternalSubclassValidation:
    async def test_missing_character_returns_404(self, client):
        resp = await client.get(_path(MISSING), headers=GOOD_HEADERS)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Персонаж не найден"

    @pytest.mark.parametrize("cid", [0, -1])
    async def test_non_positive_id_returns_404(self, client, cid):
        resp = await client.get(_path(cid), headers=GOOD_HEADERS)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Персонаж не найден"

    @pytest.mark.parametrize("cid", ["abc", "1.5", "1%20OR%201=1",
                                     "1';DROP%20TABLE%20characters;--"])
    async def test_non_int_id_returns_422(self, client, cid):
        resp = await client.get(_path(cid), headers=GOOD_HEADERS)
        assert resp.status_code == 422

    async def test_sql_ish_id_does_not_damage_table(self, client):
        await client.get(_path("1';DROP%20TABLE%20characters;--"), headers=GOOD_HEADERS)
        body = await _get(client, BERSERKER)
        assert body["subclass_key"] == "warrior_berserker"

    async def test_route_registered_before_generic_skill_id(self):
        paths = [getattr(r, "path", None) for r in app.routes]
        internal = paths.index("/skills/internal/characters/{character_id}/subclass")
        generic = paths.index("/skills/{skill_id}")
        assert internal < generic

    async def test_route_handled_by_internal_endpoint(self, client):
        """Response is the subclass contract, not a skill / skill-404 body."""
        body = await _get(client, BERSERKER)
        assert "character_id" in body and "skill_type" not in body
        resp = await client.get(_path(MISSING), headers=GOOD_HEADERS)
        assert resp.json()["detail"] == "Персонаж не найден"


# ══════════════════════════════════════════════════════════════════════════════
# 4. Public registry: GET /skills/subclasses and subclasses.py
# ══════════════════════════════════════════════════════════════════════════════


class TestSubclassRegistryEndpoint:
    async def test_all_21_with_passive(self, client):
        resp = await client.get("/skills/subclasses")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 21
        for item in items:
            assert set(item) == {"key", "class_id", "name", "description", "passive"}
            p = item["passive"]
            assert set(p) == {"key", "name", "description", "implemented"}
            assert p["key"] and p["name"] and p["description"].strip()
            assert isinstance(p["implemented"], bool)

    async def test_all_21_passives_implemented(self, client):
        items = (await client.get("/skills/subclasses")).json()
        implemented = {i["passive"]["key"] for i in items if i["passive"]["implemented"]}
        assert implemented == IMPLEMENTED_PASSIVE_KEYS
        assert len(implemented) == 21
        not_implemented = {i["passive"]["key"] for i in items if not i["passive"]["implemented"]}
        assert not_implemented == set()
        # Strict bool True on the wire, not just truthy.
        assert all(i["passive"]["implemented"] is True for i in items)
        berserk = next(i for i in items if i["key"] == "warrior_berserker")
        assert berserk["passive"]["key"] == "berserker_rage"
        assert berserk["passive"]["name"] == "Ярость"

    async def test_passive_keys_unique(self, client):
        items = (await client.get("/skills/subclasses")).json()
        keys = [i["passive"]["key"] for i in items]
        assert len(set(keys)) == 21

    @pytest.mark.parametrize("class_id", [1, 2, 3])
    async def test_class_filter_returns_7(self, client, class_id):
        resp = await client.get(f"/skills/subclasses?class_id={class_id}")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 7
        assert all(i["class_id"] == class_id for i in items)
        assert all(i["passive"] is not None for i in items)

    async def test_registry_needs_no_token(self, client):
        assert (await client.get("/skills/subclasses")).status_code == 200


class TestSubclassRegistryModule:
    def test_every_subclass_has_passive(self):
        assert len(subclass_registry.SUBCLASSES) == 21
        for s in subclass_registry.SUBCLASSES:
            assert isinstance(s.passive, subclass_registry.PassiveDef)

    def test_get_passive_for_subclass(self):
        p = subclass_registry.get_passive_for_subclass("warrior_berserker")
        assert p.key == "berserker_rage" and p.implemented is True
        assert subclass_registry.get_passive_for_subclass(None) is None
        assert subclass_registry.get_passive_for_subclass("") is None
        assert subclass_registry.get_passive_for_subclass("no_such") is None

    def test_berserk_description_has_lifesteal_below_25(self):
        """FEAT-190: Berserk rage gains lifesteal 15% below 25% HP
        (reverses the FEAT-188 "rage only, no vampirism" wording)."""
        d = subclass_registry.get_passive_for_subclass("warrior_berserker").description
        assert "вампиризм" in d.lower()
        assert "Ниже 25% здоровья" in d
        assert "15%" in d

    # --- FEAT-189/190: registry flags + description fixes ----------------------

    def test_module_all_21_implemented(self):
        flags = {s.passive.key: s.passive.implemented for s in subclass_registry.SUBCLASSES}
        assert len(flags) == 21
        assert {k for k, v in flags.items() if v} == IMPLEMENTED_PASSIVE_KEYS
        assert {k for k, v in flags.items() if not v} == set()
        assert all(v is True for v in flags.values())

    def test_berserk_passive_unchanged(self):
        p = subclass_registry.get_passive_for_subclass("warrior_berserker")
        assert p.name == "Ярость" and p.implemented is True
        assert "+4%" in p.description and "+36%" in p.description

    def test_inquisitor_description_all_non_physical_resists(self):
        d = subclass_registry.get_passive_for_subclass("warrior_inquisitor").description
        assert "не-физические сопротивления" in d
        for school in ("магия", "стихии", "святость", "проклятие"):
            assert school in d
        assert "3%" in d and "5 стаков" in d

    def test_trickster_description_has_redirect(self):
        """FEAT-190: the deceived blow goes to a random ally of the attacker at 50%."""
        d = subclass_registry.get_passive_for_subclass("rogue_trickster").description
        assert "10%" in d and "на 1 ход дольше" in d
        assert "не проходит" in d
        assert "союзника атакующего" in d
        assert "50% урона" in d
        assert "уходит" in d.lower()

    def test_necromancer_kill_is_heal_not_max_hp_growth(self):
        """PM decision: kill = heal 10% of max HP, max HP does not grow."""
        d = subclass_registry.get_passive_for_subclass("mage_necromancer").description
        assert "1 маны = 1.5 здоровья" in d
        assert "Убить себя нельзя" in d
        assert "лечение на 10% макс." in d
        assert "+10% макс" not in d

    def test_paladin_cleanses_most_recent_removable_effect(self):
        d = subclass_registry.get_passive_for_subclass("warrior_paladin").description
        assert "ниже 30%" in d and "20% макс. здоровья" in d
        assert "самого свежего" in d
        assert "оглушение и паралич не снимаются" in d

    @pytest.mark.parametrize("subclass_key, numbers", [
        ("rogue_bard", ("+5%", "максимум 3")),
        ("mage_etheriad", ("сам Эфириад",)),
        ("mage_auromancer", ("самого себя",)),
    ])
    def test_no_allies_clause(self, subclass_key, numbers):
        d = subclass_registry.get_passive_for_subclass(subclass_key).description
        assert "Если союзников нет" in d
        for n in numbers:
            assert n in d

    @pytest.mark.parametrize("subclass_key, phrases", [
        ("warrior_guardian", ("15%", "не критует", "не отражается")),
        ("rogue_bard", ("+3%", "максимум 4", "+12%", "+15%")),
        ("mage_etheriad", ("ниже 50%", "+8% сопротивлений", "−8% сопротивлений",
                           "+8% урона", "2 хода")),
        ("mage_auromancer", ("20% макс. здоровья", "3 хода")),
        ("mage_priest", ("10%", "15%")),
    ])
    def test_wave2_descriptions_quote_numbers(self, subclass_key, phrases):
        d = subclass_registry.get_passive_for_subclass(subclass_key).description
        for p in phrases:
            assert p in d

    @pytest.mark.parametrize("subclass_key, phrase", [
        ("warrior_gladiator", "не в меньшинстве"),
        ("rogue_mechanic", "Если других врагов нет"),
        ("mage_sparkmage", "Если других врагов нет"),
    ])
    def test_duel_wording_replaced(self, subclass_key, phrase):
        d = subclass_registry.get_passive_for_subclass(subclass_key).description
        assert phrase in d
        assert "дуэл" not in d.lower()
