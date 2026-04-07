// SkillUpgradeModal — perk system (FEAT-125)
import { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import axios from 'axios';
import type {
  SkillWithPerks,
  ResolvedSkill,
  CharacterSkillState,
} from './types';
import PerkCard, { type PerkCardState } from './PerkCard';
import { ruDamageType, ruEffectName, ruTargetSide } from './skillLabels';

interface SkillUpgradeModalProps {
  skillId: number;
  characterId: number;
  onClose: () => void;
  onRefresh: () => void;
}

const extractError = (err: unknown, fallback: string): string => {
  const e = err as { response?: { data?: { detail?: string } }; message?: string };
  return e.response?.data?.detail || e.message || fallback;
};

const formatCountdown = (target: string | null): string | null => {
  if (!target) return null;
  const ms = new Date(target).getTime() - Date.now();
  if (ms <= 0) return null;
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  return `${h} ч ${m} мин`;
};

const SkillUpgradeModal = ({
  skillId,
  characterId,
  onClose,
  onRefresh,
}: SkillUpgradeModalProps) => {
  const [skill, setSkill] = useState<SkillWithPerks | null>(null);
  const [resolved, setResolved] = useState<ResolvedSkill | null>(null);
  const [charState, setCharState] = useState<CharacterSkillState | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [skillRes, resolvedRes, charSkillsRes] = await Promise.all([
        axios.get<SkillWithPerks>(`/skills/${skillId}`),
        axios.get<ResolvedSkill>(`/skills/${skillId}/resolved`, {
          params: { character_id: characterId },
        }),
        axios.get<CharacterSkillState[]>(`/skills/characters/${characterId}/skills`),
      ]);
      setSkill(skillRes.data);
      setResolved(resolvedRes.data);
      const cs = charSkillsRes.data.find((s) => s.skill_id === skillId) ?? null;
      setCharState(cs);
    } catch (err) {
      const msg = extractError(err, 'Ошибка загрузки навыка');
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [skillId, characterId]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const handleUpgrade = async () => {
    setBusy(true);
    try {
      await axios.post(`/skills/characters/${characterId}/skills/${skillId}/upgrade`);
      toast.success('Навык улучшен!');
      await loadAll();
      onRefresh();
    } catch (err) {
      const msg = extractError(err, 'Ошибка улучшения навыка');
      setError(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  const handlePickPerk = async (perkId: number) => {
    setBusy(true);
    try {
      await axios.post(
        `/skills/characters/${characterId}/skills/${skillId}/perks/${perkId}`
      );
      toast.success('Перк выбран!');
      await loadAll();
      onRefresh();
    } catch (err) {
      const msg = extractError(err, 'Ошибка выбора перка');
      setError(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  const handleReset = async () => {
    if (!charState || charState.level === 0) return;
    const confirmed = window.confirm(
      'Вы потеряете весь опыт, потраченный на улучшения этого навыка. ' +
      'Сброс будет недоступен в течение 24 часов. Продолжить?'
    );
    if (!confirmed) return;
    setBusy(true);
    try {
      await axios.post(`/skills/characters/${characterId}/skills/${skillId}/reset`);
      toast.success('Навык сброшен');
      await loadAll();
      onRefresh();
    } catch (err) {
      const msg = extractError(err, 'Ошибка сброса навыка');
      setError(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  const level = charState?.level ?? 0;
  const freePoints = charState?.free_perk_points ?? 0;
  const selectedPerkIds = new Set(charState?.selected_perk_ids ?? []);
  const upgradeCost = skill ? Math.floor(skill.purchase_cost / 2) : 0;
  const atMaxLevel = level >= 4;
  const canUpgrade = !!charState && !atMaxLevel && freePoints === 0 && !busy;

  const resetCountdown = formatCountdown(charState?.reset_available_at ?? null);
  const resetAvailable =
    !!charState &&
    charState.level > 0 &&
    (!charState.reset_available_at ||
      new Date(charState.reset_available_at).getTime() <= now);

  const getPerkState = (perkId: number): PerkCardState => {
    if (selectedPerkIds.has(perkId)) return 'selected';
    if (freePoints >= 1) return 'available';
    return 'locked';
  };

  return (
    <AnimatePresence>
      <motion.div
        key="overlay"
        className="modal-overlay fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm p-2 sm:p-4"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <motion.div
          key="content"
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          className="modal-content relative w-full max-w-[680px] max-h-[92vh] overflow-y-auto gold-scrollbar bg-[#12121e]/95 border border-white/10 rounded-card shadow-card"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Close */}
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="absolute top-2 right-3 text-white/60 hover:text-white text-2xl leading-none"
          >
            ×
          </button>

          <div className="p-4 sm:p-6">
            {loading && !skill && (
              <div className="flex items-center justify-center py-12">
                <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
              </div>
            )}

            {error && !skill && (
              <div className="text-center py-12">
                <p className="text-red-400 text-sm">{error}</p>
                <button
                  type="button"
                  onClick={() => void loadAll()}
                  className="btn-blue mt-4 px-4 py-2 text-sm"
                >
                  Повторить
                </button>
              </div>
            )}

            {skill && (
              <>
                {/* Header */}
                <div className="flex items-start gap-3 mb-4">
                  {skill.skill_image && (
                    <img
                      src={skill.skill_image}
                      alt={skill.name}
                      className="w-14 h-14 sm:w-16 sm:h-16 rounded-sm object-cover flex-shrink-0"
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <h2 className="gold-text text-xl sm:text-2xl font-medium">
                      {skill.name}
                    </h2>
                    <div className="text-white/60 text-xs sm:text-sm mt-0.5">
                      Уровень {level}/4
                      {freePoints > 0 && (
                        <span className="ml-2 text-gold">
                          • {freePoints} своб. очко перка
                        </span>
                      )}
                    </div>
                    {skill.description && (
                      <p className="text-white/50 text-xs mt-1 whitespace-pre-line">
                        {skill.description}
                      </p>
                    )}
                  </div>
                </div>

                {/* Base + final stats */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
                  <div className="rounded-card bg-white/[0.03] border border-white/10 p-3">
                    <h3 className="text-[10px] uppercase text-white/50 mb-1.5">База</h3>
                    <div className="text-xs sm:text-sm text-white/80 space-y-0.5">
                      <div>Энергия: {skill.base.cost_energy}</div>
                      <div>Мана: {skill.base.cost_mana}</div>
                      <div>КД: {skill.base.cooldown}</div>
                      <div>Требуется уровень: {skill.base.level_requirement}</div>
                    </div>
                  </div>
                  {resolved && (
                    <div className="rounded-card bg-gold/5 border border-gold/30 p-3">
                      <h3 className="text-[10px] uppercase text-gold/80 mb-1.5">Итог</h3>
                      <div className="text-xs sm:text-sm text-white space-y-0.5">
                        <div>Энергия: {resolved.cost_energy}</div>
                        <div>Мана: {resolved.cost_mana}</div>
                        <div>КД: {resolved.cooldown}</div>
                        <div>Требуется уровень: {resolved.level_requirement}</div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Resolved damage/effects */}
                {resolved && (resolved.damage_entries.length > 0 || resolved.effects.length > 0) && (
                  <div className="rounded-card bg-white/[0.03] border border-white/10 p-3 mb-4 text-xs sm:text-sm">
                    {resolved.damage_entries.map((d, i) => (
                      <div key={`d-${i}`} className="text-red-300/90">
                        Урон {d.amount} {ruDamageType(d.damage_type)}
                        {d.target_side ? ` (${ruTargetSide(d.target_side)})` : ''}
                      </div>
                    ))}
                    {resolved.effects.map((e, i) => (
                      <div key={`e-${i}`} className="text-blue-300/90">
                        {ruEffectName(e.effect_name, e.attribute_key)}
                        {e.duration ? ` (${e.duration} ход.)` : ''}
                      </div>
                    ))}
                  </div>
                )}

                {/* Actions */}
                <div className="flex flex-col sm:flex-row gap-2 mb-4">
                  <button
                    type="button"
                    onClick={handleUpgrade}
                    disabled={!canUpgrade}
                    className="btn-blue flex-1 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {atMaxLevel
                      ? 'Максимальный уровень'
                      : freePoints > 0
                        ? 'Сначала выберите перк'
                        : `Улучшить (${upgradeCost} опыта)`}
                  </button>
                  <button
                    type="button"
                    onClick={handleReset}
                    disabled={!resetAvailable || busy}
                    className="btn-line flex-1 py-2 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {resetCountdown
                      ? `Сброс через ${resetCountdown}`
                      : charState && charState.level === 0
                        ? 'Нечего сбрасывать'
                        : 'Сбросить'}
                  </button>
                </div>

                {/* Perk pool */}
                <h3 className="text-white/70 text-sm mb-2">
                  Пул перков ({skill.perks.length})
                  {skill.perks.length < 4 && (
                    <span className="text-amber-400/80 text-xs ml-2">
                      (минимум 4 — сейчас не хватает)
                    </span>
                  )}
                </h3>

                {skill.perks.length === 0 ? (
                  <p className="text-white/40 text-xs italic">Перки ещё не заданы.</p>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 sm:gap-3">
                    {skill.perks.map((perk) => (
                      <PerkCard
                        key={perk.id}
                        perk={perk}
                        state={getPerkState(perk.id)}
                        onPick={handlePickPerk}
                      />
                    ))}
                  </div>
                )}

                {error && skill && (
                  <p className="text-red-400 text-xs mt-3">{error}</p>
                )}
              </>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};

export default SkillUpgradeModal;
