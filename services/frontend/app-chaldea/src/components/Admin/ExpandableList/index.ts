/**
 * FEAT-210 — shared kit of the expandable admin lists (NPCs, items, mobs).
 *
 * Typical page wiring:
 *   const { target, tab, rawTarget, open, setTab, close, normalize } = usePanelUrlState('item', isItemTabKey, 'general');
 *   const { panelDirty, onDirtyChange, guard, pendingLeave, confirmLeave, cancelLeave, resetDirty } = useDirtyGuard(target !== null);
 *   const { ready, setReady } = useReadyFilterUrlState();
 *   const geo = useGeoFilter({ onChanged: () => setPage(1) });   // list request only when geo.settled
 *   <GeoFilterSelects {...geo.selectProps} /> <ReadyFilterSelect value={ready} onChange={...} />
 *   <ExpandableRow open onToggle={() => guard(close)} avatar=… title=… ready={mark} cells=… gridClassName=… rowRef={openRowRef}>
 *     <ExpandedPanelShell title=… actions={<ReadyToggle … />} tabs={<PanelTabs … />} bodyKey=… scrollTargetRef={openRowRef}>
 *       {section editor with onDirtyChange → useDirtyReport inside}
 *     </ExpandedPanelShell>
 *   </ExpandableRow>
 *   <ConfirmationModal isOpen={pendingLeave} title="Несохранённые изменения"
 *     message="Есть несохранённые изменения. Уйти без сохранения?" onConfirm={confirmLeave} onCancel={cancelLeave} />
 */
export { default as ExpandableRow } from './ExpandableRow';
export { default as ExpandedPanelShell } from './ExpandedPanelShell';
export { default as PanelTabs } from './PanelTabs';
export { default as ReadyToggle } from './ReadyToggle';
export { default as ReadyFilterSelect } from './ReadyFilterSelect';
export { default as GeoFilterSelects, type GeoFilterSelectsProps } from './GeoFilterSelects';
export { usePanelUrlState, type PanelTarget } from './usePanelUrlState';
export { useDirtyGuard } from './useDirtyGuard';
export { useDirtyReport, useOpenSnapshotDirty } from './useDirtyReport';
export { useReadyFilterUrlState } from './useReadyFilterUrlState';
export { useGeoFilter } from './useGeoFilter';
export { readyTooltip, toReadyMark, adminReadyMark, type ReadyMark } from './readyMark';
export { parsePositiveId, useSearchParamsPatch } from './urlParams';
