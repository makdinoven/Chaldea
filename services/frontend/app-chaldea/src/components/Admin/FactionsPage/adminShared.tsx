import { useEffect, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { adminListFactions, type FactionAdminListItem } from '../../../api/factions';
import { fetchTitles } from '../../../api/titles';
import { apiErrorMessage } from '../../../api/errors';

/* FEAT-205 — small shared pieces of the admin «Фракции» section. */

export const LABEL = 'text-white/50 text-xs font-medium uppercase tracking-[0.06em]';
export const FIELD = 'input-underline w-full';
export const OPTION = 'bg-site-dark text-white';
export const INT_RE = /^\d*$/;
export const SIGNED_INT_RE = /^-?\d*$/;

/** A typed integer string → number, or null when empty / not a number. */
export const toInt = (value: string): number | null => {
  const t = value.trim();
  if (t === '' || t === '-') return null;
  const n = Number(t);
  return Number.isInteger(n) ? n : null;
};

/** All factions (incl. hidden) for selects; reloads when `reloadKey` changes. */
export const useFactionOptions = (reloadKey = 0): { factions: FactionAdminListItem[]; error: string | null } => {
  const [factions, setFactions] = useState<FactionAdminListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    adminListFactions()
      .then((list) => {
        if (!cancelled) {
          setFactions(list);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(apiErrorMessage(e, 'Не удалось загрузить список фракций'));
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);
  return { factions, error };
};

/* ── Non-repeatable quest select (conditions of entry / ranks) ── */

interface QuestRow {
  id: number;
  title: string;
  quest_type: string;
  npc_id: number;
}

let questPromise: Promise<QuestRow[]> | null = null;

export const invalidateQuestOptions = () => {
  questPromise = null;
};

const loadQuests = (): Promise<QuestRow[]> => {
  if (!questPromise) {
    questPromise = axios
      .get<QuestRow[]>('/locations/admin/quests')
      .then(({ data }) => (Array.isArray(data) ? data : []))
      .catch((e: unknown) => {
        questPromise = null;
        throw e;
      });
  }
  return questPromise;
};

/** Only NON-repeatable quests can be a condition (the backend rejects the rest). */
export const NonRepeatableQuestSelect = ({
  value,
  onChange,
  label = 'Задание',
  disabled = false,
}: {
  value: number | null;
  onChange: (id: number | null) => void;
  label?: string;
  disabled?: boolean;
}) => {
  const [quests, setQuests] = useState<QuestRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadQuests()
      .then((list) => {
        if (!cancelled) setQuests(list.filter((q) => q.quest_type !== 'repeatable'));
      })
      .catch((e) => {
        if (!cancelled) setError(apiErrorMessage(e, 'Не удалось загрузить задания'));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const known = value == null || (quests ?? []).some((q) => q.id === value);
  return (
    <label className="flex flex-col gap-1 min-w-0">
      <span className={LABEL}>{label}</span>
      <select
        value={value ?? ''}
        disabled={disabled || quests === null}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        className={FIELD}
      >
        <option value="" className={OPTION}>
          {quests === null && !error ? 'Загрузка...' : '— Нет —'}
        </option>
        {(quests ?? []).map((q) => (
          <option key={q.id} value={q.id} className={OPTION}>
            {q.title} (#{q.id})
          </option>
        ))}
        {!known && value != null && (
          <option value={value} className={OPTION}>
            #{value}
          </option>
        )}
      </select>
      {error ? (
        <span className="text-site-red text-xs">{error}</span>
      ) : (
        <span className="text-white/40 text-xs">Только неповторяемые задания</span>
      )}
    </label>
  );
};

/* ── Title select (rank reward) ── */

let titlesPromise: Promise<{ id: number; name: string }[]> | null = null;

const loadTitles = (): Promise<{ id: number; name: string }[]> => {
  if (!titlesPromise) {
    titlesPromise = fetchTitles({ page: 1, per_page: 100 })
      .then((r) => r.items.map((t) => ({ id: t.id_title, name: t.name })))
      .catch((e: unknown) => {
        titlesPromise = null;
        throw e;
      });
  }
  return titlesPromise;
};

export const TitleSelect = ({
  value,
  onChange,
  disabled = false,
}: {
  value: number | null;
  onChange: (id: number | null) => void;
  disabled?: boolean;
}) => {
  const [titles, setTitles] = useState<{ id: number; name: string }[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadTitles()
      .then((list) => {
        if (!cancelled) setTitles(list);
      })
      .catch((e) => {
        if (!cancelled) {
          const msg = e instanceof Error && e.message ? e.message : 'Не удалось загрузить титулы';
          setError(msg);
          toast.error(`Титулы: ${msg}`);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const known = value == null || (titles ?? []).some((t) => t.id === value);
  return (
    <label className="flex flex-col gap-1 min-w-0">
      <span className={LABEL}>Титул за звание</span>
      <select
        value={value ?? ''}
        disabled={disabled || titles === null}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        className={FIELD}
      >
        <option value="" className={OPTION}>
          {titles === null && !error ? 'Загрузка...' : '— Без титула —'}
        </option>
        {(titles ?? []).map((t) => (
          <option key={t.id} value={t.id} className={OPTION}>
            {t.name}
          </option>
        ))}
        {!known && value != null && (
          <option value={value} className={OPTION}>
            #{value}
          </option>
        )}
      </select>
      {error && <span className="text-site-red text-xs">{error}</span>}
    </label>
  );
};

/** Tab-like sub navigation used inside the section. */
export const SubTabs = <K extends string>({
  tabs,
  active,
  onChange,
}: {
  tabs: { key: K; label: string }[];
  active: K;
  onChange: (key: K) => void;
}) => (
  <div className="flex gap-1 sm:gap-2 border-b border-white/10 overflow-x-auto gold-scrollbar">
    {tabs.map((t) => (
      <button
        key={t.key}
        type="button"
        onClick={() => onChange(t.key)}
        className={`px-3 sm:px-4 py-2 -mb-px border-b-2 text-sm uppercase tracking-[0.06em] whitespace-nowrap transition-colors duration-200 ease-site ${
          t.key === active ? 'border-gold text-gold' : 'border-transparent text-white/50 hover:text-white'
        }`}
      >
        {t.label}
      </button>
    ))}
  </div>
);
