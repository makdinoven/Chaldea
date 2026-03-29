import { useState, useEffect, useCallback } from "react";
import toast from "react-hot-toast";
import {
  getAdminSeasons,
  getSeasonMissions,
  upsertSeasonMissions,
} from "../../../api/battlePassAdmin";
import type { AdminSeason, AdminMission } from "../../../api/battlePassAdmin";

/* ── Constants ── */

const MISSION_TYPES = [
  { value: "kill_mobs", label: "Убить мобов" },
  { value: "write_posts", label: "Написать постов" },
  { value: "level_up", label: "Поднять уровень" },
  { value: "visit_locations", label: "Посетить локации" },
  { value: "earn_gold", label: "Заработать золото" },
  { value: "spend_gold", label: "Потратить золото" },
  { value: "quest_complete", label: "Выполнить квесты (заглушка)" },
  { value: "dungeon_run", label: "Сходить в данж (заглушка)" },
  { value: "resource_gather", label: "Добыть ресурсы (заглушка)" },
];

const TOTAL_WEEKS = 6;

interface MissionRow {
  week_number: number;
  mission_type: string;
  description: string;
  target_count: number;
  xp_reward: number;
}

const emptyMission = (week: number): MissionRow => ({
  week_number: week,
  mission_type: "kill_mobs",
  description: "",
  target_count: 10,
  xp_reward: 50,
});

/* ── Component ── */

const MissionsTab = () => {
  const [seasons, setSeasons] = useState<AdminSeason[]>([]);
  const [selectedSeasonId, setSelectedSeasonId] = useState<number | null>(null);
  const [weekMissions, setWeekMissions] = useState<Record<number, MissionRow[]>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [expandedWeek, setExpandedWeek] = useState<number | null>(1);

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

  /* Load missions when season changes */
  const loadMissions = useCallback(async (seasonId: number) => {
    setLoading(true);
    try {
      const data = await getSeasonMissions(seasonId);
      const grouped: Record<number, MissionRow[]> = {};
      for (let w = 1; w <= TOTAL_WEEKS; w++) {
        const key = String(w);
        const arr = data.weeks[key] ?? [];
        grouped[w] = arr.map((m: AdminMission) => ({
          week_number: m.week_number,
          mission_type: m.mission_type,
          description: m.description,
          target_count: m.target_count,
          xp_reward: m.xp_reward,
        }));
      }
      setWeekMissions(grouped);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Не удалось загрузить задания";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedSeasonId !== null) {
      loadMissions(selectedSeasonId);
    }
  }, [selectedSeasonId, loadMissions]);

  /* ── Mutations ── */

  const updateMission = (
    week: number,
    idx: number,
    field: keyof MissionRow,
    value: string | number,
  ) => {
    setWeekMissions((prev) => {
      const copy = { ...prev };
      const missions = [...(copy[week] ?? [])];
      missions[idx] = { ...missions[idx], [field]: value };
      copy[week] = missions;
      return copy;
    });
  };

  const addMission = (week: number) => {
    setWeekMissions((prev) => {
      const copy = { ...prev };
      copy[week] = [...(copy[week] ?? []), emptyMission(week)];
      return copy;
    });
  };

  const removeMission = (week: number, idx: number) => {
    setWeekMissions((prev) => {
      const copy = { ...prev };
      copy[week] = (copy[week] ?? []).filter((_, i) => i !== idx);
      return copy;
    });
  };

  /* ── Save all ── */

  const handleSave = async () => {
    if (selectedSeasonId === null) return;
    setSaving(true);
    try {
      const allMissions: Omit<AdminMission, "id">[] = [];
      for (let w = 1; w <= TOTAL_WEEKS; w++) {
        const missions = weekMissions[w] ?? [];
        for (const m of missions) {
          allMissions.push({
            week_number: w,
            mission_type: m.mission_type,
            description: m.description,
            target_count: m.target_count,
            xp_reward: m.xp_reward,
          });
        }
      }
      await upsertSeasonMissions(selectedSeasonId, allMissions);
      toast.success("Задания сохранены");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Ошибка сохранения";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const toggleWeek = (week: number) => {
    setExpandedWeek((prev) => (prev === week ? null : week));
  };

  return (
    <div className="flex flex-col gap-5">
      {/* Season selector */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
        <h2 className="gold-text text-2xl font-medium uppercase">Задания</h2>
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

          {/* Weeks accordion */}
          <div className="flex flex-col gap-3">
            {Array.from({ length: TOTAL_WEEKS }, (_, i) => i + 1).map((week) => {
              const missions = weekMissions[week] ?? [];
              const isOpen = expandedWeek === week;
              return (
                <div key={week} className="gray-bg overflow-hidden">
                  {/* Week header */}
                  <button
                    onClick={() => toggleWeek(week)}
                    className="w-full flex items-center justify-between p-4 hover:bg-white/[0.05] transition-colors duration-200"
                  >
                    <span className="text-white font-medium">
                      Неделя {week}{" "}
                      <span className="text-white/40 text-sm font-normal">
                        ({missions.length} зад.{" "})
                      </span>
                    </span>
                    <span
                      className={`text-white/50 transition-transform duration-200 ${
                        isOpen ? "rotate-180" : ""
                      }`}
                    >
                      &#9660;
                    </span>
                  </button>

                  {/* Week content */}
                  {isOpen && (
                    <div className="px-4 pb-4 flex flex-col gap-3">
                      {missions.map((m, idx) => (
                        <div
                          key={idx}
                          className="flex flex-col gap-2 p-3 bg-white/[0.03] rounded-card"
                        >
                          <div className="flex flex-wrap items-center gap-3">
                            <select
                              className="input-underline !w-auto min-w-[180px]"
                              value={m.mission_type}
                              onChange={(e) =>
                                updateMission(week, idx, "mission_type", e.target.value)
                              }
                            >
                              {MISSION_TYPES.map((t) => (
                                <option
                                  key={t.value}
                                  value={t.value}
                                  className="bg-site-dark text-white"
                                >
                                  {t.label}
                                </option>
                              ))}
                            </select>

                            <div className="flex items-center gap-1">
                              <label className="text-xs text-white/50">Цель:</label>
                              <input
                                className="input-underline !w-[80px]"
                                type="number"
                                min={1}
                                value={m.target_count || ""}
                                onChange={(e) =>
                                  updateMission(
                                    week,
                                    idx,
                                    "target_count",
                                    parseInt(e.target.value) || 0,
                                  )
                                }
                              />
                            </div>

                            <div className="flex items-center gap-1">
                              <label className="text-xs text-white/50">XP:</label>
                              <input
                                className="input-underline !w-[80px]"
                                type="number"
                                min={0}
                                value={m.xp_reward || ""}
                                onChange={(e) =>
                                  updateMission(
                                    week,
                                    idx,
                                    "xp_reward",
                                    parseInt(e.target.value) || 0,
                                  )
                                }
                              />
                            </div>

                            <button
                              onClick={() => removeMission(week, idx)}
                              className="text-site-red hover:text-white text-sm transition-colors ml-auto"
                            >
                              Удалить
                            </button>
                          </div>

                          <input
                            className="input-underline w-full"
                            placeholder="Описание задания..."
                            value={m.description}
                            onChange={(e) =>
                              updateMission(week, idx, "description", e.target.value)
                            }
                          />
                        </div>
                      ))}

                      <button
                        onClick={() => addMission(week)}
                        className="text-sm text-site-blue hover:text-white transition-colors self-start"
                      >
                        + Добавить задание
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
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

export default MissionsTab;
