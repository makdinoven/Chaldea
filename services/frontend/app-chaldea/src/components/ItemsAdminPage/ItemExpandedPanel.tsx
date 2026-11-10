import type { RefObject } from "react";
import type { ItemAdminListRow } from "../../api/items";
import ExpandedPanelShell from "../Admin/ExpandableList/ExpandedPanelShell";
import ReadyToggle from "../Admin/ExpandableList/ReadyToggle";
import { adminReadyMark } from "../Admin/ExpandableList/readyMark";
import ItemForm from "./ItemForm";
import type { ItemTabKey } from "./itemTabKeys";

/* FEAT-210: animated panel under an item plate — header (Готов / Выдать / Удалить) and the item form,
   whose tabs are sections of one form (the form renders the tab strip itself: the set follows the live type). */

interface ItemExpandedPanelProps {
  /** null = create mode */
  item: ItemAdminListRow | null;
  /** Bumped after a save → the form remounts and reloads the item */
  formSeq: number;
  /** Type preselected for a new item */
  defaultType?: string;
  urlTab: ItemTabKey | null;
  onTabSelect: (tab: ItemTabKey) => void;
  onTabNormalize: (tab: ItemTabKey) => void;
  onSaved: (id: number, created: boolean, tab: ItemTabKey) => void;
  onCancel: () => void;
  onDirtyChange: (dirty: boolean) => void;
  onIssue: () => void;
  onDeleteRequest: () => void;
  /** Flips the «Готов» mark (no optimistic update — the page patches from the response) */
  onToggleReady: () => void;
  readyPending: boolean;
  /** Row to scroll into view once the panel has opened */
  scrollTargetRef: RefObject<HTMLDivElement>;
}

const ItemExpandedPanel = ({
  item,
  formSeq,
  defaultType,
  urlTab,
  onTabSelect,
  onTabNormalize,
  onSaved,
  onCancel,
  onDirtyChange,
  onIssue,
  onDeleteRequest,
  onToggleReady,
  readyPending,
  scrollTargetRef,
}: ItemExpandedPanelProps) => (
  <ExpandedPanelShell
    title={item ? item.name : "Новый предмет"}
    actions={
      item && (
        <>
          <ReadyToggle
            mark={adminReadyMark(item)}
            pending={readyPending}
            onToggle={onToggleReady}
            entityHint="предмет"
          />
          <button
            type="button"
            onClick={onIssue}
            className="text-sm text-white hover:text-site-blue transition-colors duration-200"
          >
            Выдать
          </button>
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
    bodyKey={`${item ? item.id : "new"}-${formSeq}`}
    scrollTargetRef={scrollTargetRef}
  >
    <ItemForm
      selected={item ? item.id : undefined}
      defaultType={defaultType}
      urlTab={urlTab}
      onTabSelect={onTabSelect}
      onTabNormalize={onTabNormalize}
      onSaved={onSaved}
      onCancel={onCancel}
      onDirtyChange={onDirtyChange}
    />
  </ExpandedPanelShell>
);

export default ItemExpandedPanel;
