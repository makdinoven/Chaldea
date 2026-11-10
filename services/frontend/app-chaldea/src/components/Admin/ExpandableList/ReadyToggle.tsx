import { readyTooltip, type ReadyMark } from './readyMark';

/**
 * FEAT-209/210 — «Готов» chip for the panel header (`ExpandedPanelShell` `actions`).
 * No optimistic update: the parent calls the API in `onToggle`, keeps `pending` true meanwhile and
 * patches its row from the response.
 */
interface ReadyToggleProps {
  mark: ReadyMark;
  pending: boolean;
  onToggle: () => void;
  /** Accusative noun for the hint «Отметить <entityHint> готовым», e.g. «НПС», «предмет», «моба» */
  entityHint: string;
}

const ReadyToggle = ({ mark, pending, onToggle, entityHint }: ReadyToggleProps) => (
  <button
    type="button"
    onClick={onToggle}
    disabled={pending}
    aria-pressed={mark.ready}
    title={
      mark.ready
        ? readyTooltip(mark.by, mark.at) ?? 'Снять отметку «Готов»'
        : `Отметить ${entityHint} готовым`
    }
    className={`chip-outline rounded-full px-3 py-1 text-xs font-medium disabled:opacity-50 ${
      mark.ready ? 'chip-outline-active' : ''
    }`}
  >
    {mark.ready ? '✓ Готов' : 'Готов'}
  </button>
);

export default ReadyToggle;
