import React, { useState, useEffect, useCallback } from 'react';
import toast from 'react-hot-toast';
import {
  getAdminUserList,
  getRoles,
  assignUserRole,
  getUserPermissions,
  setUserPermissions,
  getAllPermissions,
} from '../../../api/rbacAdmin';
import type {
  AdminUserItem,
  RoleResponse,
  PermissionItem,
} from '../../../api/rbacAdmin';
import PermissionGrid from './PermissionGrid';

const PAGE_SIZE = 20;

const UsersTab = () => {
  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [roles, setRoles] = useState<RoleResponse[]>([]);
  const [allPermissions, setAllPermissions] = useState<Record<string, PermissionItem[]>>({});

  const [expandedUserId, setExpandedUserId] = useState<number | null>(null);
  const [editRoleId, setEditRoleId] = useState<number | null>(null);
  const [editDisplayName, setEditDisplayName] = useState('');
  const [savingRole, setSavingRole] = useState(false);

  const [userOverrideGrants, setUserOverrideGrants] = useState<Set<string>>(new Set());
  const [userOverrideRevokes, setUserOverrideRevokes] = useState<Set<string>>(new Set());
  const [userEffectivePerms, setUserEffectivePerms] = useState<Set<string>>(new Set());
  const [savingPerms, setSavingPerms] = useState(false);
  const [loadingPerms, setLoadingPerms] = useState(false);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getAdminUserList({
        page,
        page_size: PAGE_SIZE,
        search: search || undefined,
        role_id: roleFilter,
      });
      setUsers(data.items);
      setTotal(data.total);
    } catch {
      const msg = 'Не удалось загрузить список пользователей';
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [page, search, roleFilter]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  useEffect(() => {
    const loadMeta = async () => {
      try {
        const [rolesData, permsData] = await Promise.all([
          getRoles(),
          getAllPermissions(),
        ]);
        setRoles(rolesData);
        setAllPermissions(permsData);
      } catch {
        toast.error('Не удалось загрузить роли и разрешения');
      }
    };
    loadMeta();
  }, []);

  const handleExpandUser = async (user: AdminUserItem) => {
    if (expandedUserId === user.id) {
      setExpandedUserId(null);
      return;
    }

    setExpandedUserId(user.id);
    setEditRoleId(user.role_id);
    setEditDisplayName(user.role_display_name || '');
    setLoadingPerms(true);

    try {
      const effective = await getUserPermissions(user.id);
      setUserEffectivePerms(new Set(effective.effective_permissions));

      // Show effective permissions as the checked state; track overrides for save
      setUserOverrideGrants(new Set(effective.effective_permissions));
      setUserOverrideRevokes(new Set(effective.overrides?.revokes ?? []));
    } catch {
      toast.error('Не удалось загрузить разрешения пользователя');
    } finally {
      setLoadingPerms(false);
    }
  };

  const handleSaveRole = async () => {
    if (expandedUserId == null || editRoleId == null) return;
    setSavingRole(true);
    try {
      await assignUserRole(expandedUserId, {
        role_id: editRoleId,
        role_display_name: editDisplayName || null,
      });
      toast.success('Роль обновлена');
      await fetchUsers();
    } catch {
      toast.error('Не удалось обновить роль');
    } finally {
      setSavingRole(false);
    }
  };

  const handlePermissionChange = (key: string, value: boolean) => {
    setUserOverrideGrants((prev) => {
      const next = new Set(prev);
      if (value) {
        next.add(key);
      } else {
        next.delete(key);
      }
      return next;
    });
    setUserOverrideRevokes((prev) => {
      const next = new Set(prev);
      if (!value) {
        next.add(key);
      } else {
        next.delete(key);
      }
      return next;
    });
  };

  const handleSavePermissions = async () => {
    if (expandedUserId == null) return;
    setSavingPerms(true);
    try {
      await setUserPermissions(expandedUserId, {
        grants: Array.from(userOverrideGrants),
        revokes: Array.from(userOverrideRevokes).filter(
          (r) => !userOverrideGrants.has(r),
        ),
      });
      toast.success('Разрешения обновлены');
    } catch {
      toast.error('Не удалось обновить разрешения');
    } finally {
      setSavingPerms(false);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '—';
    const d = new Date(dateStr);
    return d.toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <input
          type="text"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          placeholder="Поиск по имени или email..."
          className="input-underline flex-1 text-sm"
        />
        <select
          value={roleFilter ?? ''}
          onChange={(e) => {
            setRoleFilter(e.target.value ? Number(e.target.value) : null);
            setPage(1);
          }}
          className="bg-transparent border-b border-white/30 text-white text-sm py-2 px-1 focus:border-site-blue outline-none transition-colors duration-200"
        >
          <option value="" className="bg-site-bg">Все роли</option>
          {roles.map((r) => (
            <option key={r.id} value={r.id} className="bg-site-bg">
              {r.name}
            </option>
          ))}
        </select>
      </div>

      {/* Error */}
      {error && (
        <p className="text-site-red text-sm">{error}</p>
      )}

      {/* Loading */}
      {loading && (
        <p className="text-white/60 text-sm">Загрузка...</p>
      )}

      {/* Table */}
      {!loading && users.length === 0 && !error && (
        <p className="text-white/60 text-sm">Пользователи не найдены</p>
      )}

      {!loading && users.length > 0 && (
        <div className="overflow-x-auto gold-scrollbar">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-white/60 font-medium uppercase text-xs tracking-wide py-3 px-2">
                  Пользователь
                </th>
                <th className="text-white/60 font-medium uppercase text-xs tracking-wide py-3 px-2 hidden sm:table-cell">
                  Email
                </th>
                <th className="text-white/60 font-medium uppercase text-xs tracking-wide py-3 px-2">
                  Роль
                </th>
                <th className="text-white/60 font-medium uppercase text-xs tracking-wide py-3 px-2 hidden md:table-cell">
                  Название роли
                </th>
                <th className="text-white/60 font-medium uppercase text-xs tracking-wide py-3 px-2 hidden lg:table-cell">
                  Последняя активность
                </th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <React.Fragment key={user.id}>
                  <tr
                    onClick={() => handleExpandUser(user)}
                    className="border-b border-white/5 hover:bg-white/5 cursor-pointer transition-colors duration-200"
                  >
                    <td className="py-3 px-2">
                      <div className="flex items-center gap-2">
                        {user.avatar ? (
                          <img
                            src={user.avatar}
                            alt={user.username}
                            className="w-8 h-8 rounded-full object-cover"
                          />
                        ) : (
                          <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center text-white/40 text-xs">
                            {user.username[0]?.toUpperCase()}
                          </div>
                        )}
                        <span className="text-white">{user.username}</span>
                      </div>
                    </td>
                    <td className="py-3 px-2 text-white/70 hidden sm:table-cell">
                      {user.email}
                    </td>
                    <td className="py-3 px-2 text-white/70">{user.role}</td>
                    <td className="py-3 px-2 text-white/70 hidden md:table-cell">
                      {user.role_display_name || '—'}
                    </td>
                    <td className="py-3 px-2 text-white/50 text-xs hidden lg:table-cell">
                      {formatDate(user.last_active_at)}
                    </td>
                  </tr>

                  {/* Expanded editor */}
                  {expandedUserId === user.id && (
                    <tr key={`${user.id}-editor`}>
                      <td colSpan={5} className="p-4 bg-white/[0.03]">
                        <div className="space-y-5">
                          {/* Role editor */}
                          <div>
                            <h4 className="text-white text-sm font-medium uppercase tracking-wide mb-3">
                              Роль
                            </h4>
                            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-end">
                              <div className="flex-1">
                                <label className="text-white/50 text-xs block mb-1">Роль</label>
                                <select
                                  value={editRoleId ?? ''}
                                  onChange={(e) => setEditRoleId(Number(e.target.value))}
                                  className="bg-transparent border-b border-white/30 text-white text-sm py-2 px-1 w-full focus:border-site-blue outline-none transition-colors duration-200"
                                >
                                  {roles.map((r) => (
                                    <option key={r.id} value={r.id} className="bg-site-bg">
                                      {r.name} (уровень {r.level})
                                    </option>
                                  ))}
                                </select>
                              </div>
                              <div className="flex-1">
                                <label className="text-white/50 text-xs block mb-1">
                                  Название роли (необязательно)
                                </label>
                                <input
                                  type="text"
                                  value={editDisplayName}
                                  onChange={(e) => setEditDisplayName(e.target.value)}
                                  placeholder="Например: Главный модератор"
                                  className="input-underline w-full text-sm"
                                />
                              </div>
                              <button
                                onClick={handleSaveRole}
                                disabled={savingRole}
                                className="btn-blue text-sm px-4 py-2 whitespace-nowrap"
                              >
                                {savingRole ? 'Сохранение...' : 'Сохранить роль'}
                              </button>
                            </div>
                          </div>

                          {/* Permission overrides */}
                          <div>
                            <h4 className="text-white text-sm font-medium uppercase tracking-wide mb-3">
                              Индивидуальные разрешения
                            </h4>
                            {loadingPerms ? (
                              <p className="text-white/50 text-sm">Загрузка разрешений...</p>
                            ) : (
                              <>
                                <PermissionGrid
                                  grouped={allPermissions}
                                  checked={userOverrideGrants}
                                  onChange={handlePermissionChange}
                                />
                                <button
                                  onClick={handleSavePermissions}
                                  disabled={savingPerms}
                                  className="btn-blue text-sm px-4 py-2 mt-4"
                                >
                                  {savingPerms ? 'Сохранение...' : 'Сохранить разрешения'}
                                </button>
                              </>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="text-white/60 hover:text-site-blue disabled:opacity-30 disabled:cursor-not-allowed text-sm transition-colors duration-200"
          >
            Назад
          </button>
          <span className="text-white/60 text-sm">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="text-white/60 hover:text-site-blue disabled:opacity-30 disabled:cursor-not-allowed text-sm transition-colors duration-200"
          >
            Вперёд
          </button>
        </div>
      )}
    </div>
  );
};

export default UsersTab;
