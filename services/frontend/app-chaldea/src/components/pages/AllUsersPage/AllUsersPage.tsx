import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { fetchAllUsers } from '../../../api/usersApi';
import type { UserPublicItem } from '../../../types/users';

const DEFAULT_AVATAR = 'assets/avatars/avatar.png';
const PAGE_SIZE = 50;

const formatDate = (dateStr: string | null): string => {
  if (!dateStr) return '—';
  const date = new Date(dateStr);
  return date.toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
};

const AllUsersPage = () => {
  const [users, setUsers] = useState<UserPublicItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchAllUsers(page, PAGE_SIZE)
      .then((res) => {
        if (!cancelled) {
          setUsers(res.data.items);
          setTotal(res.data.total);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError('Не удалось загрузить список пользователей. Попробуйте позже.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [page]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="mt-10"
    >
      <h1 className="gold-text text-2xl font-medium uppercase mb-8">
        Все наёмники
      </h1>

      {error && (
        <p className="text-site-red text-base mb-6">{error}</p>
      )}

      {loading && !error && (
        <p className="text-white/60 text-base">Загрузка...</p>
      )}

      {!loading && !error && users.length === 0 && (
        <p className="text-white/60 text-base">Пока нет ни одного наёмника.</p>
      )}

      {!loading && !error && users.length > 0 && (
        <>
          <motion.div
            initial="hidden"
            animate="visible"
            variants={{
              hidden: {},
              visible: { transition: { staggerChildren: 0.05 } },
            }}
            className="flex flex-col gap-3"
          >
            {users.map((user) => (
              <motion.div
                key={user.id}
                variants={{
                  hidden: { opacity: 0, y: 10 },
                  visible: { opacity: 1, y: 0 },
                }}
                className="flex items-center gap-4 py-3 px-4 rounded-card bg-white/[0.04] hover:bg-white/[0.07] transition-colors duration-200 ease-site"
              >
                <img
                  src={user.avatar || DEFAULT_AVATAR}
                  alt={user.username}
                  className="w-10 h-10 rounded-full object-cover flex-shrink-0"
                />
                <Link
                  to={`/user-profile/${user.id}`}
                  className="site-link text-base font-medium"
                >
                  {user.username}
                </Link>
                <span className="ml-auto text-white/40 text-xs">
                  {formatDate(user.registered_at)}
                </span>
              </motion.div>
            ))}
          </motion.div>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-4 mt-8">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="btn-line text-sm disabled:opacity-30 disabled:cursor-not-allowed"
              >
                Назад
              </button>
              <span className="text-white/60 text-sm">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="btn-line text-sm disabled:opacity-30 disabled:cursor-not-allowed"
              >
                Вперёд
              </button>
            </div>
          )}
        </>
      )}
    </motion.div>
  );
};

export default AllUsersPage;
