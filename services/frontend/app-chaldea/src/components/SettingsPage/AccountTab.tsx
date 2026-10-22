import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import toast from 'react-hot-toast';
import { Monitor, LogOut } from 'react-feather';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { getMe } from '../../redux/slices/userSlice';
import { BASE_URL_DEFAULT } from '../../api/api';
import { setTokens } from '../../api/authToken';
import {
  accountError,
  changeEmail,
  changePassword,
  fetchSessions,
  revokeOtherSessions,
  revokeSession,
  type AccountSession,
} from '../../api/account';
import { describeUserAgent } from '../../utils/describeUserAgent';
import { formatServerDate } from '../../utils/serverDate';
import { SettingsCard } from './SettingsControls';

const MIN_PASSWORD_LENGTH = 6;
const MAX_PASSWORD_LENGTH = 128;

interface AccountCharacter {
  id: number;
  name: string;
  avatar: string | null;
  level: number | null;
  race_name?: string | null;
  class_name?: string | null;
}

const dateTime = (value: string | null) =>
  value
    ? formatServerDate(value, { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })
    : '—';

/** A labelled text field in the site's underline style. */
const Field = ({
  label,
  type = 'text',
  value,
  onChange,
  autoComplete,
}: {
  label: string;
  type?: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete?: string;
}) => (
  <label className="flex flex-col gap-1">
    <span className="text-white/60 text-xs">{label}</span>
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      autoComplete={autoComplete}
      className="input-underline w-full"
    />
  </label>
);

const EmailForm = () => {
  const dispatch = useAppDispatch();
  const currentEmail = useAppSelector((state) => state.user.email);
  const [open, setOpen] = useState(false);
  const [newEmail, setNewEmail] = useState('');
  const [password, setPassword] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!newEmail.trim() || !password) {
      toast.error('Введите новую почту и текущий пароль');
      return;
    }
    setSaving(true);
    try {
      // The tokens name the account by its email, so the server hands back fresh ones.
      const { data } = await changeEmail(newEmail.trim(), password);
      setTokens(data.access_token, data.refresh_token);
      await dispatch(getMe());
      toast.success('Почта изменена');
      setOpen(false);
      setNewEmail('');
      setPassword('');
    } catch (err) {
      toast.error(accountError(err, 'Не удалось изменить почту'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-white/60 text-xs">Почта</p>
          <p className="text-white text-sm truncate">{currentEmail ?? '—'}</p>
        </div>
        {!open && (
          <button type="button" onClick={() => setOpen(true)} className="site-link text-sm shrink-0">
            Изменить
          </button>
        )}
      </div>
      {open && (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <Field label="Новая почта" type="email" value={newEmail} onChange={setNewEmail} autoComplete="email" />
          <Field
            label="Текущий пароль"
            type="password"
            value={password}
            onChange={setPassword}
            autoComplete="current-password"
          />
          <p className="text-white/40 text-xs">Письмо-подтверждение пока не отправляется — проверьте адрес.</p>
          <div className="flex flex-col sm:flex-row gap-2 sm:justify-end">
            <button type="button" onClick={() => setOpen(false)} className="btn-line sm:!w-auto sm:px-6 !text-sm">
              Отмена
            </button>
            <button type="submit" disabled={saving} className="btn-blue w-full sm:w-auto disabled:opacity-40">
              {saving ? 'Сохранение...' : 'Сменить почту'}
            </button>
          </div>
        </form>
      )}
    </div>
  );
};

const PasswordForm = ({ onChanged }: { onChanged: () => void }) => {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!current || !next) {
      toast.error('Заполните текущий и новый пароль');
      return;
    }
    if (next.length < MIN_PASSWORD_LENGTH || next.length > MAX_PASSWORD_LENGTH) {
      toast.error(`Пароль должен быть от ${MIN_PASSWORD_LENGTH} до ${MAX_PASSWORD_LENGTH} символов`);
      return;
    }
    if (next !== repeat) {
      toast.error('Новые пароли не совпадают');
      return;
    }
    setSaving(true);
    try {
      await changePassword(current, next);
      toast.success('Пароль изменён. Другие устройства вышли из аккаунта');
      setCurrent('');
      setNext('');
      setRepeat('');
      onChanged();
    } catch (err) {
      toast.error(accountError(err, 'Не удалось изменить пароль'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <p className="text-white/60 text-xs">Пароль</p>
      <Field label="Текущий пароль" type="password" value={current} onChange={setCurrent} autoComplete="current-password" />
      <Field label="Новый пароль" type="password" value={next} onChange={setNext} autoComplete="new-password" />
      <Field label="Повторите новый пароль" type="password" value={repeat} onChange={setRepeat} autoComplete="new-password" />
      <p className="text-white/40 text-xs">После смены пароля все остальные устройства выйдут из аккаунта.</p>
      <div className="flex justify-end">
        <button type="submit" disabled={saving} className="btn-blue w-full sm:w-auto disabled:opacity-40">
          {saving ? 'Сохранение...' : 'Сменить пароль'}
        </button>
      </div>
    </form>
  );
};

const SessionsCard = ({ reloadKey }: { reloadKey: number }) => {
  const [sessions, setSessions] = useState<AccountSession[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = async () => {
    setError(null);
    try {
      const { data } = await fetchSessions();
      setSessions(data.sessions);
    } catch (err) {
      setError(accountError(err, 'Не удалось загрузить список сессий'));
    }
  };

  useEffect(() => {
    load();
  }, [reloadKey]);

  const end = async (session: AccountSession) => {
    setBusy(session.id);
    try {
      await revokeSession(session.id);
      toast.success('Сессия завершена');
      await load();
    } catch (err) {
      toast.error(accountError(err, 'Не удалось завершить сессию'));
    } finally {
      setBusy(null);
    }
  };

  const endOthers = async () => {
    setBusy('others');
    try {
      await revokeOtherSessions();
      toast.success('Все остальные устройства вышли из аккаунта');
      await load();
    } catch (err) {
      toast.error(accountError(err, 'Не удалось завершить сессии'));
    } finally {
      setBusy(null);
    }
  };

  const others = sessions?.filter((s) => !s.current) ?? [];

  return (
    <SettingsCard title="Сессии" description="Где сейчас открыт ваш аккаунт. Незнакомое устройство — завершите его и смените пароль.">
      {error ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-site-red text-sm">{error}</p>
          <button type="button" onClick={load} className="btn-line !w-auto px-6 text-sm">
            Повторить
          </button>
        </div>
      ) : !sessions ? (
        <div className="flex justify-center py-8">
          <div className="w-8 h-8 border-2 border-white/20 border-t-white rounded-full animate-spin" />
        </div>
      ) : (
        <>
          <ul className="flex flex-col divide-y divide-white/5">
            {sessions.map((session) => (
              <li key={session.id} className="flex items-center gap-3 py-2.5">
                <Monitor size={18} className={session.current ? 'text-gold shrink-0' : 'text-white/40 shrink-0'} />
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm truncate">
                    {describeUserAgent(session.user_agent)}
                    {session.current && <span className="text-gold text-xs ml-2">это устройство</span>}
                  </p>
                  <p className="text-white/40 text-xs">
                    Активность: {dateTime(session.last_used_at ?? session.created_at)} · вход {dateTime(session.created_at)}
                  </p>
                </div>
                {!session.current && (
                  <button
                    type="button"
                    onClick={() => end(session)}
                    disabled={busy !== null}
                    className="text-site-red text-xs hover:text-white transition-colors duration-200 ease-site shrink-0 disabled:opacity-40"
                  >
                    {busy === session.id ? 'Завершаю…' : 'Завершить'}
                  </button>
                )}
              </li>
            ))}
          </ul>
          {others.length > 0 && (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={endOthers}
                disabled={busy !== null}
                className="flex items-center gap-2 text-site-red text-sm hover:text-white transition-colors duration-200 ease-site disabled:opacity-40"
              >
                <LogOut size={16} />
                {busy === 'others' ? 'Завершаю…' : 'Выйти на всех, кроме этого'}
              </button>
            </div>
          )}
        </>
      )}
    </SettingsCard>
  );
};

const CharactersCard = () => {
  const dispatch = useAppDispatch();
  const userId = useAppSelector((state) => state.user.id) as number | null;
  const currentId = useAppSelector((state) => state.user.character?.id ?? null);
  const [characters, setCharacters] = useState<AccountCharacter[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [switching, setSwitching] = useState<number | null>(null);

  const load = async () => {
    if (userId === null) return;
    setError(null);
    try {
      const { data } = await axios.get<{ characters?: AccountCharacter[] }>(
        `${BASE_URL_DEFAULT}/users/${userId}/characters`,
      );
      setCharacters(data.characters ?? []);
    } catch {
      setError('Не удалось загрузить персонажей');
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const makeCurrent = async (characterId: number) => {
    if (userId === null) return;
    setSwitching(characterId);
    try {
      await axios.put(`${BASE_URL_DEFAULT}/users/${userId}/update_character`, {
        current_character: characterId,
      });
      await dispatch(getMe()).unwrap();
      toast.success('Персонаж переключён');
    } catch (err) {
      toast.error(accountError(err, 'Не удалось переключить персонажа'));
    } finally {
      setSwitching(null);
    }
  };

  return (
    <SettingsCard title="Персонажи" description="Текущий персонаж — тот, за которого вы играете сейчас.">
      {error ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-site-red text-sm">{error}</p>
          <button type="button" onClick={load} className="btn-line !w-auto px-6 text-sm">
            Повторить
          </button>
        </div>
      ) : !characters ? (
        <div className="flex justify-center py-8">
          <div className="w-8 h-8 border-2 border-white/20 border-t-white rounded-full animate-spin" />
        </div>
      ) : characters.length === 0 ? (
        <div className="flex flex-col items-start gap-2">
          <p className="text-white/50 text-sm">У вас пока нет персонажей.</p>
          <Link to="/createCharacter" className="site-link text-sm">
            Создать персонажа
          </Link>
        </div>
      ) : (
        <ul className="flex flex-col divide-y divide-white/5">
          {characters.map((character) => {
            const isCurrent = character.id === currentId;
            return (
              <li key={character.id} className="flex items-center gap-3 py-2.5">
                <div
                  className={`w-11 h-11 rounded-full overflow-hidden shrink-0 bg-white/5 ${
                    isCurrent ? 'ring-2 ring-gold' : ''
                  }`}
                >
                  {character.avatar && (
                    <img src={character.avatar} alt="" className="w-full h-full object-cover" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm truncate">{character.name}</p>
                  <p className="text-white/40 text-xs truncate">
                    {[
                      character.level != null ? `Ур. ${character.level}` : null,
                      character.race_name,
                      character.class_name,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                </div>
                {isCurrent ? (
                  <span className="text-gold text-xs shrink-0">Текущий</span>
                ) : (
                  <button
                    type="button"
                    onClick={() => makeCurrent(character.id)}
                    disabled={switching !== null}
                    className="site-link text-xs shrink-0 disabled:opacity-40"
                  >
                    {switching === character.id ? 'Переключаю…' : 'Сделать текущим'}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </SettingsCard>
  );
};

/**
 * «Аккаунт»: sign-in details, where the account is open, and its characters.
 * There is no account deletion by design.
 */
const AccountTab = () => {
  // A password change ends the other sessions: the list reloads after it.
  const [sessionsKey, setSessionsKey] = useState(0);

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 sm:gap-6 items-start">
      <div className="flex flex-col gap-4 sm:gap-6 min-w-0">
        <SettingsCard title="Вход в аккаунт">
          <EmailForm />
          <div className="h-px bg-white/10" />
          <PasswordForm onChanged={() => setSessionsKey((k) => k + 1)} />
        </SettingsCard>
        <CharactersCard />
      </div>
      <SessionsCard reloadKey={sessionsKey} />
    </div>
  );
};

export default AccountTab;
