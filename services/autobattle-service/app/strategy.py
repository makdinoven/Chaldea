# strategy.py  ───────────────────────────────────────────────
from __future__ import annotations
import random
from typing import Any, Dict, Tuple, List

import lightgbm as lgb
import numpy as np

# путь к файлу модели
from pathlib import Path
_MODEL_PATH = Path("/mnt/data/auto_battle_lgbm.txt")

_MODE_CHOICES = {"attack", "defense", "balance"}


def _flatten(tree) -> List[dict]:
    """
    Универсально «расплющивает» любое количество вложенных списков:
        [{..}, [{..}, {..}], …]  ->  list[dict]
    """
    out: list[dict] = []
    stack = [tree]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            out.append(cur)
        elif isinstance(cur, list):
            stack.extend(cur)
    return out


class Strategy:
    def __init__(self):
        self.mode = "balance"
        self.model: lgb.Booster | None = None
        self._load_model()

    def set_mode(self, mode: str):
        if mode not in _MODE_CHOICES:
            raise ValueError(f"Unknown mode {mode}")
        self.mode = mode

    # ────────── публичный вызов из main.py ──────────
    def select_actions(
        self, ctx: Dict[str, Any]
    ) -> Tuple[Dict[str, int | None], int | None]:
        available = self._filter_available(ctx)
        weights   = self._calc_weights(available)
        chosen    = self._pick_best(weights, available)
        return chosen["skills"], chosen["item_id"]

    # ────────── helpers ──────────
    # ──────────────────────────────────────────────────────────
    def _filter_available(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """
        Достаём из снапшота навыки и fast-слоты текущего участника,
        убираем навыки на кулдауне.
        """

        def _flatten(tree) -> list[dict]:
            out, stack = [], [tree]
            while stack:
                cur = stack.pop()
                if isinstance(cur, dict):
                    out.append(cur)
                elif isinstance(cur, list):
                    stack.extend(cur)
            return out

        me_pid = int(ctx["runtime"]["current_actor"])

        # <─── СНАПШОТ теперь список ─────────────────────────>
        my_snapshot = next(
            snap for snap in ctx["snapshot"] if snap["participant_id"] == me_pid
        )

        # skills: list[..., {...}, [...]]
        raw_skills = my_snapshot["skills"]
        skills_list = _flatten(raw_skills)  # гарантированно list[dict]
        skills_map = {r["id"]: r for r in skills_list}

        # fast-слоты берём из runtime, там же quantities актуальны
        raw_slots = ctx["runtime"]["participants"][str(me_pid)].get("fast_slots", [])
        fast_slots = _flatten(raw_slots)

        # фильтруем кулдауны
        cooldowns = ctx["runtime"]["participants"][str(me_pid)]["cooldowns"]
        me_stat = ctx["runtime"]["participants"][str(me_pid)]

        def _enough(r: dict) -> bool:
            return (
                    me_stat["energy"] >= r.get("cost_energy", 0) and
                    me_stat["mana"] >= r.get("cost_mana", 0) and
                    me_stat["stamina"] >= r.get("cost_stamina", 0)
            )
        available_skills = {
            rid: r for rid, r in skills_map.items()
            if cooldowns.get(str(rid), 0) == 0 and _enough(r)
        }

        return {
            "skills": available_skills,  # dict[id] → json
            "fast_slots": fast_slots,  # list[dict]
        }

    def _calc_weights(self, available: Dict[str, Any]) -> Dict[int, float]:
        base = {"attack": 1.0, "support": 0.8, "defense": 0.6}
        boost = {"attack": 0.4, "balance": 0.2, "defense": -0.2}
        out: Dict[int, float] = {}
        for rid, r in available["skills"].items():
            if not isinstance(r, dict):
                raise RuntimeError(f"NOT DICT: {type(r)} → {r!r}")
                continue
            t = r.get("skill_type", "attack")
            w = base.get(t, 0.5) + boost[self.mode] + random.uniform(-0.1, 0.1)
            out[rid] = w
        return out

    def _pick_best(self, w: Dict[int, float], avail: Dict[str, Any]) -> Dict[str, Any]:
        by_type = {"attack": [], "defense": [], "support": []}
        for rid, weight in w.items():
            t = avail["skills"][rid].get("skill_type", "attack")
            by_type.setdefault(t, []).append((rid, weight))
        for lst in by_type.values():
            lst.sort(key=lambda x: x[1], reverse=True)

        skills = {
            "attack_rank_id": by_type["attack"][0][0] if by_type["attack"] else None,
            "defense_rank_id": by_type["defense"][0][0] if by_type["defense"] else None,
            "support_rank_id": by_type["support"][0][0] if by_type["support"] else None,
        }

        item_id = None
        for slot in avail["fast_slots"]:
            if slot.get("quantity", 0) > 0:
                item_id = slot["item_id"]
                break

        return {"skills": skills, "item_id": item_id}

    # ────────── загрузка / сохранение модели ──────────
    def _load_model(self):
        if _MODEL_PATH.exists():
            self.model = lgb.Booster(model_file=str(_MODEL_PATH))

    def _save_model(self):
        if self.model:
            _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.model.save_model(str(_MODEL_PATH))
