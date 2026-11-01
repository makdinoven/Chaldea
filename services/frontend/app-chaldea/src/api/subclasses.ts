import axios from 'axios';
import { apiErrorMessage } from './errors';

/**
 * A subclass's passive (FEAT-188): one per subclass, from the skills-service
 * registry. `implemented: false` — described, but has no effect in battle yet.
 */
export interface SubclassPassive {
  key: string;
  name: string;
  description: string;
  implemented: boolean;
}

/**
 * Public subclass registry (skills-service) — used by the wizard's «Путь» step
 * as a preview of where a class grows (rule 13), and (FEAT-188) for the
 * subclass passive in the profile and on the skill tree.
 */
export interface Subclass {
  key: string;
  class_id: number;
  name: string;
  description: string;
  /** FEAT-188; absent on an older backend. */
  passive?: SubclassPassive | null;
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
