interface Tab {
  key: string;
  label: string;
}

const TABS: Tab[] = [
  { key: 'character', label: 'Персонаж' },
  { key: 'skills', label: 'Навыки' },
  { key: 'logs', label: 'Логи персонажа' },
  { key: 'titles', label: 'Титулы' },
  { key: 'craft', label: 'Крафт' },
];

interface ProfileTabsProps {
  activeTab: string;
  onTabChange: (tabKey: string) => void;
}

const ProfileTabs = ({ activeTab, onTabChange }: ProfileTabsProps) => {
  return (
    <nav className="flex items-center gap-8 mb-8">
      {TABS.map((tab) => {
        const isActive = activeTab === tab.key;
        return (
          <button
            key={tab.key}
            onClick={() => onTabChange(tab.key)}
            className={`relative pb-2 text-sm font-medium uppercase tracking-[0.06em] transition-all duration-200 ease-site gold-text ${
              isActive
                ? ''
                : 'opacity-70 hover:opacity-100'
            }`}
          >
            {tab.label}
            {isActive && (
              <span className="absolute bottom-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-[#999] to-transparent" />
            )}
          </button>
        );
      })}
    </nav>
  );
};

export default ProfileTabs;
