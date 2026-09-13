import { useState, useCallback } from 'react';
import { checkSpelling, SpellCheckError, SpellError } from '../api/spellcheck';

export interface UseSpellCheckReturn {
  errors: SpellError[];
  loading: boolean;
  checked: boolean;
  /** Russian, player-facing message of the last failure, or `null`. */
  error: string | null;
  /**
   * Runs the check. Never rejects — it resolves with the Russian error message
   * when the check failed, or `null` on success, so the caller can also toast
   * it without reading a state value that is still stale in its closure.
   */
  runCheck: (text: string) => Promise<string | null>;
  /** «Пропустить» — drops an error without touching anyone's offsets. */
  dismissError: (index: number) => void;
  /** A correction was applied — drop it and re-sync the remaining offsets. */
  applyFix: (index: number, replacementLength: number) => void;
  /** Surface a failure that happened outside `runCheck` (e.g. a bad range). */
  setError: (message: string | null) => void;
  reset: () => void;
}

const GENERIC_ERROR = 'Не удалось проверить правописание. Попробуйте ещё раз.';

export const useSpellCheck = (): UseSpellCheckReturn => {
  const [errors, setErrors] = useState<SpellError[]>([]);
  const [loading, setLoading] = useState(false);
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runCheck = useCallback(async (text: string): Promise<string | null> => {
    setLoading(true);
    setChecked(false);
    setError(null);
    try {
      const result = await checkSpelling(text);
      setErrors(result);
      setChecked(true);
      return null;
    } catch (e) {
      // Never rethrow: the rejection used to propagate and leave the panel
      // blank, which is exactly the "invisible failure" the rules forbid.
      const message = e instanceof SpellCheckError ? e.message : GENERIC_ERROR;
      setErrors([]);
      setError(message);
      return message;
    } finally {
      setLoading(false);
    }
  }, []);

  const dismissError = useCallback((index: number) => {
    setErrors((prev) => prev.filter((_, i) => i !== index));
  }, []);

  /**
   * FEAT-157 (T5). Applying a correction rewrites the post, so every error that
   * sits **after** the corrected word moves by exactly
   * `replacementLength - error.len`. Shifting is exact and synchronous; the
   * alternative — re-running the check after every click — would fire a
   * third-party request per fix and could race the next click.
   *
   * Errors at the very same `pos` are overlapping reports of the same token and
   * are deliberately left alone (strictly greater comparison).
   */
  const applyFix = useCallback((index: number, replacementLength: number) => {
    setErrors((prev) => {
      const applied = prev[index];
      if (!applied) return prev;
      const delta = replacementLength - applied.len;
      return prev
        .filter((_, i) => i !== index)
        .map((err) =>
          err.pos > applied.pos ? { ...err, pos: err.pos + delta } : err,
        );
    });
  }, []);

  const reset = useCallback(() => {
    setErrors([]);
    setLoading(false);
    setChecked(false);
    setError(null);
  }, []);

  return {
    errors,
    loading,
    checked,
    error,
    runCheck,
    dismissError,
    applyFix,
    setError,
    reset,
  };
};
