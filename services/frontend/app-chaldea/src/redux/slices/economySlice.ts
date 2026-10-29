import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import toast from 'react-hot-toast';
import type { RootState } from '../store';
import { getCurrencyFormsApi } from '../../api/economy';
import {
  DEFAULT_CURRENCY_FORMS,
  setCurrencyForms,
  type CurrencyForms,
} from '../../utils/currency';

const CURRENCY_LOAD_ERROR = 'Не удалось загрузить название валюты';

interface EconomyState {
  currency: CurrencyForms;
  status: 'idle' | 'loading' | 'succeeded' | 'failed';
  error: string | null;
}

const initialState: EconomyState = {
  currency: DEFAULT_CURRENCY_FORMS,
  status: 'idle',
  error: null,
};

const FORM_KEYS: (keyof CurrencyForms)[] = ['name', 'genitive', 'one', 'few', 'many', 'short'];

/** Keeps a default for any form the server left empty or omitted. */
const withDefaults = (data: Partial<CurrencyForms> | null | undefined): CurrencyForms => {
  const result = { ...DEFAULT_CURRENCY_FORMS };
  FORM_KEYS.forEach((key) => {
    const value = data?.[key];
    if (typeof value === 'string' && value.trim()) result[key] = value.trim();
  });
  return result;
};

/**
 * Loads the currency forms. Dispatched once by the app shell; the admin
 * «Экономика» settings pass `{ force: true }` after saving to refresh the UI wording.
 */
export const fetchCurrencyForms = createAsyncThunk<
  CurrencyForms,
  { force?: boolean } | void,
  { rejectValue: string }
>(
  'economy/fetchCurrencyForms',
  async (_, { rejectWithValue }) => {
    try {
      const { data } = await getCurrencyFormsApi();
      const forms = withDefaults(data);
      // Module mirror for non-React code (e.g. teleportSlice messages).
      setCurrencyForms(forms);
      return forms;
    } catch {
      toast.error(CURRENCY_LOAD_ERROR);
      return rejectWithValue(CURRENCY_LOAD_ERROR);
    }
  },
  {
    // Fetched once per page load; a second dispatch is a no-op unless forced.
    condition: (arg, { getState }) => {
      const { status } = (getState() as RootState).economy;
      if (arg && arg.force) return status !== 'loading';
      return status === 'idle';
    },
  },
);

const economySlice = createSlice({
  name: 'economy',
  initialState,
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchCurrencyForms.pending, (state) => {
        state.status = 'loading';
        state.error = null;
      })
      .addCase(fetchCurrencyForms.fulfilled, (state, action) => {
        state.status = 'succeeded';
        state.currency = action.payload;
      })
      .addCase(fetchCurrencyForms.rejected, (state, action) => {
        // Defaults stay in place; the toast was shown by the thunk.
        state.status = 'failed';
        state.error = action.payload ?? CURRENCY_LOAD_ERROR;
      });
  },
});

export const selectCurrencyForms = (state: RootState): CurrencyForms => state.economy.currency;

export default economySlice.reducer;
