import type { PermissionItem } from '../../../api/rbacAdmin';

const MODULE_LABELS: Record<string, string> = {
  users: 'Пользователи',
  items: 'Предметы',
  characters: 'Персонажи',
  skills: 'Навыки',
  locations: 'Локации',
  rules: 'Правила',
  photos: 'Фото',
  notifications: 'Уведомления',
};

interface PermissionGridProps {
  grouped: Record<string, PermissionItem[]>;
  checked: Set<string>;
  onChange: (permKey: string, value: boolean) => void;
  disabled?: boolean;
  disabledTooltip?: string;
}

const PermissionGrid = ({
  grouped,
  checked,
  onChange,
  disabled = false,
  disabledTooltip,
}: PermissionGridProps) => {
  const modules = Object.keys(grouped).sort((a, b) => {
    const order = Object.keys(MODULE_LABELS);
    return order.indexOf(a) - order.indexOf(b);
  });

  const isModuleFullyChecked = (mod: string) =>
    grouped[mod].every((p) => checked.has(`${p.module}:${p.action}`));

  const handleModuleToggle = (mod: string) => {
    if (disabled) return;
    const full = isModuleFullyChecked(mod);
    grouped[mod].forEach((p) => {
      const key = `${p.module}:${p.action}`;
      onChange(key, !full);
    });
  };

  return (
    <div className="space-y-4" title={disabled ? disabledTooltip : undefined}>
      {modules.map((mod) => {
        const perms = grouped[mod];
        const allChecked = isModuleFullyChecked(mod);
        const someChecked =
          !allChecked && perms.some((p) => checked.has(`${p.module}:${p.action}`));

        return (
          <div key={mod}>
            <label
              className={`flex items-center gap-2 mb-2 cursor-pointer select-none ${
                disabled ? 'opacity-60 cursor-not-allowed' : ''
              }`}
            >
              <input
                type="checkbox"
                checked={allChecked}
                ref={(el) => {
                  if (el) el.indeterminate = someChecked;
                }}
                onChange={() => handleModuleToggle(mod)}
                disabled={disabled}
                className="w-4 h-4 accent-site-blue"
              />
              <span className="text-white text-sm font-medium uppercase tracking-wide">
                {MODULE_LABELS[mod] || mod}
              </span>
            </label>

            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-x-4 gap-y-1 pl-6">
              {perms.map((p) => {
                const key = `${p.module}:${p.action}`;
                return (
                  <label
                    key={key}
                    className={`flex items-center gap-2 cursor-pointer select-none ${
                      disabled ? 'opacity-60 cursor-not-allowed' : ''
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked.has(key)}
                      onChange={(e) => onChange(key, e.target.checked)}
                      disabled={disabled}
                      className="w-3.5 h-3.5 accent-site-blue"
                    />
                    <span className="text-white/80 text-sm">{p.action}</span>
                  </label>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default PermissionGrid;
