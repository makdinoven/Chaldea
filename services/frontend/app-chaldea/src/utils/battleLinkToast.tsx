import toast from 'react-hot-toast';

interface BattleLinkToastOptions {
  text: string;
  /** Where «К бою» leads (`battlePath(...)`). */
  path: string;
  /** Router navigation — the Toaster lives outside the Router, so the caller passes its `navigate`. */
  onGo: (path: string) => void;
  tone?: 'default' | 'error';
  duration?: number;
}

/** A popup with a «К бою» button: a battle the player was pulled into (e.g. sea monsters on the deck, FEAT-214). */
export const showBattleLinkToast = ({ text, path, onGo, tone = 'default', duration }: BattleLinkToastOptions) =>
  toast(
    (t) => (
      <span className="flex flex-col sm:flex-row sm:items-center gap-2 min-w-0">
        <span className="break-words">{text}</span>
        <button
          type="button"
          className="btn-blue !py-1 !px-3 text-sm shrink-0 self-start sm:self-auto"
          onClick={() => {
            toast.dismiss(t.id);
            onGo(path);
          }}
        >
          К бою
        </button>
      </span>
    ),
    { duration, icon: tone === 'error' ? '⚔️' : undefined },
  );
