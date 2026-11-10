import { useCallback, useEffect, useState } from 'react';

/**
 * FEAT-208/210 — unsaved-changes guard of an expanded list panel.
 *
 * - `onDirtyChange` (stable) — pass to the section editors (they report via `useDirtyReport`)
 * - `guard(action)` — runs `action` now, or postpones it until the admin confirms leaving
 * - `pendingLeave` / `confirmLeave` / `cancelLeave` — drive the page's `ConfirmationModal`
 *   (title «Несохранённые изменения», message «Есть несохранённые изменения. Уйти без сохранения?»)
 * - `resetDirty()` — drop the flag (e.g. after the open element was deleted)
 *
 * While dirty, reload / tab close asks via `beforeunload`. The flag resets when `panelOpen` turns false.
 */
export const useDirtyGuard = (panelOpen: boolean) => {
  const [panelDirty, setPanelDirty] = useState(false);
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null);

  // A closed panel can't be dirty
  useEffect(() => {
    if (!panelOpen) setPanelDirty(false);
  }, [panelOpen]);

  // Reload / tab close with unsaved changes
  useEffect(() => {
    if (!panelDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [panelDirty]);

  const guard = useCallback(
    (action: () => void) => {
      if (panelDirty) setPendingAction(() => action);
      else action();
    },
    [panelDirty],
  );

  const confirmLeave = useCallback(() => {
    const action = pendingAction;
    setPendingAction(null);
    setPanelDirty(false);
    action?.();
  }, [pendingAction]);

  const cancelLeave = useCallback(() => setPendingAction(null), []);
  const onDirtyChange = useCallback((dirty: boolean) => setPanelDirty(dirty), []);
  const resetDirty = useCallback(() => setPanelDirty(false), []);

  return {
    panelDirty,
    onDirtyChange,
    guard,
    pendingLeave: pendingAction !== null,
    confirmLeave,
    cancelLeave,
    resetDirty,
  };
};
