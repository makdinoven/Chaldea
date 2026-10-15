import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { fetchUserStats } from '../../../api/usersApi';
import type { UserStatsResponse } from '../../../types/users';

const Footer = () => {
  const [stats, setStats] = useState<UserStatsResponse | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchUserStats()
      .then((res) => {
        if (!cancelled) setStats(res.data);
      })
      .catch(() => {
        // Graceful degradation: footer silently hides on error, does not break the page
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <motion.footer
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex w-full flex-col items-center gap-2 px-4 py-6 text-center text-sm text-white/60"
    >
      {/* Player counts: hidden if the stats request fails, the rest of the footer stays */}
      {stats && (
        <p>
          <span>Наёмников:{' '}</span>
          <Link
            to="/players"
            className="gold-text text-sm font-medium site-link transition-colors duration-200 ease-site"
          >
            {stats.total_users}
          </Link>
          <span className="mx-2 text-white/30">|</span>
          <span>В мире сейчас:{' '}</span>
          <Link
            to="/players/online"
            className="gold-text text-sm font-medium site-link transition-colors duration-200 ease-site"
          >
            {stats.online_users}
          </Link>
        </p>
      )}
      {/* Required by the CC BY 3.0 licence of the Game Icons used for battle effects */}
      <p className="text-xs text-white/40">
        Иконки эффектов:{' '}
        <a
          href="https://game-icons.net"
          target="_blank"
          rel="noopener noreferrer"
          className="site-link transition-colors duration-200 ease-site"
        >
          game-icons.net
        </a>{' '}
        — Lorc, Delapouite и другие авторы, лицензия{' '}
        <a
          href="https://creativecommons.org/licenses/by/3.0/"
          target="_blank"
          rel="noopener noreferrer"
          className="site-link transition-colors duration-200 ease-site"
        >
          CC BY 3.0
        </a>
      </p>
    </motion.footer>
  );
};

export default Footer;
