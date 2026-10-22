import { useCallback, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import axios from 'axios';
import { parseServerDate } from '../../utils/serverDate';
import { ruDamageType, ruEffectName, ruTargetSide } from './skillLabels';
import { toSameOriginMedia } from '../pages/BattlePage/Arena3D/sameOriginMedia';
import type { SkillPageAction, SkillPageModel, SkillPagePerk } from './Books3D/skillPageModel';
import type { CharacterSkillState, ResolvedSkill, SkillPerkRead, SkillWithPerks } from './types';

/*
  Everything a skill's spread in a book needs from the game: what to write on
  its two pages, and what each control there does. The same requests and rules
  as SkillUpgradeModal, which serves the 2D wheel.
*/

const MAX_LEVEL = 4;
/** Below this many perks the pool is short of what the design calls for; the page says so. */
const MIN_PERKS = 4;

const extractError = (err: unknown, fallback: string): string => {
  const e = err as { response?: { data?: { detail?: string } }; message?: string };
  return e.response?.data?.detail || e.message || fallback;
};

// `reset_available_at` comes from skills-service as naive UTC, so it is read in
// the server's frame — the same instant the server uses to allow a reset.
const countdown = (target: string | null, now: number): string | null => {
  const at = parseServerDate(target);
  if (!at) return null;
  const ms = at.getTime() - now;
  if (ms <= 0) return null;
  return `${Math.floor(ms / 3_600_000)} ч ${Math.floor((ms % 3_600_000) / 60_000)} мин`;
};

const signed = (value: number) => (value > 0 ? `+${value}` : `−${Math.abs(value)}`);

/** A perk's changes as short lines of text. */
const perkChanges = (perk: SkillPerkRead): string[] => {
  const lines: string[] = [];
  const delta = (value: number | null, label: string) => {
    if (value != null && value !== 0) lines.push(`${label}: ${signed(value)}`);
  };
  delta(perk.delta_cost_energy, 'Энергия');
  delta(perk.delta_cost_mana, 'Мана');
  delta(perk.delta_cooldown, 'Откат');
  delta(perk.delta_level_requirement, 'Треб. уровень');
  for (const d of perk.damage_entries)
    lines.push(`+${d.amount} ${ruDamageType(d.damage_type)}${d.target_side ? ` (${ruTargetSide(d.target_side)})` : ''}`);
  for (const e of perk.effects)
    lines.push(`${ruEffectName(e.effect_name, e.attribute_key)}${e.duration ? ` (${e.duration} ход.)` : ''}`);
  return lines;
};

interface UseSkillPageArgs {
  /** The skill whose spread is open, or null. */
  skillId: number | null;
  characterId: number | null;
  onBack: () => void;
  onRefresh: () => void;
}

const useSkillPage = ({ skillId, characterId, onBack, onRefresh }: UseSkillPageArgs) => {
  const [skill, setSkill] = useState<SkillWithPerks | null>(null);
  const [resolved, setResolved] = useState<ResolvedSkill | null>(null);
  const [charState, setCharState] = useState<CharacterSkillState | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingReset, setConfirmingReset] = useState(false);
  const [perkPage, setPerkPage] = useState(0);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  const loadAll = useCallback(async () => {
    if (skillId === null || characterId === null) return;
    setLoading(true);
    setError(null);
    try {
      const [skillRes, resolvedRes, charSkillsRes] = await Promise.all([
        axios.get<SkillWithPerks>(`/skills/${skillId}`),
        axios.get<ResolvedSkill>(`/skills/${skillId}/resolved`, { params: { character_id: characterId } }),
        axios.get<CharacterSkillState[]>(`/skills/characters/${characterId}/skills`),
      ]);
      setSkill(skillRes.data);
      setResolved(resolvedRes.data);
      setCharState(charSkillsRes.data.find((s) => s.skill_id === skillId) ?? null);
    } catch (err) {
      const msg = extractError(err, 'Ошибка загрузки навыка');
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [skillId, characterId]);

  // A different skill starts clean: no stale card from the last one.
  useEffect(() => {
    setSkill(null);
    setResolved(null);
    setCharState(null);
    setConfirmingReset(false);
    setPerkPage(0);
    void loadAll();
  }, [loadAll]);

  const level = charState?.level ?? 0;
  const freePoints = charState?.free_perk_points ?? 0;

  const model: SkillPageModel | null = useMemo(() => {
    if (skillId === null) return null;
    if (!skill) {
      return {
        skillId,
        loading,
        error,
        title: '',
        image: null,
        description: null,
        level: 0,
        maxLevel: MAX_LEVEL,
        freePerkPoints: 0,
        stats: [],
        effects: [],
        upgrade: { label: '', enabled: false, busy: false },
        reset: { label: '', enabled: false },
        confirmingReset: false,
        perks: [],
        perkNote: null,
        perkPage: 0,
      };
    }
    const selected = new Set(charState?.selected_perk_ids ?? []);
    const atMax = level >= MAX_LEVEL;
    const resetAt = charState?.reset_available_at ? parseServerDate(charState.reset_available_at)?.getTime() ?? NaN : null;
    const resetReady = !!charState && charState.level > 0 && (resetAt === null || resetAt <= now);
    const wait = countdown(charState?.reset_available_at ?? null, now);

    const perks: SkillPagePerk[] = skill.perks.map((p) => ({
      id: p.id,
      name: p.name,
      description: p.description,
      changes: perkChanges(p),
      state: selected.has(p.id) ? 'selected' : freePoints >= 1 ? 'available' : 'locked',
    }));

    return {
      skillId,
      loading,
      error,
      title: skill.name,
      image: toSameOriginMedia(skill.skill_image),
      description: skill.description,
      level,
      maxLevel: MAX_LEVEL,
      freePerkPoints: freePoints,
      stats: [
        { label: 'Энергия', base: skill.base.cost_energy, total: resolved?.cost_energy ?? skill.base.cost_energy },
        { label: 'Мана', base: skill.base.cost_mana, total: resolved?.cost_mana ?? skill.base.cost_mana },
        { label: 'Откат', base: skill.base.cooldown, total: resolved?.cooldown ?? skill.base.cooldown },
        {
          label: 'Треб. уровень',
          base: skill.base.level_requirement,
          total: resolved?.level_requirement ?? skill.base.level_requirement,
        },
      ],
      effects: [
        ...(resolved?.damage_entries ?? []).map((d) => ({
          text: `Урон ${d.amount} ${ruDamageType(d.damage_type)}${d.target_side ? ` (${ruTargetSide(d.target_side)})` : ''}`,
          tone: 'damage' as const,
        })),
        ...(resolved?.effects ?? []).map((e) => ({
          text: `${ruEffectName(e.effect_name, e.attribute_key)}${e.duration ? ` (${e.duration} ход.)` : ''}`,
          tone: 'effect' as const,
        })),
      ],
      upgrade: {
        label: atMax
          ? 'Наивысший уровень'
          : freePoints > 0
            ? 'Сначала выберите перк'
            : busy
              ? 'Улучшаю…'
              : `Улучшить — ${Math.floor(skill.purchase_cost / 2)} опыта`,
        enabled: !!charState && !atMax && freePoints === 0 && !busy,
        busy,
      },
      reset: {
        label: wait ? `Сброс через ${wait}` : charState && charState.level === 0 ? 'Сбрасывать нечего' : 'Сбросить навык',
        enabled: resetReady && !busy,
      },
      confirmingReset,
      perks,
      perkNote:
        freePoints > 0
          ? `Можно выбрать перк: ${freePoints}`
          : skill.perks.length < MIN_PERKS
            ? `Перков меньше ${MIN_PERKS} — пул ещё не собран`
            : null,
      perkPage,
    };
  }, [skillId, skill, resolved, charState, loading, error, level, freePoints, busy, now, confirmingReset, perkPage]);

  /** Runs a request that changes the skill, then reloads it and the tree's progress. */
  const act = useCallback(
    async (url: string, success: string, failure: string) => {
      setBusy(true);
      try {
        await axios.post(url);
        toast.success(success);
        await loadAll();
        onRefresh();
      } catch (err) {
        const msg = extractError(err, failure);
        setError(msg);
        toast.error(msg);
      } finally {
        setBusy(false);
      }
    },
    [loadAll, onRefresh],
  );

  const onAction = useCallback(
    (action: SkillPageAction) => {
      if (skillId === null || characterId === null) return;
      const base = `/skills/characters/${characterId}/skills/${skillId}`;
      switch (action.kind) {
        case 'back':
          onBack();
          return;
        case 'retry':
          void loadAll();
          return;
        case 'perkPage':
          setPerkPage(action.page);
          return;
        case 'reset':
          if (model?.reset.enabled) setConfirmingReset(true);
          return;
        case 'cancelReset':
          setConfirmingReset(false);
          return;
        case 'confirmReset':
          setConfirmingReset(false);
          void act(`${base}/reset`, 'Навык сброшен', 'Ошибка сброса навыка');
          return;
        case 'upgrade':
          if (model?.upgrade.enabled) void act(`${base}/upgrade`, 'Навык улучшен!', 'Ошибка улучшения навыка');
          return;
        case 'pick':
          if (!busy && freePoints >= 1) void act(`${base}/perks/${action.perkId}`, 'Перк выбран!', 'Ошибка выбора перка');
      }
    },
    [skillId, characterId, onBack, loadAll, model, act, busy, freePoints],
  );

  return { model, onAction };
};

export default useSkillPage;
