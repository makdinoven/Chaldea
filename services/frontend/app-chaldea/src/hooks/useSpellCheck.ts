import { useState, useCallback } from 'react';
import { checkSpelling, SpellError } from '../api/spellcheck';

export interface UseSpellCheckReturn {
  errors: SpellError[];
  loading: boolean;
  checked: boolean;
  runCheck: (text: string) => Promise<void>;
  dismissError: (index: number) => void;
  reset: () => void;
}

export const useSpellCheck = (): UseSpellCheckReturn => {
  const [errors, setErrors] = useState<SpellError[]>([]);
  const [loading, setLoading] = useState(false);
  const [checked, setChecked] = useState(false);

  const runCheck = useCallback(async (text: string) => {
    setLoading(true);
    setChecked(false);
    try {
      const result = await checkSpelling(text);
      setErrors(result);
      setChecked(true);
    } finally {
      setLoading(false);
    }
  }, []);

  const dismissError = useCallback((index: number) => {
    setErrors((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const reset = useCallback(() => {
    setErrors([]);
    setLoading(false);
    setChecked(false);
  }, []);

  return { errors, loading, checked, runCheck, dismissError, reset };
};
