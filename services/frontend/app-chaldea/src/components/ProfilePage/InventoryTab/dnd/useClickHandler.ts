import { useRef, useCallback, useEffect } from 'react';

interface UseClickHandlerOptions {
  item: { item: { item_type: string } };
  onSingleClick: (e: React.MouseEvent) => void;
  onDoubleClick: (e: React.MouseEvent) => void;
  isEquippable: boolean;
}

interface ClickHandlers {
  onClick: (e: React.MouseEvent) => void;
  onDoubleClick: (e: React.MouseEvent) => void;
}

const CLICK_DELAY = 250;

/**
 * Hook for discriminating single-click (context menu) and double-click (equip).
 *
 * - Equippable items: single click is delayed by 250ms to detect double-click.
 * - Non-equippable items: single click fires immediately, no delay.
 */
const useClickHandler = ({
  onSingleClick,
  onDoubleClick,
  isEquippable,
}: UseClickHandlerOptions): ClickHandlers => {
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingEventRef = useRef<React.MouseEvent | null>(null);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();

      // Non-equippable items: no delay, open context menu immediately
      if (!isEquippable) {
        onSingleClick(e);
        return;
      }

      // Equippable items: wait for potential double-click
      if (timeoutRef.current) {
        // Second click arrived before timeout — treat as double-click
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
        const firstEvent = pendingEventRef.current;
        pendingEventRef.current = null;
        if (firstEvent) {
          onDoubleClick(firstEvent);
        }
        return;
      }

      // First click: store event and start timer
      pendingEventRef.current = e;
      // Persist the synthetic event so it survives the timeout
      e.persist?.();

      timeoutRef.current = setTimeout(() => {
        timeoutRef.current = null;
        const storedEvent = pendingEventRef.current;
        pendingEventRef.current = null;
        if (storedEvent) {
          onSingleClick(storedEvent);
        }
      }, CLICK_DELAY);
    },
    [isEquippable, onSingleClick, onDoubleClick],
  );

  const handleDoubleClick = useCallback(
    (e: React.MouseEvent) => {
      // Prevent default browser double-click behavior (text selection)
      e.preventDefault();
      e.stopPropagation();
    },
    [],
  );

  return {
    onClick: handleClick,
    onDoubleClick: handleDoubleClick,
  };
};

export default useClickHandler;
