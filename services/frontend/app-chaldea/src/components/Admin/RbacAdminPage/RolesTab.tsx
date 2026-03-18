import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import {
  getRoles,
  getRolePermissions,
  setRolePermissions,
  getAllPermissions,
} from '../../../api/rbacAdmin';
import type { RoleResponse, PermissionItem } from '../../../api/rbacAdmin';
import PermissionGrid from './PermissionGrid';

const RolesTab = () => {
  const [roles, setRoles] = useState<RoleResponse[]>([]);
  const [allPermissions, setAllPermissions] = useState<Record<string, PermissionItem[]>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [expandedRoleId, setExpandedRoleId] = useState<number | null>(null);
  const [rolePerms, setRolePerms] = useState<Set<string>>(new Set());
  const [loadingPerms, setLoadingPerms] = useState(false);
  const [savingPerms, setSavingPerms] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [rolesData, permsData] = await Promise.all([
          getRoles(),
          getAllPermissions(),
        ]);
        // Sort by level ascending
        setRoles(rolesData.sort((a, b) => a.level - b.level));
        setAllPermissions(permsData);
      } catch {
        const msg = 'Не удалось загрузить роли';
        setError(msg);
        toast.error(msg);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const handleExpandRole = async (role: RoleResponse) => {
    if (expandedRoleId === role.id) {
      setExpandedRoleId(null);
      return;
    }

    setExpandedRoleId(role.id);
    setLoadingPerms(true);

    try {
      const data = await getRolePermissions(role.id);
      setRolePerms(new Set(data.permissions));
    } catch {
      toast.error('Не удалось загрузить разрешения роли');
    } finally {
      setLoadingPerms(false);
    }
  };

  const handlePermChange = (key: string, value: boolean) => {
    setRolePerms((prev) => {
      const next = new Set(prev);
      if (value) {
        next.add(key);
      } else {
        next.delete(key);
      }
      return next;
    });
  };

  const handleSave = async () => {
    if (expandedRoleId == null) return;
    setSavingPerms(true);
    try {
      await setRolePermissions(expandedRoleId, {
        permissions: Array.from(rolePerms),
      });
      toast.success('Разрешения роли обновлены');
    } catch {
      toast.error('Не удалось обновить разрешения роли');
    } finally {
      setSavingPerms(false);
    }
  };

  const isAdminRole = (role: RoleResponse) => role.name === 'admin';

  // Build a set of ALL permission keys for admin display
  const allPermKeys = new Set<string>();
  Object.values(allPermissions).forEach((perms) =>
    perms.forEach((p) => allPermKeys.add(`${p.module}:${p.action}`)),
  );

  if (loading) {
    return <p className="text-white/60 text-sm">Загрузка ролей...</p>;
  }

  if (error) {
    return <p className="text-site-red text-sm">{error}</p>;
  }

  return (
    <div className="space-y-3">
      {roles.map((role) => {
        const isAdmin = isAdminRole(role);
        const isExpanded = expandedRoleId === role.id;

        return (
          <div
            key={role.id}
            className="border border-white/10 rounded-card overflow-hidden"
          >
            {/* Role header */}
            <button
              onClick={() => handleExpandRole(role)}
              className="w-full flex items-center justify-between p-4 hover:bg-white/5 transition-colors duration-200 text-left"
            >
              <div className="flex items-center gap-3">
                <span className="text-white font-medium">{role.name}</span>
                <span className="text-white/40 text-xs">
                  уровень {role.level}
                </span>
              </div>
              <span className="text-white/40 text-sm">
                {isExpanded ? '▲' : '▼'}
              </span>
            </button>

            {/* Expanded permission grid */}
            {isExpanded && (
              <div className="p-4 pt-0 border-t border-white/5">
                {role.description && (
                  <p className="text-white/50 text-xs mb-3">{role.description}</p>
                )}

                {loadingPerms ? (
                  <p className="text-white/50 text-sm">Загрузка разрешений...</p>
                ) : (
                  <>
                    {isAdmin && (
                      <p className="text-gold text-xs mb-3 italic">
                        Администратор всегда имеет все права
                      </p>
                    )}

                    <PermissionGrid
                      grouped={allPermissions}
                      checked={isAdmin ? allPermKeys : rolePerms}
                      onChange={handlePermChange}
                      disabled={isAdmin}
                      disabledTooltip="Администратор всегда имеет все права"
                    />

                    {!isAdmin && (
                      <button
                        onClick={handleSave}
                        disabled={savingPerms}
                        className="btn-blue text-sm px-4 py-2 mt-4"
                      >
                        {savingPerms ? 'Сохранение...' : 'Сохранить'}
                      </button>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default RolesTab;
