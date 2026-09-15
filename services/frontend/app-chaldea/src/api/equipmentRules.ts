import axios from 'axios';
import { apiErrorMessage } from './errors';

/**
 * Admin API for class/subclass equipment rules (inventory-service).
 * A scope is a class (subclass_key null — characters without a subclass yet)
 * or one subclass. No row for a scope means everything is allowed.
 */

/** "category:<weapon category>" or "kind:<weapon kind>" */
export type HandToken = string;

export interface EquipmentRuleRow {
  scope_key: string;
  class_id: number;
  subclass_key: string | null;
  armor_classes: string[];
  main_hand: HandToken[];
  off_hand: HandToken[];
  updated_at: string | null;
}

export interface EquipmentRulePayload {
  class_id: number;
  subclass_key: string | null;
  armor_classes: string[];
  main_hand: HandToken[];
  off_hand: HandToken[];
}

export const fetchEquipmentRuleRows = async (): Promise<EquipmentRuleRow[]> => {
  try {
    const { data } = await axios.get<EquipmentRuleRow[]>('/inventory/admin/equipment-rules');
    return data ?? [];
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось загрузить ограничения экипировки.'));
  }
};

export const saveEquipmentRule = async (payload: EquipmentRulePayload): Promise<EquipmentRuleRow> => {
  try {
    const { data } = await axios.put<EquipmentRuleRow>('/inventory/admin/equipment-rules', payload);
    return data;
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось сохранить ограничения.'));
  }
};

export const deleteEquipmentRule = async (classId: number, subclassKey: string | null): Promise<void> => {
  try {
    await axios.delete('/inventory/admin/equipment-rules', {
      params: subclassKey ? { class_id: classId, subclass_key: subclassKey } : { class_id: classId },
    });
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось снять ограничения.'));
  }
};
