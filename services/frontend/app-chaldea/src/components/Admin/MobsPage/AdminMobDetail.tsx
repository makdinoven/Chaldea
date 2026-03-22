import { useEffect, useState } from 'react';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchMobTemplate,
  selectSelectedTemplate,
  selectDetailLoading,
  selectDetailError,
  clearSelectedTemplate,
} from '../../../redux/slices/mobsSlice';
import AdminMobSkills from './AdminMobSkills';
import AdminMobLoot from './AdminMobLoot';
import AdminMobSpawns from './AdminMobSpawns';

interface AdminMobDetailProps {
  templateId: number;
  onClose: () => void;
}

const TABS = [
  { key: 'skills', label: 'Навыки' },
  { key: 'loot', label: 'Лут-таблица' },
  { key: 'spawns', label: 'Спавн' },
] as const;

type TabKey = typeof TABS[number]['key'];

const TIER_LABELS: Record<string, string> = {
  normal: 'Обычный',
  elite: 'Элитный',
  boss: 'Босс',
};

const TIER_COLORS: Record<string, string> = {
  normal: 'bg-white/20 text-white',
  elite: 'bg-purple-500/30 text-purple-300',
  boss: 'bg-site-red/30 text-site-red',
};

const AdminMobDetail = ({ templateId, onClose }: AdminMobDetailProps) => {
  const dispatch = useAppDispatch();
  const template = useAppSelector(selectSelectedTemplate);
  const loading = useAppSelector(selectDetailLoading);
  const error = useAppSelector(selectDetailError);
  const [activeTab, setActiveTab] = useState<TabKey>('skills');

  useEffect(() => {
    dispatch(fetchMobTemplate(templateId));
    return () => {
      dispatch(clearSelectedTemplate());
    };
  }, [dispatch, templateId]);

  const reload = () => {
    dispatch(fetchMobTemplate(templateId));
  };

  if (loading) {
    return (
      <div className="w-full max-w-[1240px] mx-auto flex flex-col gap-6">
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full max-w-[1240px] mx-auto flex flex-col gap-6">
        <div className="text-site-red text-sm">{error}</div>
        <button onClick={onClose} className="btn-line !w-auto !px-6">
          Назад
        </button>
      </div>
    );
  }

  if (!template) return null;

  return (
    <div className="w-full max-w-[1240px] mx-auto flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <button
          onClick={onClose}
          className="text-sm text-white/50 hover:text-site-blue transition-colors duration-200 self-start"
        >
          &larr; Назад к списку
        </button>
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">
          {template.name}
        </h1>
        <span className={`px-3 py-1 rounded-full text-xs font-medium self-start ${TIER_COLORS[template.tier] || ''}`}>
          {TIER_LABELS[template.tier] || template.tier}
        </span>
        <span className="text-white/50 text-sm">
          LVL {template.level}
        </span>
      </div>

      {template.description && (
        <p className="text-white/70 text-sm">{template.description}</p>
      )}

      <div className="flex gap-4 text-sm text-white/70">
        <span>Опыт: <span className="text-white">{template.xp_reward}</span></span>
        <span>Золото: <span className="text-gold">{template.gold_reward}</span></span>
        <span>Респавн: <span className="text-white">{template.respawn_enabled ? `${template.respawn_seconds ?? 0} сек` : 'Выкл'}</span></span>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-white/10">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 text-sm font-medium transition-colors duration-200 border-b-2 ${
              activeTab === tab.key
                ? 'text-gold border-gold'
                : 'text-white/50 border-transparent hover:text-white hover:border-white/30'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {activeTab === 'skills' && (
          <AdminMobSkills templateId={templateId} skills={template.skills} onUpdate={reload} />
        )}
        {activeTab === 'loot' && (
          <AdminMobLoot templateId={templateId} lootTable={template.loot_entries} onUpdate={reload} />
        )}
        {activeTab === 'spawns' && (
          <AdminMobSpawns templateId={templateId} spawns={template.spawn_locations} onUpdate={reload} />
        )}
      </div>
    </div>
  );
};

export default AdminMobDetail;
