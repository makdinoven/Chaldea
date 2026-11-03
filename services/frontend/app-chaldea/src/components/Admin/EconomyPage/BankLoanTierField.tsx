import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { putEconomyBankFlag } from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import type { EconBankAdminItem } from '../../../types/economy';
import ReputationTierSelect from '../ReputationPage/ReputationTierSelect';

interface BankLoanTierFieldProps {
  bank: EconBankAdminItem;
  canEdit: boolean;
  onSaved: (item: EconBankAdminItem) => void;
}

/**
 * FEAT-197 «Мин. репутация для займа» of one bank. Saved through the «Банк есть» PUT with the current flag and
 * `seed_capital: false`, so only the tier changes.
 */
const BankLoanTierField = ({ bank, canEdit, onSaved }: BankLoanTierFieldProps) => {
  const stored = bank.loan_min_reputation_tier ?? null;
  const [value, setValue] = useState<string | null>(stored);
  const [saving, setSaving] = useState(false);

  useEffect(() => setValue(stored), [stored]);

  const save = async () => {
    setSaving(true);
    try {
      const item = await putEconomyBankFlag(bank.region_id, {
        is_enabled: bank.enabled,
        seed_capital: false,
        loan_min_reputation_tier: value,
      });
      toast.success('Порог репутации для займов сохранён');
      onSaved(item);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить порог репутации для займов'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col sm:flex-row sm:items-end gap-3">
      <div className="sm:w-64">
        <ReputationTierSelect
          id={`bank-loan-tier-${bank.region_id}`}
          label="Мин. репутация для займа"
          value={value}
          disabled={!canEdit || saving}
          onChange={setValue}
        />
      </div>
      {canEdit && value !== stored && (
        <button type="button" className="btn-blue w-full sm:w-auto !text-sm !px-5 !py-1.5 disabled:opacity-50"
          disabled={saving} onClick={() => void save()}>
          {saving ? 'Сохранение...' : 'Сохранить'}
        </button>
      )}
    </div>
  );
};

export default BankLoanTierField;
