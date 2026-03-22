"""
Tests for case normalization in Strategy._pick_best() and _calc_weights()
(FEAT-060, Task #6).

Verifies that:
- _pick_best() produces lowercase keys (attack_rank_id, defense_rank_id, support_rank_id)
  regardless of skill_type case ("Attack", "DEFENSE", "support")
- _calc_weights() correctly applies mode bonuses regardless of skill_type case
"""

import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Remove any mocked version of strategy left by other test files
# (e.g. test_endpoint_auth.py injects MagicMock into sys.modules at module level)
if "strategy" in sys.modules and isinstance(sys.modules["strategy"], MagicMock):
    del sys.modules["strategy"]

from strategy import Strategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_avail(skills_dict):
    """Wrap a skills dict into the format _filter_available returns."""
    return {"skills": skills_dict, "fast_slots": []}


def _skill(rid, skill_type, cost_energy=0, cost_mana=0, cost_stamina=0):
    """Build a minimal skill rank dict."""
    return {
        "id": rid,
        "skill_type": skill_type,
        "cost_energy": cost_energy,
        "cost_mana": cost_mana,
        "cost_stamina": cost_stamina,
        "damage_base": 10,
    }


# ---------------------------------------------------------------------------
# Tests for _pick_best() — case normalization
# ---------------------------------------------------------------------------

class TestPickBestCaseNormalization:
    """_pick_best() should produce lowercase keys regardless of skill_type case."""

    def test_capitalized_skill_types(self):
        """Capitalized types ("Attack", "Defense", "Support") map to lowercase keys."""
        s = Strategy()
        avail = _make_avail({
            1: _skill(1, "Attack"),
            2: _skill(2, "Defense"),
            3: _skill(3, "Support"),
        })
        weights = {1: 1.0, 2: 0.8, 3: 0.6}
        feats = {}

        result = s._pick_best(weights, avail, feats)

        assert result["skills"]["attack_rank_id"] == 1
        assert result["skills"]["defense_rank_id"] == 2
        assert result["skills"]["support_rank_id"] == 3

    def test_uppercase_skill_types(self):
        """Fully uppercase types ("ATTACK", "DEFENSE", "SUPPORT") map to lowercase keys."""
        s = Strategy()
        avail = _make_avail({
            10: _skill(10, "ATTACK"),
            20: _skill(20, "DEFENSE"),
            30: _skill(30, "SUPPORT"),
        })
        weights = {10: 1.0, 20: 0.9, 30: 0.7}
        feats = {}

        result = s._pick_best(weights, avail, feats)

        assert result["skills"]["attack_rank_id"] == 10
        assert result["skills"]["defense_rank_id"] == 20
        assert result["skills"]["support_rank_id"] == 30

    def test_already_lowercase_skill_types(self):
        """Already-lowercase types still work correctly."""
        s = Strategy()
        avail = _make_avail({
            5: _skill(5, "attack"),
            6: _skill(6, "defense"),
            7: _skill(7, "support"),
        })
        weights = {5: 1.0, 6: 0.8, 7: 0.6}
        feats = {}

        result = s._pick_best(weights, avail, feats)

        assert result["skills"]["attack_rank_id"] == 5
        assert result["skills"]["defense_rank_id"] == 6
        assert result["skills"]["support_rank_id"] == 7

    def test_mixed_case_skill_types(self):
        """Mixed case ("Attack", "defense", "SUPPORT") all normalize to lowercase keys."""
        s = Strategy()
        avail = _make_avail({
            1: _skill(1, "Attack"),
            2: _skill(2, "defense"),
            3: _skill(3, "SUPPORT"),
        })
        weights = {1: 1.0, 2: 0.9, 3: 0.8}
        feats = {}

        result = s._pick_best(weights, avail, feats)

        assert result["skills"]["attack_rank_id"] == 1
        assert result["skills"]["defense_rank_id"] == 2
        assert result["skills"]["support_rank_id"] == 3

    def test_no_capitalized_keys_in_output(self):
        """No keys like 'Attack_rank_id' should appear — only lowercase."""
        s = Strategy()
        avail = _make_avail({
            1: _skill(1, "Attack"),
            2: _skill(2, "Defense"),
            3: _skill(3, "Support"),
        })
        weights = {1: 1.0, 2: 0.8, 3: 0.6}
        feats = {}

        result = s._pick_best(weights, avail, feats)
        skills = result["skills"]

        # Should NOT have capitalized keys
        assert "Attack_rank_id" not in skills
        assert "Defense_rank_id" not in skills
        assert "Support_rank_id" not in skills

        # Should have lowercase keys
        assert "attack_rank_id" in skills
        assert "defense_rank_id" in skills
        assert "support_rank_id" in skills

    def test_empty_skills(self):
        """With no skills, all rank_ids should be None."""
        s = Strategy()
        avail = _make_avail({})
        weights = {}
        feats = {}

        result = s._pick_best(weights, avail, feats)

        assert result["skills"]["attack_rank_id"] is None
        assert result["skills"]["defense_rank_id"] is None
        assert result["skills"]["support_rank_id"] is None

    def test_picks_highest_weight_per_bucket(self):
        """When multiple skills of same type exist, picks highest weight."""
        s = Strategy()
        avail = _make_avail({
            1: _skill(1, "Attack"),
            2: _skill(2, "Attack"),
            3: _skill(3, "Defense"),
        })
        weights = {1: 0.5, 2: 1.5, 3: 0.8}
        feats = {}

        result = s._pick_best(weights, avail, feats)

        assert result["skills"]["attack_rank_id"] == 2  # higher weight
        assert result["skills"]["defense_rank_id"] == 3


# ---------------------------------------------------------------------------
# Tests for _calc_weights() — case normalization in mode bonuses
# ---------------------------------------------------------------------------

class TestCalcWeightsCaseNormalization:
    """_calc_weights() should apply mode bonuses regardless of skill_type case."""

    def test_attack_mode_bonus_with_capitalized_type(self):
        """Attack mode gives +0.5 bonus to 'Attack' (capitalized) skills."""
        s = Strategy()
        s.set_mode("attack")

        avail = _make_avail({
            1: _skill(1, "Attack"),
            2: _skill(2, "Defense"),
        })
        feats = {"hp_ratio": 1.0}

        weights = s._calc_weights(avail, feats)

        # Attack skill should have higher weight than Defense
        # attack mode: attack gets +0.5, defense gets -0.2
        # So weight_1 > weight_2
        assert weights[1] > weights[2]

    def test_defense_mode_bonus_with_uppercase_type(self):
        """Defense mode gives +0.5 bonus to 'DEFENSE' (uppercase) skills."""
        s = Strategy()
        s.set_mode("defense")

        avail = _make_avail({
            1: _skill(1, "ATTACK"),
            2: _skill(2, "DEFENSE"),
        })
        feats = {"hp_ratio": 1.0}

        weights = s._calc_weights(avail, feats)

        # Defense skill should have higher weight than Attack
        assert weights[2] > weights[1]

    def test_support_bonus_with_low_hp_capitalized(self):
        """Support bonus from low HP applies to 'Support' (capitalized) skill."""
        s = Strategy()
        s.set_mode("balance")

        avail = _make_avail({
            1: _skill(1, "Support"),
            2: _skill(2, "Attack"),
        })
        feats = {"hp_ratio": 0.2}  # low HP — support gets extra bonus

        weights = s._calc_weights(avail, feats)

        # Support should get significant bonus from low HP
        # balance mode: both get +0.2
        # support also gets (1.0 - 0.2) * 0.5 = 0.4 extra
        # So support weight > attack weight
        assert weights[1] > weights[2]

    def test_consistent_weights_regardless_of_case(self):
        """Same skill with different cases should get same weight (within noise)."""
        s = Strategy()
        s.set_mode("attack")

        avail_lower = _make_avail({1: _skill(1, "attack")})
        avail_upper = _make_avail({1: _skill(1, "ATTACK")})
        avail_cap = _make_avail({1: _skill(1, "Attack")})
        feats = {"hp_ratio": 1.0}

        # Run multiple times and check that the weights are in the same range
        # (noise is +-0.05, so the base weights should be the same)
        import random
        random.seed(42)
        w_lower = s._calc_weights(avail_lower, feats)[1]
        random.seed(42)
        w_upper = s._calc_weights(avail_upper, feats)[1]
        random.seed(42)
        w_cap = s._calc_weights(avail_cap, feats)[1]

        # With same random seed, noise is identical, so weights must be equal
        assert w_lower == w_upper == w_cap
