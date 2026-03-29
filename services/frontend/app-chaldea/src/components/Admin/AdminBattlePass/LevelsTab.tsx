import { useState, useEffect, useCallback } from "react";
import toast from "react-hot-toast";
import {
  getAdminSeasons,
  getSeasonLevels,
  upsertSeasonLevels,
} from "../../../api/battlePassAdmin";
import type {
  AdminSeason,
  AdminLevel,
  AdminLevelInput,
} from "../../../api/battlePassAdmin";

/* ── Constants ── */

const REWARD_TYPES = [
  { value: "gold", label: "Золото" },
  { value: "xp", label: "Опыт" },
  { value: "item", label: "Предмет" },
  { value: "diamonds", label: "Алмазы" },
  { value: "frame", label: "Рамка" },
  { value: "chat_background", label: "Подложка" },
];

const TOTAL_LEVELS = 30;

interface RewardInput {
  reward_type: "gold" | "xp" | "item" | "diamonds" | "frame" | "chat_background";
  reward_value: number;
  item_id: number | null;
  cosmetic_slug: string | null;
}

interface LevelRow {
  level_number: number;
  required_xp: number;
  free_rewards: RewardInput[];
  premium_rewards: RewardInput[];
}

const emptyReward = (): RewardInput => ({
  reward_type: "gold",
  reward_value: 0,
  item_id: null,
  cosmetic_slug: null,
});

const buildEmptyLevels = (): LevelRow[] =>
  Array.from({ length: TOTAL_LEVELS }, (_, i) => ({
    level_number: i + 1,
    required_xp: 100 + i * 50,
    free_rewards: [emptyReward()],
    premium_rewards: [emptyReward()],
  }));

/* ── Component ── */

const LevelsTab = () => {
  const [seasons, setSeasons] = useState<AdminSeason[]>([]);
  const [selectedSeasonId, setSelectedSeasonId] = useState<number | null>(null);
  const [levels, setLevels] = useState<LevelRow[]>(buildEmptyLevels());
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  /* Load seasons */
  useEffect(() => {
    getAdminSeasons()
      .then((res) => {
        setSeasons(res.items);
        if (res.items.length > 0 && selectedSeasonId === null) {
          setSelectedSeasonId(res.items[0].id);
        }
      })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : "Не удалось загрузить сезоны";
        toast.error(msg);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* Load levels when season changes */
  const loadLevels = useCallback(async (seasonId: number) => {
    setLoading(true);
    try {
      const data: AdminLevel[] = await getSeasonLevels(seasonId);
      if (data.length === 0) {
        setLevels(buildEmptyLevels());
      } else {
        const rows: LevelRow[] = data.map((lvl) => ({
          level_number: lvl.level_number,
          required_xp: lvl.required_xp,
          free_rewards: lvl.rewards
            .filter((r) => r.track === "free")
            .map((r) => ({
              reward_type: r.reward_type as RewardInput["reward_type"],
              reward_value: r.reward_value,
              item_id: r.item_id,
              cosmetic_slug: r.cosmetic_slug ?? null,
            })),
          premium_rewards: lvl.rewards
            .filter((r) => r.track === "premium")
            .map((r) => ({
              reward_type: r.reward_type as RewardInput["reward_type"],
              reward_value: r.reward_value,
              item_id: r.item_id,
              cosmetic_slug: r.cosmetic_slug ?? null,
            })),
        }));
        /* Fill missing levels */
        const existing = new Set(rows.map((r) => r.level_number));
        for (let i = 1; i <= TOTAL_LEVELS; i++) {
          if (!existing.has(i)) {
            rows.push({
              level_number: i,
              required_xp: 100 + (i - 1) * 50,
              free_rewards: [emptyReward()],
              premium_rewards: [emptyReward()],
            });
          }
        }
        rows.sort((a, b) => a.level_number - b.level_number);
        /* Ensure at least one reward per track */
        rows.forEach((r) => {
          if (r.free_rewards.length === 0) r.free_rewards.push(emptyReward());
          if (r.premium_rewards.length === 0) r.premium_rewards.push(emptyReward());
        });
        setLevels(rows);
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Не удалось загрузить уровни";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedSeasonId !== null) {
      loadLevels(selectedSeasonId);
    }
  }, [selectedSeasonId, loadLevels]);

  /* ── Mutations ── */

  const updateLevelXp = (idx: number, xp: number) => {
    setLevels((prev) => {
      const copy = [...prev];
      copy[idx] = { ...copy[idx], required_xp: xp };
      return copy;
    });
  };

  const updateReward = (
    levelIdx: number,
    track: "free" | "premium",
    rewardIdx: number,
    field: keyof RewardInput,
    value: string | number | null,
  ) => {
    setLevels((prev) => {
      const copy = [...prev];
      const key = track === "free" ? "free_rewards" : "premium_rewards";
      const rewards = [...copy[levelIdx][key]];
      rewards[rewardIdx] = { ...rewards[rewardIdx], [field]: value };
      copy[levelIdx] = { ...copy[levelIdx], [key]: rewards };
      return copy;
    });
  };

  const addReward = (levelIdx: number, track: "free" | "premium") => {
    setLevels((prev) => {
      const copy = [...prev];
      const key = track === "free" ? "free_rewards" : "premium_rewards";
      copy[levelIdx] = {
        ...copy[levelIdx],
        [key]: [...copy[levelIdx][key], emptyReward()],
      };
      return copy;
    });
  };

  const removeReward = (
    levelIdx: number,
    track: "free" | "premium",
    rewardIdx: number,
  ) => {
    setLevels((prev) => {
      const copy = [...prev];
      const key = track === "free" ? "free_rewards" : "premium_rewards";
      const rewards = copy[levelIdx][key].filter((_, i) => i !== rewardIdx);
      copy[levelIdx] = { ...copy[levelIdx], [key]: rewards };
      return copy;
    });
  };

  /* ── Save all ── */

  const handleSave = async () => {
    if (selectedSeasonId === null) return;
    setSaving(true);
    try {
      const payload: AdminLevelInput[] = levels.map((lvl) => ({
        level_number: lvl.level_number,
        required_xp: lvl.required_xp,
        free_rewards: lvl.free_rewards
          .filter((r) => r.reward_value > 0 || r.cosmetic_slug)
          .map((r) => ({
            reward_type: r.reward_type,
            reward_value: r.reward_value,
            item_id: r.item_id,
            cosmetic_slug: r.cosmetic_slug,
          })),
        premium_rewards: lvl.premium_rewards
          .filter((r) => r.reward_value > 0 || r.cosmetic_slug)
          .map((r) => ({
            reward_type: r.reward_type,
            reward_value: r.reward_value,
            item_id: r.item_id,
            cosmetic_slug: r.cosmetic_slug,
          })),
      }));
      await upsertSeasonLevels(selectedSeasonId, payload);
      toast.success("Уровни сохранены");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Ошибка сохранения";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  /* ── Reward row renderer ── */

  const renderRewards = (
    levelIdx: number,
    track: "free" | "premium",
    rewards: RewardInput[],
  ) => (
    <div className="flex flex-col gap-2">
      <span className="text-xs text-white/50 uppercase tracking-[0.06em]">
        {track === "free" ? "Бесплатные" : "Премиум"}
      </span>
      {rewards.map((rw, ri) => (
        <div key={ri} className="flex flex-wrap items-center gap-2">
          <select
            className="input-underline !w-auto min-w-[100px]"
            value={rw.reward_type}
            onChange={(e) =>
              updateReward(levelIdx, track, ri, "reward_type", e.target.value)
            }
          >
            {REWARD_TYPES.map((t) => (
              <option key={t.value} value={t.value} className="bg-site-dark text-white">
                {t.label}
              </option>
            ))}
          </select>
          <input
            className="input-underline !w-[80px]"
            type="number"
            min={0}
            placeholder="Кол-во"
            value={rw.reward_value || ""}
            onChange={(e) =>
              updateReward(
                levelIdx,
                track,
                ri,
                "reward_value",
                parseInt(e.target.value) || 0,
              )
            }
          />
          {rw.reward_type === "item" && (
            <input
              className="input-underline !w-[80px]"
              type="number"
              min={1}
              placeholder="Item ID"
              value={rw.item_id ?? ""}
              onChange={(e) =>
                updateReward(
                  levelIdx,
                  track,
                  ri,
                  "item_id",
                  e.target.value ? parseInt(e.target.value) : null,
                )
              }
            />
          )}
          {(rw.reward_type === "frame" || rw.reward_type === "chat_background") && (
            <input
              className="input-underline !w-[140px]"
              type="text"
              placeholder="Slug косметики *"
              value={rw.cosmetic_slug ?? ""}
              required
              onChange={(e) =>
                updateReward(
                  levelIdx,
                  track,
                  ri,
                  "cosmetic_slug",
                  e.target.value || null,
                )
              }
            />
          )}
          <button
            onClick={() => removeReward(levelIdx, track, ri)}
            className="text-site-red hover:text-white text-xs transition-colors"
            title="Удалить награду"
          >
            &#10005;
          </button>
        </div>
      ))}
      <button
        onClick={() => addReward(levelIdx, track)}
        className="text-xs text-site-blue hover:text-white transition-colors self-start"
      >
        + Добавить награду
      </button>
    </div>
  );

  return (
    <div className="flex flex-col gap-5">
      {/* Season selector */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
        <h2 className="gold-text text-2xl font-medium uppercase">Уровни и награды</h2>
        <select
          className="input-underline !w-auto min-w-[200px]"
          value={selectedSeasonId ?? ""}
          onChange={(e) => setSelectedSeasonId(Number(e.target.value))}
        >
          {seasons.length === 0 && (
            <option value="" className="bg-site-dark text-white">
              Нет сезонов
            </option>
          )}
          {seasons.map((s) => (
            <option key={s.id} value={s.id} className="bg-site-dark text-white">
              {s.name}
            </option>
          ))}
        </select>
      </div>

      {loading && (
        <p className="text-white/60 text-sm py-4">Загрузка...</p>
      )}

      {!loading && selectedSeasonId !== null && (
        <>
          {/* Save button */}
          <div className="flex justify-end">
            <button
              className="btn-blue !text-base !px-5 !py-2"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? "Сохранение..." : "Сохранить все"}
            </button>
          </div>

          {/* Levels grid */}
          <div className="flex flex-col gap-4 gold-scrollbar overflow-y-auto max-h-[70vh]">
            {levels.map((lvl, idx) => (
              <div
                key={lvl.level_number}
                className="gray-bg p-4 flex flex-col gap-3"
              >
                <div className="flex flex-wrap items-center gap-4">
                  <span className="gold-text text-lg font-medium min-w-[80px]">
                    Ур. {lvl.level_number}
                  </span>
                  <div className="flex items-center gap-2">
                    <label className="text-xs text-white/50">XP:</label>
                    <input
                      className="input-underline !w-[100px]"
                      type="number"
                      min={1}
                      value={lvl.required_xp || ""}
                      onChange={(e) =>
                        updateLevelXp(idx, parseInt(e.target.value) || 0)
                      }
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {renderRewards(idx, "free", lvl.free_rewards)}
                  {renderRewards(idx, "premium", lvl.premium_rewards)}
                </div>
              </div>
            ))}
          </div>

          {/* Bottom save */}
          <div className="flex justify-end">
            <button
              className="btn-blue !text-base !px-5 !py-2"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? "Сохранение..." : "Сохранить все"}
            </button>
          </div>
        </>
      )}
    </div>
  );
};

export default LevelsTab;
