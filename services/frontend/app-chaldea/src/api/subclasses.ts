import axios from 'axios';
import { apiErrorMessage } from './errors';

/**
 * Public subclass registry (skills-service, unchanged by FEAT-154) — used by
 * the wizard's «Путь» step as a preview of where a class grows (rule 13).
 */
export interface Subclass {
  key: string;
  class_id: number;
  name: string;
  description: string;
}

/** All subclasses, optionally narrowed to a single class. */
export const fetchSubclasses = async (classId?: number): Promise<Subclass[]> => {
  try {
    const { data } = await axios.get<Subclass[]>('/skills/subclasses', {
      params: classId ? { class_id: classId } : undefined,
    });
    return data ?? [];
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось загрузить подклассы.'));
  }
};
