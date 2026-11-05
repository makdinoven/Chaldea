"""FEAT-201 QA (task 8): the stealth stat in character-service — gaps not covered by the developer's tests.

* §3.3 worked numbers not pinned elsewhere: escape with stealth 100 = 35, flee 45 via ``law_core.chance``,
  the full witness pipeline per subclass (Фокусник / Агент), agility/luck never enter the pure maths;
* ``GET /characters/{id}/stealth``: the cap (raw 400 -> eff 200 -> reduction 90), other subclasses, luck and
  agility ignored, non-integer id 422;
* admin shadow settings: the new stealth fields round-trip, their bounds are 400 with Russian text, the
  removed FEAT-199 knobs are ignored (not stored, not echoed), a missing new field is 422, max 100 accepted;
* migration ``041_stealth`` driven against a simulated MySQL information_schema: upgrade / re-run no-op /
  downgrade / upgrade, the Q2 escape rule (0.150 -> 0.300 only when untouched), admin edits kept on re-run;
* ``StatPreset`` root validator: stealth counted, luck not double counted, the same Russian error, negatives
  rejected; the subrace admin endpoint accepts a preset with stealth;
* passport: ``PASSPORT_STAT_KEYS`` has 11 keys incl. stealth, ``normalize_starting_attributes`` keeps stealth
  and still accepts old 10-key snapshots.
"""

import importlib.util
import os
import re
from decimal import Decimal as D

import pytest
from pydantic import ValidationError

import crud
import law_core as lc
import schemas
import shadow_core as sc
from tests.law_world import ALPHA, USER_ALPHA, api, as_admin, as_user, law_world, q, rep_world  # noqa: F401
from tests.shadow_world import set_attrs, set_subclass

S = sc.DEFAULT_SETTINGS


# =============================================================================================== §3.3 numbers

def test_escape_with_stealth_100_is_35():
    s = lc.DEFAULT_SETTINGS
    assert D(str(s.escape_per_point_pct)) == D("0.3")
    assert lc.chance(s.escape_base_pct, s.escape_per_point_pct, s.escape_min_pct, s.escape_max_pct, D(100)) \
        == D("35.00")


def test_flee_is_stealth_plus_agility_equal_weight():
    assert lc.chance(20, D("0.25"), 0, 100, D(40), D(60)) == D("45.00")
    assert lc.chance(20, D("0.25"), 0, 100, D(60), D(40)) == D("45.00")      # order does not matter
    assert lc.chance(20, D("0.25"), 0, 100, D(-10), D(60)) == D("35.00")     # negative points count as 0


@pytest.mark.parametrize("subclass,raw,expected", [
    ("rogue_trickster", 0, "85.00"),     # +30 -> red 15
    ("warrior_agent", 0, "90.00"),       # +20 -> red 10
    ("warrior_agent", 100, "45.00"),     # 120 -> eff 110 -> red 55
    ("rogue_assassin", 200, "21.25"),    # 230 -> eff 100 + 50 + 7.5 = 157.5 -> red 78.75
    ("mage_other", 100, "50.00"),        # not a stealth subclass
])
def test_settlement_witness_per_subclass(subclass, raw, expected):
    red = sc.stealth_reduction_pct(sc.effective_stealth(raw, sc.subclass_stealth_points(subclass, S)), S)
    assert sc.group_chance([sc.member_chance(S.witness_base_safe_pct, red, False, 0)], 1, S) == D(expected)


def test_subclass_points_follow_the_settings():
    custom = sc.ShadowSettings(**{**{n: getattr(S, n) for n in sc.SETTINGS_FIELDS}, "stealth_agent_points": 0})
    assert sc.subclass_stealth_points("warrior_agent", custom) == 0
    assert sc.subclass_stealth_points("rogue_assassin", custom) == 30


def test_settings_have_no_agility_or_luck_or_mask_knob():
    names = " ".join(sc.SETTINGS_FIELDS)
    for gone in ("witness_stealth_per_point_pct", "witness_agent_pct", "witness_assassin_pct",
                 "witness_trickster_pct", "witness_mask_pct"):
        assert gone not in sc.SETTINGS_FIELDS
    assert "agility" not in names and "luck" not in names


def test_default_bases_and_bounds():
    assert (S.witness_base_safe_pct, S.witness_base_farm_pct, S.witness_base_dangerous_pct,
            S.witness_base_dungeon_pct) == (100, 70, 40, 25)
    assert (S.witness_min_pct, S.witness_max_pct) == (5, 100)
    assert (S.stealth_pct_per_point, S.stealth_max_reduction_pct) == (D("0.5"), 90)


# =============================================================================================== /stealth endpoint

def test_stealth_endpoint_applies_the_cap_and_max_reduction(api, law_world):
    set_attrs(law_world, ALPHA, stealth=400)
    as_user(USER_ALPHA)
    body = api.get(f"/characters/{ALPHA}/stealth").json()
    assert (body["stealth"], body["effective"], body["reduction_pct"]) == (400, 200.0, 90.0)


@pytest.mark.parametrize("key,name,bonus", [("rogue_trickster", "Фокусник", 30), ("warrior_agent", "Агент", 20)])
def test_stealth_endpoint_other_subclasses(api, law_world, key, name, bonus):
    set_subclass(law_world, ALPHA, key)
    as_user(USER_ALPHA)
    body = api.get(f"/characters/{ALPHA}/stealth").json()
    assert (body["subclass_name"], body["subclass_bonus"], body["effective"]) == (name, bonus, float(bonus))
    assert body["reduction_pct"] == bonus * 0.5


def test_stealth_endpoint_ignores_agility_and_luck(api, law_world):
    set_attrs(law_world, ALPHA, agility=150, luck=150, stealth=0)
    as_user(USER_ALPHA)
    body = api.get(f"/characters/{ALPHA}/stealth").json()
    assert (body["effective"], body["reduction_pct"]) == (0.0, 0.0)


@pytest.mark.parametrize("bad", ["abc", "1%20OR%201=1", "1;DROP%20TABLE%20characters"])
def test_stealth_endpoint_non_integer_id_422(api, law_world, bad):
    as_user(USER_ALPHA)
    assert api.get(f"/characters/{bad}/stealth").status_code == 422


# =============================================================================================== settings API

def _settings_body(**settings):
    s = {n: (float(v) if not isinstance(v, (bool, int)) else v)
         for n, v in ((n, getattr(S, n)) for n in sc.SETTINGS_FIELDS)}
    s.update(settings)
    fame = [{"code": t.code, "name": t.name, "min_value": t.min_value, "witness_pct": float(t.witness_pct)}
            for t in sc.DEFAULT_TIERS if t.scale == "fame"]
    infamy = [{"code": t.code, "name": t.name, "min_value": t.min_value}
              for t in sc.DEFAULT_TIERS if t.scale == "infamy"]
    return {"settings": s, "fame_tiers": fame, "infamy_tiers": infamy}


def test_put_new_stealth_settings_round_trip(api, law_world):
    as_admin()
    body = _settings_body(stealth_pct_per_point=0.75, stealth_max_reduction_pct=80, stealth_assassin_points=40,
                          stealth_trickster_points=25, stealth_agent_points=0, witness_max_pct=100)
    resp = api.put("/characters/admin/shadow/settings", json=body)
    assert resp.status_code == 200, resp.text
    got = api.get("/characters/admin/shadow/settings").json()["settings"]
    assert (got["stealth_pct_per_point"], got["stealth_max_reduction_pct"], got["stealth_assassin_points"],
            got["stealth_trickster_points"], got["stealth_agent_points"], got["witness_max_pct"]) == \
        (0.75, 80.0, 40, 25, 0, 100.0)


def test_new_settings_drive_the_stealth_endpoint(api, law_world):
    as_admin()
    assert api.put("/characters/admin/shadow/settings",
                   json=_settings_body(stealth_pct_per_point=1, stealth_max_reduction_pct=60)).status_code == 200
    set_attrs(law_world, ALPHA, stealth=80)
    as_user(USER_ALPHA)
    body = api.get(f"/characters/{ALPHA}/stealth").json()
    assert (body["reduction_pct"], body["pct_per_point"], body["max_reduction_pct"]) == (60.0, 1.0, 60.0)


@pytest.mark.parametrize("settings,fragment", [
    ({"stealth_pct_per_point": 10.5}, "Снижение за очко скрытности: от 0 до 10"),
    ({"stealth_pct_per_point": -0.1}, "Снижение за очко скрытности"),
    ({"stealth_max_reduction_pct": 100.5}, "Предел снижения скрытностью: от 0 до 100"),
    ({"stealth_assassin_points": 501}, "Скрытность подкласса «Ассасин»: от 0 до 500"),
    ({"stealth_trickster_points": -1}, "Скрытность подкласса «Фокусник»"),
    ({"stealth_agent_points": 1000}, "Скрытность подкласса «Агент»"),
    ({"witness_max_pct": 100.01}, "от 0 до 100"),
])
def test_put_stealth_settings_bounds_400(api, law_world, settings, fragment):
    as_admin()
    resp = api.put("/characters/admin/shadow/settings", json=_settings_body(**settings))
    assert resp.status_code == 400, resp.text
    assert fragment in resp.json()["detail"]
    assert q(law_world, "SELECT COUNT(*) FROM shadow_settings") == 0


@pytest.mark.parametrize("value", [0, 500])
def test_subclass_points_edges_accepted(api, law_world, value):
    as_admin()
    assert api.put("/characters/admin/shadow/settings",
                   json=_settings_body(stealth_assassin_points=value)).status_code == 200


def test_removed_feat199_knobs_are_ignored(api, law_world):
    as_admin()
    body = _settings_body()
    body["settings"].update(witness_mask_pct=10, witness_agent_pct=10, witness_stealth_per_point_pct=0.1)
    assert api.put("/characters/admin/shadow/settings", json=body).status_code == 200
    got = api.get("/characters/admin/shadow/settings").json()["settings"]
    assert not {"witness_mask_pct", "witness_agent_pct", "witness_stealth_per_point_pct"} & set(got)


@pytest.mark.parametrize("field", ["stealth_pct_per_point", "stealth_max_reduction_pct", "stealth_agent_points"])
def test_missing_new_field_is_422(api, law_world, field):
    as_admin()
    body = _settings_body()
    body["settings"].pop(field)
    assert api.put("/characters/admin/shadow/settings", json=body).status_code == 422


def test_subclass_points_must_be_integers(api, law_world):
    as_admin()
    resp = api.put("/characters/admin/shadow/settings", json=_settings_body(stealth_agent_points="двадцать"))
    assert resp.status_code == 422


# =============================================================================================== migration 041

_VERSIONS = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")


def _load_041():
    spec = importlib.util.spec_from_file_location("m041_qa", os.path.join(_VERSIONS, "041_stealth.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeMySQL:
    """A tiny stand-in for MySQL: information_schema answers + the DDL / UPDATE statements 041 issues."""

    def __init__(self, escape_row="0.150", tables=("shadow_settings", "law_crimes", "law_settings")):
        self.tables = set(tables)
        old = {c: re.search(r"DEFAULT (\S+)", ddl).group(1) for c, ddl in _load_041()._OLD_SHADOW_COLUMNS}
        bases = {"witness_base_safe_pct": "70.00", "witness_base_farm_pct": "45.00",
                 "witness_base_dangerous_pct": "25.00", "witness_base_dungeon_pct": "15.00",
                 "witness_max_pct": "95.00"}
        self.defaults = {
            "shadow_settings": {**old, **bases, "witness_min_pct": "5.00"},
            "law_crimes": {"status": None},
            "law_settings": {"escape_per_point_pct": "0.150"},
        }
        self.rows = {"shadow_settings": {**old, **bases, "witness_min_pct": "5.00"},
                     "law_settings": {"escape_per_point_pct": escape_row}}
        self.statements = []

    # --- connection API used by the migration helpers
    def execute(self, clause, params=None):
        sql = str(clause)
        params = params or {}
        value = None
        if "information_schema.tables" in sql:
            value = int(params["t"] in self.tables)
        elif "column_default" in sql:
            value = self.defaults.get(params["t"], {}).get(params["c"])
        elif "information_schema.columns" in sql:
            value = int(params["c"] in self.defaults.get(params["t"], {}))
        return _Scalar(value)

    # --- op.execute
    def op_execute(self, sql):
        self.statements.append(sql)
        m = re.match(r"ALTER TABLE (\w+) ADD COLUMN (\w+) (.*)$", sql)
        if m:
            t, c, ddl = m.groups()
            d = re.search(r"DEFAULT (\S+)", ddl)
            self.defaults[t][c] = d.group(1) if d else None
            if t in self.rows:
                self.rows[t][c] = d.group(1) if d else None
            return
        m = re.match(r"ALTER TABLE (\w+) DROP COLUMN (\w+)$", sql)
        if m:
            t, c = m.groups()
            del self.defaults[t][c]
            self.rows.get(t, {}).pop(c, None)
            return
        m = re.match(r"ALTER TABLE (\w+) MODIFY (\w+) .* DEFAULT (\S+)$", sql)
        if m:
            t, c, d = m.groups()
            assert c in self.defaults[t], f"MODIFY of a missing column {t}.{c}"
            self.defaults[t][c] = d
            return
        m = re.match(r"UPDATE (\w+) SET (.*) WHERE id = 1(?: AND (\w+) = (\S+))?$", sql)
        if m:
            t, assignments, cond_col, cond_val = m.groups()
            row = self.rows[t]
            if cond_col and D(row[cond_col]) != D(cond_val):
                return
            for part in assignments.split(","):
                col, val = (x.strip() for x in part.split("="))
                row[col] = val
            return
        raise AssertionError(f"unexpected SQL: {sql}")


class _Scalar:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _Op:
    def __init__(self, db):
        self.db = db

    def get_bind(self):
        return self.db

    def execute(self, sql):
        self.db.op_execute(sql)


def _run(db, step):
    mod = _load_041()
    mod.op = _Op(db)
    getattr(mod, step)()
    return mod


def test_041_upgrade_from_feat199():
    db = _FakeMySQL()
    mod = _run(db, "upgrade")
    ss = db.defaults["shadow_settings"]
    for c, _ in mod._OLD_SHADOW_COLUMNS:
        assert c not in ss and c not in db.rows["shadow_settings"]
    assert {c: ss[c] for c, _ in mod._NEW_SHADOW_COLUMNS} == {
        "stealth_pct_per_point": "0.500", "stealth_max_reduction_pct": "90.00", "stealth_assassin_points": "30",
        "stealth_trickster_points": "30", "stealth_agent_points": "20"}
    row = db.rows["shadow_settings"]
    assert [D(row[c]) for c in ("witness_base_safe_pct", "witness_base_farm_pct", "witness_base_dangerous_pct",
                                "witness_base_dungeon_pct", "witness_max_pct")] == [100, 70, 40, 25, 100]
    assert row["stealth_agent_points"] == "20"                       # existing row gets the new defaults
    assert "stealth_reduction_pct" in db.defaults["law_crimes"] and db.defaults["law_crimes"]["stealth_reduction_pct"] is None
    assert db.rows["law_settings"]["escape_per_point_pct"] == "0.300"     # Q2: untouched default doubled
    assert db.defaults["law_settings"]["escape_per_point_pct"] == "0.300"


def test_041_escape_tuned_by_admin_is_kept():
    db = _FakeMySQL(escape_row="0.200")
    _run(db, "upgrade")
    assert db.rows["law_settings"]["escape_per_point_pct"] == "0.200"
    assert db.defaults["law_settings"]["escape_per_point_pct"] == "0.300"
    _run(db, "downgrade")
    assert db.rows["law_settings"]["escape_per_point_pct"] == "0.200"     # downgrade halves only 0.300
    assert db.defaults["law_settings"]["escape_per_point_pct"] == "0.150"


def test_041_rerun_is_a_noop_and_keeps_admin_edits():
    db = _FakeMySQL()
    _run(db, "upgrade")
    db.rows["shadow_settings"]["witness_base_safe_pct"] = "80.00"          # admin edit after deploy
    db.rows["law_settings"]["escape_per_point_pct"] = "0.150"             # admin chose the old value on purpose
    db.statements.clear()
    _run(db, "upgrade")
    assert db.statements == []
    assert db.rows["shadow_settings"]["witness_base_safe_pct"] == "80.00"
    assert db.rows["law_settings"]["escape_per_point_pct"] == "0.150"


def test_041_downgrade_restores_feat199():
    db = _FakeMySQL()
    before_defaults = {t: dict(v) for t, v in db.defaults.items()}
    before_rows = {t: dict(v) for t, v in db.rows.items()}
    _run(db, "upgrade")
    _run(db, "downgrade")
    assert db.defaults == before_defaults
    assert {t: {c: D(v) for c, v in r.items()} for t, r in db.rows.items()} == \
        {t: {c: D(v) for c, v in r.items()} for t, r in before_rows.items()}
    # and up again lands on the same FEAT-201 state
    _run(db, "upgrade")
    assert db.rows["law_settings"]["escape_per_point_pct"] == "0.300"
    assert D(db.rows["shadow_settings"]["witness_base_safe_pct"]) == 100


def test_041_without_tables_does_nothing():
    db = _FakeMySQL(tables=())
    _run(db, "upgrade")
    assert db.statements == []


def test_041_revision_chain():
    mod = _load_041()
    assert (mod.revision, mod.down_revision) == ("041_stealth", "040_shadow_renown")
    assert len(mod.revision) <= 32
    text_ = open(mod.__file__, encoding="utf-8").read()
    assert "ALTER TABLE items" not in text_ and not re.search(r"\bENUM\s*\(", text_)


# =============================================================================================== StatPreset

_TEN = ["strength", "agility", "intelligence", "endurance", "health", "energy", "mana", "stamina", "charisma", "luck"]


def test_preset_keys_end_with_stealth():
    assert schemas.STAT_PRESET_KEYS == _TEN + ["stealth"]


def test_preset_with_stealth_accepted():
    p = schemas.StatPreset(strength=40, agility=30, stealth=30)
    assert p.stealth == 30


def test_old_preset_without_stealth_still_valid():
    p = schemas.StatPreset(**{k: 10 for k in _TEN})
    assert p.stealth == 0


def test_luck_is_not_double_counted():
    """The old field validator sat on «luck» and summed KEYS[:-1] + luck; with stealth appended it would count
    luck twice (luck 50 + strength 50 -> 150)."""
    schemas.StatPreset(luck=50, strength=50)
    with pytest.raises(ValidationError):
        schemas.StatPreset(luck=50, strength=25)


@pytest.mark.parametrize("kw,total", [
    ({"strength": 90, "stealth": 20}, 110),
    ({"stealth": 99}, 99),
    ({}, 0),
])
def test_wrong_sum_same_russian_message(kw, total):
    with pytest.raises(ValidationError) as exc:
        schemas.StatPreset(**kw)
    assert f"Сумма пресета должна быть равна 100, получено {total}" in str(exc.value)


def test_negative_stealth_rejected_with_russian_message():
    with pytest.raises(ValidationError) as exc:
        schemas.StatPreset(strength=110, stealth=-10)
    assert "Значение стата не может быть отрицательным" in str(exc.value)
    assert "Сумма пресета" not in str(exc.value)            # skip_on_failure: no confusing second error


# subrace admin endpoint (fixtures of test_race_crud)
from tests.test_race_crud import _create_race, _create_subrace, client, db_session  # noqa: E402,F401


def test_subrace_endpoint_accepts_stealth(client):
    race_id = _create_race(client, name="Теневая раса").json()["id_race"]
    preset = {k: 0 for k in _TEN}
    preset.update(strength=60, stealth=40)
    resp = _create_subrace(client, race_id, name="Сумеречные", stat_preset=preset)
    assert resp.status_code == 201, resp.text
    assert resp.json()["stat_preset"]["stealth"] == 40


def test_subrace_endpoint_rejects_wrong_sum_with_stealth(client):
    race_id = _create_race(client, name="Шумная раса").json()["id_race"]
    preset = {k: 0 for k in _TEN}
    preset.update(strength=100, stealth=5)
    resp = _create_subrace(client, race_id, name="Громкие", stat_preset=preset)
    assert resp.status_code == 422
    assert "получено 105" in resp.text


# =============================================================================================== passport

def test_passport_keys_are_eleven_with_stealth():
    assert len(crud.PASSPORT_STAT_KEYS) == 11
    assert crud.PASSPORT_STAT_KEYS[-1] == "stealth"
    assert set(crud.PASSPORT_STAT_KEYS) == set(schemas.STAT_PRESET_KEYS)


def test_normalize_keeps_stealth_and_old_snapshots():
    raw = {k: 9 for k in _TEN}
    raw.update(stealth=10, junk="x", flag=True)
    out = crud.normalize_starting_attributes(raw)
    assert out["stealth"] == 10 and len(out) == 11 and "junk" not in out
    old = crud.normalize_starting_attributes({k: 10 for k in _TEN})
    assert "stealth" not in old and len(old) == 10
