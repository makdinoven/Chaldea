import { useCallback, useEffect, useState, type RefObject } from 'react';
import toast from 'react-hot-toast';
import ExpandedPanelShell from '../ExpandableList/ExpandedPanelShell';
import PanelTabs from '../ExpandableList/PanelTabs';
import ReadyToggle from '../ExpandableList/ReadyToggle';
import { adminReadyMark } from '../ExpandableList/readyMark';
import { fetchMobTemplate, type MobTemplateDetail, type MobTemplateListItem } from '../../../api/mobs';
import { apiErrorMessage } from '../../../api/errors';
import AdminMobTemplateForm from './AdminMobTemplateForm';
import MobStatsEditor from './MobStatsEditor';
import AdminMobSkills from './AdminMobSkills';
import AdminMobLoot from './AdminMobLoot';
import AdminMobSpawns from './AdminMobSpawns';
import { MOB_TAB_LABELS, type MobTabKey } from './mobTabKeys';

/* FEAT-210: animated panel under a mob plate — header («Готов», «Удалить»), tabs, active section.
   Loads the template detail itself (skills / loot / spawns / stats props). */

interface MobExpandedPanelProps {
  /** null = create mode */
  mob: MobTemplateListItem | null;
  tabs: MobTabKey[];
  activeTab: MobTabKey;
  onTabSelect: (tab: MobTabKey) => void;
  onSaved: (id: number, created: boolean) => void;
  onCancel: () => void;
  onDirtyChange: (dirty: boolean) => void;
  onDeleteRequest: () => void;
  onToggleReady: () => void;
  readyPending: boolean;
  /** Skills / loot / spawns saved — the list (spawn count) must be refreshed */
  onChanged: (id: number) => void;
  scrollTargetRef: RefObject<HTMLDivElement>;
}

const Spinner = () => (
  <div className="flex items-center justify-center py-8">
    <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
  </div>
);

const MobExpandedPanel = ({
  mob,
  tabs,
  activeTab,
  onTabSelect,
  onSaved,
  onCancel,
  onDirtyChange,
  onDeleteRequest,
  onToggleReady,
  readyPending,
  onChanged,
  scrollTargetRef,
}: MobExpandedPanelProps) => {
  const mobId = mob?.id ?? null;
  const [detail, setDetail] = useState<MobTemplateDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  const loadDetail = useCallback(async (id: number) => {
    try {
      const data = await fetchMobTemplate(id);
      setDetail(data);
      setDetailError(null);
    } catch (err) {
      const message = apiErrorMessage(err, 'Не удалось загрузить данные моба');
      setDetailError(message);
      toast.error(message);
    }
  }, []);

  useEffect(() => {
    setDetail(null);
    setDetailError(null);
    if (mobId !== null) loadDetail(mobId);
  }, [mobId, loadDetail]);

  const handleSaved = (id: number, created: boolean) => {
    if (!created) loadDetail(id);
    onSaved(id, created);
  };

  const handleSubUpdate = () => {
    if (mobId === null) return;
    loadDetail(mobId);
    onChanged(mobId);
  };

  const renderSection = () => {
    if (!mob || activeTab === 'general') {
      return (
        <AdminMobTemplateForm
          editingId={mob ? mob.id : null}
          onSaved={handleSaved}
          onCancel={onCancel}
          onDirtyChange={onDirtyChange}
        />
      );
    }
    if (detailError && !detail) {
      return <p className="text-site-red text-sm">{detailError}</p>;
    }
    if (!detail || detail.id !== mob.id) return <Spinner />;
    switch (activeTab) {
      case 'stats':
        return (
          <MobStatsEditor
            templateId={mob.id}
            idClass={detail.id_class}
            baseAttributes={detail.base_attributes}
            onDirtyChange={onDirtyChange}
          />
        );
      case 'skills':
        return (
          <AdminMobSkills
            templateId={mob.id}
            skills={detail.skills}
            onUpdate={handleSubUpdate}
            onDirtyChange={onDirtyChange}
          />
        );
      case 'loot':
        return (
          <AdminMobLoot
            templateId={mob.id}
            lootTable={detail.loot_entries}
            onUpdate={handleSubUpdate}
            onDirtyChange={onDirtyChange}
          />
        );
      case 'spawns':
        return (
          <AdminMobSpawns
            templateId={mob.id}
            spawns={detail.spawn_locations}
            onUpdate={handleSubUpdate}
            onDirtyChange={onDirtyChange}
          />
        );
      default:
        return null;
    }
  };

  return (
    <ExpandedPanelShell
      title={mob ? mob.name : 'Новый моб'}
      actions={
        mob && (
          <>
            <ReadyToggle mark={adminReadyMark(mob)} pending={readyPending} onToggle={onToggleReady} entityHint="моба" />
            <button
              type="button"
              onClick={onDeleteRequest}
              className="text-sm text-site-red hover:text-white transition-colors duration-200"
            >
              Удалить
            </button>
          </>
        )
      }
      tabs={
        <PanelTabs tabs={tabs} labels={MOB_TAB_LABELS} active={activeTab} onSelect={onTabSelect} layoutId="mob-panel-tab" />
      }
      bodyKey={`${mob ? mob.id : 'new'}-${activeTab}`}
      scrollTargetRef={scrollTargetRef}
    >
      {renderSection()}
    </ExpandedPanelShell>
  );
};

export default MobExpandedPanel;
