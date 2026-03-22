from __future__ import annotations
import math, random, statistics
from typing import Dict, Any, List, Tuple

_MODE_BONUS = {
    "attack":  {"attack": +0.5, "support": +0.1, "defense": -0.2},
    "defense": {"attack": -0.2, "support": +0.1, "defense": +0.5},
    "balance": {"attack": +0.2, "support": +0.2, "defense": +0.2},
}
_MODE_CHOICES = set(_MODE_BONUS)

# ────────────────────────────────────────────────────────────────
def _flatten(tree) -> List[dict]:
    out, st = [], [tree]
    while st:
        cur = st.pop()
        if isinstance(cur, dict):
            out.append(cur)
        elif isinstance(cur, list):
            st.extend(cur)
    return out

# ────────────────────────────────────────────────────────────────
class Strategy:
    def __init__(self) -> None:
        self.mode    : str = "balance"
        self.rating  : Dict[int, Tuple[int, int]] = {}   # rank_id → (likes, dislikes)

    # ───────────── публичное API ─────────────
    def set_mode(self, mode: str) -> None:
        if mode not in _MODE_CHOICES:
            raise ValueError(f"unknown mode {mode}")
        self.mode = mode

    def feedback(self, rank_ids: List[int], liked: bool) -> None:
        for rid in rank_ids:
            good, bad = self.rating.get(rid, (0, 0))
            self.rating[rid] = (good + (1 if liked else 0),
                                bad  + (0 if liked else 1))

    def select_actions(
        self, ctx: Dict[str, Any]
    ) -> Tuple[Dict[str, int | None], int | None]:

        avail   = self._filter_available(ctx)
        feats   = ctx.get("features", {})
        weights = self._calc_weights(avail, feats)
        choice  = self._pick_best(weights, avail, feats)
        return choice["skills"], choice["item_id"]

    # ───────────── helpers ─────────────
    # ------------------------------------------------------------------
    def _filter_available(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        pid   = int(ctx["runtime"]["current_actor"])
        me_rt = ctx["runtime"]["participants"][str(pid)]

        snap  = next(s for s in ctx["snapshot"] if s["participant_id"] == pid)
        skills = {r["id"]: r for r in _flatten(snap["skills"])}

        slots  = _flatten(me_rt.get("fast_slots", []))
        cdict  = me_rt["cooldowns"]

        def enough(r: dict) -> bool:
            return (
                me_rt["energy"]  >= r.get("cost_energy", 0) and
                me_rt["mana"]    >= r.get("cost_mana", 0) and
                me_rt["stamina"] >= r.get("cost_stamina", 0)
            )

        available = {rid: r for rid, r in skills.items()
                     if cdict.get(str(rid), 0) == 0 and enough(r)}

        return {"skills": available, "fast_slots": slots}

    # ------------------------------------------------------------------
    def _wilson(self, likes: int, dislikes: int) -> float:
        n = likes + dislikes
        if n == 0:
            return 0.5
        z = 1.96
        p = likes / n
        return (
            p + z*z/(2*n)
            - z * math.sqrt(p*(1-p)/n + z*z/(4*n))
        ) / (1 + z*z/n)       # 0…1

    def _calc_weights(
        self, avail: Dict[str, Any], f: Dict[str, float]
    ) -> Dict[int, float]:

        out: Dict[int, float] = {}
        for rid, row in avail["skills"].items():
            base  = 1.0
            stype = row.get("skill_type", "attack").lower()
            bonus = _MODE_BONUS[self.mode].get(stype, 0.0)

            # влияние HP: чем меньше, тем важнее support/defense
            if stype == "support":
                bonus += (1.0 - f.get("hp_ratio", 1.0)) * 0.5
            if stype == "defense":
                bonus += (1.0 - f.get("hp_ratio", 1.0)) * 0.3

            # пользовательские лайки
            likes, dislikes = self.rating.get(rid, (0, 0))
            rating = self._wilson(likes, dislikes)    # 0..1

            noise = random.uniform(-0.05, 0.05)
            out[rid] = base + bonus + rating + noise
        return out

    # ------------------------------------------------------------------
    def _pick_best(
        self, w: Dict[int, float],
        avail: Dict[str, Any],
        f: Dict[str, float]
    ) -> Dict[str, Any]:

        # ------------- выбор навыков -----------------
        buckets = {"attack": [], "defense": [], "support": []}
        for rid, weight in w.items():
            t = avail["skills"][rid].get("skill_type", "attack").lower()
            buckets.setdefault(t, []).append((rid, weight))

        skills = {"attack_rank_id": None, "defense_rank_id": None, "support_rank_id": None}
        for t, lst in buckets.items():
            if lst:
                rid, _ = max(lst, key=lambda x: x[1])
                skills[f"{t}_rank_id"] = rid

        # ------------- выбор предмета ----------------
        need_hp   = max(0.0, f.get("hp_ratio",1.0)  - 0.7)   # >0 если <70 %
        need_mana = max(0.0, f.get("mana_ratio",1.0)- 0.6)
        need_energy = max(0.0, f.get("energy_ratio",1.0)-0.6)

        def value(slot):
            v  = need_hp   * slot.get("health_recovery", 0)
            v += need_mana * slot.get("mana_recovery",   0)
            v += need_energy * slot.get("energy_recovery", 0)
            v += 0.01 * slot.get("quantity",0)
            return v

        item_id = None
        if avail["fast_slots"]:
            best = max(avail["fast_slots"], key=value)
            if value(best) > 0:
                item_id = best["item_id"]

        return {"skills": skills, "item_id": item_id}
