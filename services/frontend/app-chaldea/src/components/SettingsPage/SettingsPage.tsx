import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Bell, Key, Lock, Monitor, User } from 'react-feather';
import type { Icon } from 'react-feather';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  loadUserProfile,
  selectUserProfile,
  selectProfileLoading,
  selectProfileError,
} from '../../redux/slices/userProfileSlice';
import ProfileAppearanceTab from './ProfileAppearanceTab';
import PrivacyTab from './PrivacyTab';
import NotificationsTab from './NotificationsTab';
import InterfaceTab from './InterfaceTab';
import AccountTab from './AccountTab';

type TabKey = 'profile' | 'privacy' | 'notifications' | 'interface' | 'account';

const TABS: { key: TabKey; label: string; icon: Icon }[] = [
  { key: 'profile', label: 'Профиль и внешний вид', icon: User },
  { key: 'privacy', label: 'Приватность и общение', icon: Lock },
  { key: 'notifications', label: 'Уведомления', icon: Bell },
  { key: 'interface', label: 'Игра и интерфейс', icon: Monitor },
  { key: 'account', label: 'Аккаунт', icon: Key },
];

const isTabKey = (value: string | null): value is TabKey => TABS.some((tab) => tab.key === value);

/**
 * The player's own settings, reached from the menu under the avatar. The
 * chosen section sits in `?tab=` so a link can open it directly.
 */
const SettingsPage = () => {
  const dispatch = useAppDispatch();
  const [searchParams, setSearchParams] = useSearchParams();
  const userId = useAppSelector((state) => state.user.id) as number | null;
  const profile = useAppSelector(selectUserProfile);
  const profileLoading = useAppSelector(selectProfileLoading);
  const profileError = useAppSelector(selectProfileError);

  const tabParam = searchParams.get('tab');
  const activeTab: TabKey = isTabKey(tabParam) ? tabParam : 'profile';

  useEffect(() => {
    if (userId !== null) dispatch(loadUserProfile(userId));
  }, [userId, dispatch]);

  const ownProfile = profile && profile.id === userId ? profile : null;

  const selectTab = (key: TabKey) => setSearchParams(key === 'profile' ? {} : { tab: key }, { replace: true });

  return (
    <div className="w-full max-w-[1200px] mx-auto flex flex-col gap-4 sm:gap-6">
      <h1 className="gold-text text-2xl sm:text-3xl font-medium uppercase">Настройки</h1>

      <div className="flex flex-col lg:flex-row gap-4 sm:gap-6 items-start">
        {/* Sections: side by side on phones, a column beside the content from lg */}
        <nav
          className="gray-bg p-2 w-full lg:w-60 shrink-0 grid grid-cols-2 lg:flex lg:flex-col gap-1 lg:sticky lg:top-4"
          aria-label="Разделы настроек"
        >
          {TABS.map(({ key, label, icon: TabIcon }) => {
            const active = key === activeTab;
            return (
              <button
                key={key}
                type="button"
                onClick={() => selectTab(key)}
                aria-current={active ? 'page' : undefined}
                className={`flex items-center gap-2.5 px-3 py-2.5 rounded-card text-xs sm:text-sm text-left transition-colors duration-200 ease-site ${
                  active
                    ? 'bg-white/[0.08] text-white'
                    : 'text-white/50 hover:text-white hover:bg-white/[0.04]'
                }`}
              >
                <TabIcon size={16} className={active ? 'text-gold' : ''} />
                {label}
              </button>
            );
          })}
        </nav>

        <div className="flex-1 min-w-0 w-full">
          {activeTab === 'privacy' ? (
            <PrivacyTab />
          ) : activeTab === 'notifications' ? (
            <NotificationsTab />
          ) : activeTab === 'interface' ? (
            <InterfaceTab />
          ) : activeTab === 'account' ? (
            <AccountTab />
          ) : ownProfile ? (
            <ProfileAppearanceTab key={ownProfile.id} profile={ownProfile} />
          ) : profileError && !profileLoading ? (
            <div className="gray-bg p-5 flex flex-col items-start gap-3">
              <p className="text-site-red text-sm">Не удалось загрузить профиль</p>
              <button
                type="button"
                onClick={() => userId !== null && dispatch(loadUserProfile(userId))}
                className="btn-line text-sm"
              >
                Повторить
              </button>
            </div>
          ) : (
            <div className="flex justify-center py-16">
              <div className="w-10 h-10 border-2 border-white/20 border-t-white rounded-full animate-spin" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SettingsPage;
