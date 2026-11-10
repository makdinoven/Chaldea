import { useEffect, useState } from 'react';

/**
 * FEAT-208: forwards a section's "has unsaved changes" flag to the expanded panel
 * (wire `onDirtyChange` to `useDirtyGuard().onDirtyChange`).
 * Emits on every change and `false` on unmount.
 */
export const useDirtyReport = (dirty: boolean, onDirtyChange?: (dirty: boolean) => void) => {
  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);
};

/**
 * FEAT-208: dirty flag for an editor that is opened with some initial value.
 * A snapshot is taken when `open` becomes true (the values set in the same
 * batch as opening are the baseline); dirty = open && value differs from it.
 * Bump `openSeq` when the editor is re-opened for another record while already open.
 */
export const useOpenSnapshotDirty = (open: boolean, value: unknown, openSeq = 0): boolean => {
  const serialized = JSON.stringify(value);
  const [snapshot, setSnapshot] = useState<string | null>(null);

  useEffect(() => {
    setSnapshot(open ? serialized : null);
    // Only re-baseline when the editor opens / closes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, openSeq]);

  return open && snapshot !== null && snapshot !== serialized;
};
