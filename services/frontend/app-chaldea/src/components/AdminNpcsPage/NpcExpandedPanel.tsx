import type { RefObject } from 'react';
import ExpandedPanelShell from '../Admin/ExpandableList/ExpandedPanelShell';
import PanelTabs from '../Admin/ExpandableList/PanelTabs';
import ReadyToggle from '../Admin/ExpandableList/ReadyToggle';
import { toReadyMark } from '../Admin/ExpandableList/readyMark';
import NpcGeneralForm, { type RaceWithSubraces } from './NpcGeneralForm';
import NpcStatsEditor from './NpcStatsEditor';
import NpcEquipmentEditor from './NpcEquipmentEditor';
import DialogueEditor from './DialogueEditor';
import QuestEditor from './QuestEditor';
import NpcShopEditor from './NpcShopEditor';
import TeleportLinksPanel from './TeleportLinksPanel';
import GuardPatrolPanel from './GuardPatrolPanel';
import { NPC_TAB_LABELS, type NpcTabKey } from './npcTabKeys';
import type { NpcListItem } from './NpcRow';

/* FEAT-208: animated panel under an NPC plate (shared ExpandedPanelShell) — header with danger actions, tabs, active section. */

interface NpcExpandedPanelProps {
  /** null = create mode */
  npc: NpcListItem | null;
  tabs: NpcTabKey[];
  activeTab: NpcTabKey;
  onTabSelect: (tab: NpcTabKey) => void;
  racesData: RaceWithSubraces[];
  onSaved: (id: number, created: boolean) => void;
  onCancel: () => void;
  onDirtyChange: (dirty: boolean) => void;
  onDeleteRequest: () => void;
  onResurrect: () => void;
  resurrecting: boolean;
  /** FEAT-209: flips the «Готов» flag (no optimistic update — parent patches from the response) */
  onToggleReady: () => void;
  readyPending: boolean;
  /** Row to scroll into view once the panel has opened */
  scrollTargetRef: RefObject<HTMLDivElement>;
}

const NpcExpandedPanel = ({
  npc,
  tabs,
  activeTab,
  onTabSelect,
  racesData,
  onSaved,
  onCancel,
  onDirtyChange,
  onDeleteRequest,
  onResurrect,
  resurrecting,
  onToggleReady,
  readyPending,
  scrollTargetRef,
}: NpcExpandedPanelProps) => {
  const renderSection = () => {
    if (!npc || activeTab === 'general') {
      return (
        <NpcGeneralForm
          npcId={npc ? npc.id : null}
          racesData={racesData}
          onSaved={onSaved}
          onCancel={onCancel}
          onDirtyChange={onDirtyChange}
        />
      );
    }
    switch (activeTab) {
      case 'stats':
        return (
          <NpcStatsEditor
            embedded
            npcId={npc.id}
            npcName={npc.name}
            npcLevel={npc.level}
            racesData={racesData}
            onDirtyChange={onDirtyChange}
          />
        );
      case 'equipment':
        return <NpcEquipmentEditor embedded npcId={npc.id} npcName={npc.name} />;
      case 'dialogues':
        return <DialogueEditor embedded npcId={npc.id} npcName={npc.name} onDirtyChange={onDirtyChange} />;
      case 'quests':
        return <QuestEditor embedded npcId={npc.id} npcName={npc.name} onDirtyChange={onDirtyChange} />;
      case 'shop':
        return <NpcShopEditor embedded npcId={npc.id} npcName={npc.name} onDirtyChange={onDirtyChange} />;
      case 'teleports':
        return <TeleportLinksPanel npcId={npc.id} onDirtyChange={onDirtyChange} />;
      case 'patrol':
        return <GuardPatrolPanel npcId={npc.id} onDirtyChange={onDirtyChange} />;
      default:
        return null;
    }
  };

  return (
    <ExpandedPanelShell
      title={npc ? npc.name : 'Новый НПС'}
      actions={
        npc && (
          <>
            <ReadyToggle
              mark={toReadyMark(npc.npc_ready, npc.npc_ready_at, npc.npc_ready_by)}
              pending={readyPending}
              onToggle={onToggleReady}
              entityHint="НПС"
            />
            {npc.npc_status === 'dead' && (
              <button
                type="button"
                onClick={onResurrect}
                disabled={resurrecting}
                className="text-sm text-green-400 hover:text-green-300 transition-colors duration-200 disabled:opacity-50"
              >
                {resurrecting ? 'Воскрешение...' : 'Воскресить'}
              </button>
            )}
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
        <PanelTabs
          tabs={tabs}
          labels={NPC_TAB_LABELS}
          active={activeTab}
          onSelect={onTabSelect}
          layoutId="npc-panel-tab"
        />
      }
      bodyKey={`${npc ? npc.id : 'new'}-${activeTab}`}
      scrollTargetRef={scrollTargetRef}
    >
      {renderSection()}
    </ExpandedPanelShell>
  );
};

export default NpcExpandedPanel;
