"""
Всю «умную» часть держим здесь.
LightGBM-модель подгружается/сохраняется автоматически.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, List, Tuple

import lightgbm as lgb
import numpy as np

_MODEL_PATH = Path("/mnt/data/auto_battle_lgbm.txt")
_MODE_CHOICES = {"attack", "defense", "balance"}


class Strategy:
    """
    Очень упрощённый, но расширяемый класс:
      • хранит weights на уровне Python-словаря,
      • позволяет «подкручивать» веса и доучивать LightGBM.
    """

    def __init__(self):
        self.mode: str = "balance"
        self.model: lgb.Booster | None = None
        self._load_model()

    # ──────────────────────────────────────────────────────────────
    # public API
    # ──────────────────────────────────────────────────────────────
    def set_mode(self, mode: str):
        if mode not in _MODE_CHOICES:
            raise ValueError(f"Unknown mode '{mode}'")
        self.mode = mode

    def select_actions(
        self,
        ctx: Dict[str, Any],
    ) -> Tuple[Dict[str, int | None], int | None]:
        """
        На входе – полный бой-контекст, полученный из /state.
        На выходе – словарь skills и item_id.
        """
        available = self._filter_available(ctx)
        weights = self._calc_weights(ctx, available)
        chosen = self._pick_best(weights, available)
        return chosen["skills"], chosen["item_id"]

    def learn_from_result(self, features: List[float], grade: int):
        """
        grade == 1 (понравилось) / 0 (не понравилось)
        """
        X = np.array([features])
        y = np.array([grade])
        if self.model is None:
            lgb_train = lgb.Dataset(X, y)
            self.model = lgb.train(
                params={"objective": "binary", "verbosity": -1}, train_set=lgb_train, num_boost_round=10
            )
        else:
            self.model = lgb.train(
                params={"objective": "binary", "verbosity": -1},
                train_set=lgb.Dataset(X, y),
                init_model=self.model,
                num_boost_round=10,
            )
        self._save_model()

    # ──────────────────────────────────────────────────────────────
    # internal helpers
    # ──────────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────
    def _filter_available(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """
        Убираем навыки на кулдауне + недоступные по ресурсам.
        Универсально раскладываем skills, даже если там list-of-list.
        """

        def _flatten(obj) -> list[dict]:
            """Рекурсивно превращает [ [...], {...}, ...] → list[dict]."""
            out: list[dict] = []
            stack = [obj]
            while stack:
                cur = stack.pop()
                if isinstance(cur, dict):
                    out.append(cur)
                elif isinstance(cur, list):
                    stack.extend(cur)
            return out

        me = str(ctx["runtime"]["current_actor"])

        raw_skills = next(
            snap["skills"]
            for snap in ctx["snapshot"]["participants"]
            if snap["participant_id"] == int(me)
        )
        skills: list[dict] = _flatten(raw_skills)  # ← теперь гарантированно list[dict]

        # строим id ➜ json
        skills_map = {r["id"]: r for r in skills}

        cooldowns = ctx["runtime"]["participants"][me]["cooldowns"]
        available_skills = {
            rid: r
            for rid, r in skills_map.items()
            if cooldowns.get(str(rid), 0) == 0
        }

        return {
            "skills": available_skills,
            "resources": ctx["runtime"]["participants"][me],
            "fast_slots": ctx["runtime"]["participants"][me].get("fast_slots", []),
        }

    def _calc_weights(self, ctx: Dict[str, Any], available: Dict[str, Any]) -> Dict[int, float]:
        """
        Возвращает {rank_id: weight}. Здесь – заглушка.
        """
        base_weight = {"attack": 1.0, "support": 0.8, "defense": 0.6}
        mode_boost = {"attack": 0.4, "balance": 0.2, "defense": -0.2}
        weights = {}
        for rid, r in available["skills"].items():
            if not isinstance(r, dict):
                continue
            t = r.get("skill_type", "attack")  # "attack" / "support" / "defense"
            w = base_weight.get(t, 0.5) + mode_boost[self.mode]
            # + случайный фактор
            w += random.uniform(-0.1, 0.1)
            weights[rid] = w
        return weights

    def _pick_best(self, weights: Dict[int, float], available: Dict[str, Any]) -> Dict[str, Any]:
        """
        Максимум 1 attack, 1 defense, 1 support, 1 consumable.
        """
        by_type = {"attack": [], "defense": [], "support": []}
        for rid, w in weights.items():
            t = available["skills"][rid]["skill_type"]
            by_type[t].append((rid, w))
        for lst in by_type.values():
            lst.sort(key=lambda x: x[1], reverse=True)

        skills = {
            "attack_rank_id": by_type["attack"][0][0] if by_type["attack"] else None,
            "defense_rank_id": by_type["defense"][0][0] if by_type["defense"] else None,
            "support_rank_id": by_type["support"][0][0] if by_type["support"] else None,
        }

        # выбираем первый consumable с quantity>0
        item_id = None
        for slot in available["fast_slots"]:
            if slot.get("quantity", 0) > 0:
                item_id = slot["item_id"]
                break

        return {"skills": skills, "item_id": item_id}

    # ─────────────────────────────────────
    def _load_model(self):
        if _MODEL_PATH.exists():
            self.model = lgb.Booster(model_file=str(_MODEL_PATH))

    def _save_model(self):
        if self.model:
            _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.model.save_model(str(_MODEL_PATH))
