import axios from 'axios';
import type { CurrencyForms } from '../utils/currency';

/** Public currency word forms (FEAT-181, character-service). */
export const getCurrencyFormsApi = () =>
  axios.get<CurrencyForms>('/characters/economy/currency');
