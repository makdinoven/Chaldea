import { useState } from 'react';
import { motion } from 'motion/react';
import UsersTab from './UsersTab';
import RolesTab from './RolesTab';

type Tab = 'users' | 'roles';

const TABS: { key: Tab; label: string }[] = [
  { key: 'users', label: 'Пользователи' },
  { key: 'roles', label: 'Роли' },
];

const RbacAdminPage = () => {
  const [activeTab, setActiveTab] = useState<Tab>('users');

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="w-full max-w-[1240px] mx-auto"
    >
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em] mb-8">
        Пользователи и роли
      </h1>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-white/10">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2.5 text-sm font-medium uppercase tracking-wide transition-colors duration-200 border-b-2 -mb-px ${
              activeTab === tab.key
                ? 'text-white border-site-blue'
                : 'text-white/50 border-transparent hover:text-white/80'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'users' && <UsersTab />}
      {activeTab === 'roles' && <RolesTab />}
    </motion.div>
  );
};

export default RbacAdminPage;
