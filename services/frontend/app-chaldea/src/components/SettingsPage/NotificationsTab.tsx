import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchNotificationPreferences,
  updateNotificationPreferences,
  selectNotificationPreferences,
  type ConfigurableCategory,
  type NotificationMode,
  type NotificationPreferences,
} from '../../redux/slices/notificationSlice';
import { setClientPrefs, useClientPrefs } from '../../utils/clientPrefs';
import { playSound } from '../../utils/notifySound';
import SoundSlots from './SoundSlots';
import { SettingsCard, ChoiceGroup, Toggle, type Option } from './SettingsControls';

const MODE_OPTIONS: Option<NotificationMode>[] = [
  { value: 'all', label: 'Со всплывашкой и звуком' },
  { value: 'bell', label: 'Только в колокольчик' },
  { value: 'off', label: 'Не присылать' },
];

const CATEGORIES: { key: ConfigurableCategory; label: string; hint: string }[] = [
  {
    key: 'messages',
    label: 'Личные сообщения и упоминания',
    hint: 'Сами сообщения приходят всегда — здесь только звук, системное уведомление и упоминания в беседах.',
  },
  { key: 'social', label: 'Друзья и стена', hint: 'Заявки в друзья, новые друзья, записи на вашей стене.' },
  { key: 'trade', label: 'Аукцион и обмен', hint: 'Ставку перебили, лот продан или выкуплен, предложения обмена.' },
  { key: 'party', label: 'Отряды и боевые группы', hint: 'Приглашения, исключение и роспуск группы.' },
  { key: 'world', label: 'Локации', hint: 'Вас зовут на локацию, новые посты в избранных локациях.' },
  { key: 'progress', label: 'Персонажи и титулы', hint: 'Решения по заявкам на персонажа, новые титулы.' },
];


type PermissionState = NotificationPermission | 'unsupported';

const readPermission = (): PermissionState =>
  typeof Notification === 'undefined' ? 'unsupported' : Notification.permission;

/**
 * «Уведомления»: what the account is sent (kept on the server, so it holds on
 * every device) and how this browser announces it — sound and system popups.
 */
const NotificationsTab = () => {
  const dispatch = useAppDispatch();
  const saved = useAppSelector(selectNotificationPreferences);
  const prefs = useClientPrefs();

  const [draft, setDraft] = useState<NotificationPreferences>(saved);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [permission, setPermission] = useState<PermissionState>(readPermission);

  const load = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const fresh = await dispatch(fetchNotificationPreferences()).unwrap();
      setDraft(fresh);
    } catch (err) {
      setLoadError(typeof err === 'string' ? err : 'Не удалось загрузить настройки уведомлений');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const dirty = CATEGORIES.some(({ key }) => draft[key] !== saved[key]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const fresh = await dispatch(updateNotificationPreferences(draft)).unwrap();
      setDraft(fresh);
      toast.success('Настройки уведомлений сохранены');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось сохранить настройки уведомлений');
    } finally {
      setSaving(false);
    }
  };

  const handleBrowserNotifications = async (enabled: boolean) => {
    if (!enabled) {
      setClientPrefs({ browserNotifications: false });
      return;
    }
    if (permission === 'unsupported') return;
    let result: PermissionState = permission;
    if (result === 'default') {
      try {
        result = await Notification.requestPermission();
      } catch {
        result = readPermission();
      }
      setPermission(result);
    }
    if (result === 'granted') {
      setClientPrefs({ browserNotifications: true });
      toast.success('Системные уведомления включены');
    } else {
      toast.error('Браузер запретил уведомления для сайта — разрешите их в настройках сайта в браузере');
    }
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 sm:gap-6 items-start">
      <SettingsCard
        title="Что присылать"
        description="Хранится в аккаунте и действует на всех устройствах."
      >
        {loadError ? (
          <div className="flex flex-col items-start gap-3">
            <p className="text-site-red text-sm">{loadError}</p>
            <button type="button" onClick={load} className="btn-line text-sm">
              Повторить
            </button>
          </div>
        ) : loading ? (
          <div className="flex justify-center py-8">
            <div className="w-8 h-8 border-2 border-white/20 border-t-white rounded-full animate-spin" />
          </div>
        ) : (
          <>
            {CATEGORIES.map((category) => (
              <ChoiceGroup
                key={category.key}
                label={category.label}
                hint={category.hint}
                options={MODE_OPTIONS}
                value={draft[category.key]}
                onChange={(mode) => setDraft((prev) => ({ ...prev, [category.key]: mode }))}
              />
            ))}

            <p className="text-white/40 text-xs">
              Всегда приходят: нападение на вас и начало боя, вызовы на дуэль, ответы поддержки и
              объявления администрации — чтобы ничего важного в игре не прошло мимо.
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

      <SettingsCard title="Звук и система" description="Только для этого браузера — сохраняется сразу.">
        <Toggle
          label="Звуки"
          hint="Короткий сигнал о сообщении, уведомлении и начале боя."
          checked={prefs.soundEnabled}
          onChange={(soundEnabled) => setClientPrefs({ soundEnabled })}
        />

        <div className={`flex flex-col gap-3 ${prefs.soundEnabled ? '' : 'opacity-40 pointer-events-none'}`}>
          <div className="flex items-center gap-3">
            <span className="text-white/60 text-xs w-20 shrink-0">Громкость</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={prefs.soundVolume}
              onChange={(e) => setClientPrefs({ soundVolume: Number(e.target.value) })}
              onPointerUp={() => playSound('notification', { force: true })}
              aria-label="Громкость"
              className="flex-1 h-1.5 appearance-none rounded-full bg-white/10 cursor-pointer
                [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
                [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-site-blue
                [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:rounded-full
                [&::-moz-range-thumb]:bg-site-blue [&::-moz-range-thumb]:border-0"
            />
            <span className="text-white/40 text-xs w-10 text-right tabular-nums">
              {Math.round(prefs.soundVolume * 100)}%
            </span>
          </div>
          <SoundSlots />
        </div>

        <Toggle
          label="Системные уведомления"
          hint={
            permission === 'unsupported'
              ? 'Этот браузер не поддерживает системные уведомления.'
              : permission === 'denied'
                ? 'Браузер запретил уведомления для сайта — разрешите их в настройках сайта в браузере.'
                : 'Всплывают в углу экрана, когда вкладка с игрой свёрнута или открыта другая.'
          }
          checked={prefs.browserNotifications && permission === 'granted'}
          disabled={permission === 'unsupported' || permission === 'denied'}
          onChange={handleBrowserNotifications}
        />
      </SettingsCard>
    </div>
  );
};

export default NotificationsTab;
