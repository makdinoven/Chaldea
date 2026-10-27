import { useState } from 'react';
import toast from 'react-hot-toast';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import { updateRole, type MiniRole, type RoleInput } from '../../../api/episodes';
import { apiErrorMessage } from '../../../api/errors';
import ImageField from './ImageField';
import { FIELD, LABEL } from './EpisodeFormModal';

interface RoleFormModalProps {
  episodeId: number;
  role: MiniRole;
  onClose: () => void;
  onSaved: (role: MiniRole) => void;
}

/** A mini-role's look: the name, avatar and a few words, shown on its posts. */
const RoleFormModal = ({ episodeId, role, onClose, onSaved }: RoleFormModalProps) => {
  const [form, setForm] = useState<RoleInput>({
    name: role.name,
    avatar_url: role.avatar_url,
    description: role.description,
  });
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!form.name.trim()) {
      toast.error('У роли должно быть имя');
      return;
    }
    setSaving(true);
    try {
      onSaved(await updateRole(episodeId, role.id, form));
      toast.success('Роль сохранена');
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить роль'));
      setSaving(false);
    }
  };

  return (
    <ModalShell
      open
      onClose={onClose}
      title="Мини-роль"
      size="sm"
      dismissible={!saving}
      closeOnBackdrop={false}
      footer={
        <>
          <button type="button" onClick={onClose} disabled={saving} className="btn-line w-full sm:w-auto !px-5">Отмена</button>
          <button type="button" onClick={() => void save()} disabled={saving} className="btn-blue w-full sm:w-auto !px-6 disabled:opacity-50">
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <ImageField label="Аватар" round value={form.avatar_url} onChange={(url) => setForm({ ...form, avatar_url: url })} />
        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Имя</span>
          <input value={form.name} maxLength={100} onChange={(e) => setForm({ ...form, name: e.target.value })} className={FIELD} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>О персонаже</span>
          <textarea value={form.description} maxLength={5000} onChange={(e) => setForm({ ...form, description: e.target.value })}
            className={`${FIELD} resize-y min-h-[100px]`} placeholder="Кто это, как выглядит — по желанию" />
        </label>
      </div>
    </ModalShell>
  );
};

export default RoleFormModal;
