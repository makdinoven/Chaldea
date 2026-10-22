import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { fetchBlocks, unblockUser, selectBlocks } from '../../redux/slices/messengerSlice';
import {
  fetchPrivacySettings,
  updatePrivacySettings,
  type AudiencePrivacy,
  type PrivacySettings,
} from '../../api/userProfile';
import { formatServerDate } from '../../utils/serverDate';
import { SettingsCard, ChoiceGroup, Toggle, type Option } from './SettingsControls';

const AUDIENCE_OPTIONS: Option<AudiencePrivacy>[] = [
  { value: 'all', label: 'Все' },
  { value: 'friends', label: 'Только друзья' },
  { value: 'nobody', label: 'Никто' },
];

const FRIEND_REQUEST_OPTIONS: Option<'all' | 'nobody'>[] = [
  { value: 'all', label: 'Все' },
  { value: 'nobody', label: 'Никто' },
];

type AudienceKey = 'message_privacy' | 'wall_view_privacy' | 'wall_post_privacy' | 'friends_list_privacy';

const AUDIENCE_SETTINGS: { key: AudienceKey; label: string; hint?: string }[] = [
  { key: 'message_privacy', label: 'Кто может писать мне в личные сообщения' },
  { key: 'wall_view_privacy', label: 'Кто видит мою стену' },
  {
    key: 'wall_post_privacy',
    label: 'Кто может писать на моей стене',
    hint: 'Писать на стене может только тот, кто её видит.',
  },
  { key: 'friends_list_privacy', label: 'Кто видит список моих друзей' },
];

const loadErrorText = (err: unknown) =>
  axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string'
    ? err.response.data.detail
    : 'Не удалось загрузить настройки приватности';

/**
 * «Приватность и общение»: who may reach the player and what others see of
 * them, plus the blocklist. Duels, parties and the like are deliberately not
 * here — in a role-play world everyone can always be interacted with.
 */
const PrivacyTab = () => {
  const dispatch = useAppDispatch();
  const blocks = useAppSelector(selectBlocks);

  const [saved, setSaved] = useState<PrivacySettings | null>(null);
  const [draft, setDraft] = useState<PrivacySettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [unblockingId, setUnblockingId] = useState<number | null>(null);

  const load = async () => {
    setLoadError(null);
    try {
      const { data } = await fetchPrivacySettings();
      setSaved(data);
      setDraft(data);
    } catch (err) {
      setLoadError(loadErrorText(err));
    }
  };

  useEffect(() => {
    load();
    dispatch(fetchBlocks())
      .unwrap()
      .catch((err: unknown) =>
        toast.error(typeof err === 'string' ? err : 'Не удалось загрузить чёрный список'),
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dispatch]);

  const dirty =
    saved !== null &&
    draft !== null &&
    (Object.keys(saved) as (keyof PrivacySettings)[]).some((key) => saved[key] !== draft[key]);

  const update = <K extends keyof PrivacySettings>(key: K, value: PrivacySettings[K]) =>
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));

  const handleSave = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      const { data } = await updatePrivacySettings(draft);
      setSaved(data);
      setDraft(data);
      toast.success('Настройки приватности сохранены');
    } catch (err) {
      toast.error(
        axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string'
          ? err.response.data.detail
          : 'Не удалось сохранить настройки приватности',
      );
    } finally {
      setSaving(false);
    }
  };

  const handleUnblock = async (blockedUserId: number) => {
    setUnblockingId(blockedUserId);
    try {
      await dispatch(unblockUser(blockedUserId)).unwrap();
      toast.success('Пользователь разблокирован');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось разблокировать');
    } finally {
      setUnblockingId(null);
    }
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 sm:gap-6 items-start">
      <SettingsCard title="Приватность">
        {loadError ? (
          <div className="flex flex-col items-start gap-3">
            <p className="text-site-red text-sm">{loadError}</p>
            <button type="button" onClick={load} className="btn-line text-sm">
              Повторить
            </button>
          </div>
        ) : !draft ? (
          <div className="flex justify-center py-8">
            <div className="w-8 h-8 border-2 border-white/20 border-t-white rounded-full animate-spin" />
          </div>
        ) : (
          <>
            {AUDIENCE_SETTINGS.map((setting) => (
              <ChoiceGroup
                key={setting.key}
                label={setting.label}
                hint={setting.hint}
                options={AUDIENCE_OPTIONS}
                value={draft[setting.key]}
                onChange={(value) => update(setting.key, value)}
              />
            ))}

            <ChoiceGroup
              label="Кто может отправлять мне заявки в друзья"
              options={FRIEND_REQUEST_OPTIONS}
              value={draft.friend_request_privacy}
              onChange={(value) => update('friend_request_privacy', value)}
            />

            <Toggle
              label="Показывать, что я в сети"
              hint="Если выключить, другие не увидят ни отметку «в сети», ни время последнего визита."
              checked={draft.show_online}
              onChange={(value) => update('show_online', value)}
            />

            <p className="text-white/40 text-xs">
              Вызвать на дуэль, позвать в отряд или обратиться к вашему персонажу в ролевой может
              любой игрок — это часть мира и не настраивается.
            </p>

            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleSave}
                disabled={saving || !dirty}
                className="btn-blue w-full sm:w-auto disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {saving ? 'Сохранение...' : 'Сохранить'}
              </button>
            </div>
          </>
        )}
      </SettingsCard>

      <SettingsCard title="Чёрный список">
        <p className="text-white/50 text-xs -mt-2">
          Заблокированные не могут писать вам в личные сообщения, на стену и отправлять заявки в
          друзья. Заблокировать игрока можно на странице его профиля.
        </p>
        {blocks.length === 0 ? (
          <p className="text-white/30 text-sm py-4 text-center">Список пуст</p>
        ) : (
          <ul className="flex flex-col divide-y divide-white/5">
            {blocks.map((block) => (
              <li key={block.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <Link
                    to={`/user-profile/${block.blocked_user_id}`}
                    className="site-link text-sm truncate block"
                  >
                    {block.blocked_username || `Пользователь #${block.blocked_user_id}`}
                  </Link>
                  {block.created_at && (
                    <span className="text-white/30 text-xs">
                      с {formatServerDate(block.created_at, { day: 'numeric', month: 'long', year: 'numeric' })}
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => handleUnblock(block.blocked_user_id)}
                  disabled={unblockingId === block.blocked_user_id}
                  className="text-site-red text-xs hover:text-white transition-colors duration-200 ease-site shrink-0 disabled:opacity-40"
                >
                  {unblockingId === block.blocked_user_id ? 'Снимаю…' : 'Разблокировать'}
                </button>
              </li>
            ))}
          </ul>
        )}
      </SettingsCard>
    </div>
  );
};

export default PrivacyTab;
