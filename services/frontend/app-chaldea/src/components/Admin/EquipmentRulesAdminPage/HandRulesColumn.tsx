import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'react-feather';
import { WEAPON_SUBCLASS_GROUPS } from '../../../constants/items';
import type { HandToken } from '../../../api/equipmentRules';

export const categoryToken = (category: string): HandToken => `category:${category}`;
export const kindToken = (kind: string): HandToken => `kind:${kind}`;

interface HandRulesColumnProps {
  title: string;
  tokens: Set<HandToken>;
  onChange: (next: Set<HandToken>) => void;
  /** Weapon categories not offered in this column (two-handed for the off-hand) */
  excludedCategories?: readonly string[];
  note?: string;
  disabled?: boolean;
}

const HandRulesColumn = ({ title, tokens, onChange, excludedCategories = [], note, disabled }: HandRulesColumnProps) => {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const groups = WEAPON_SUBCLASS_GROUPS.filter((g) => !excludedCategories.includes(g.key));

  const toggleExpanded = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const toggleCategory = (groupKey: string, kinds: string[]) => {
    const next = new Set(tokens);
    const token = categoryToken(groupKey);
    if (next.has(token)) {
      next.delete(token);
    } else {
      next.add(token);
      // The whole category is allowed now: per-kind ticks inside are redundant
      kinds.forEach((kind) => next.delete(kindToken(kind)));
    }
    onChange(next);
  };

  const toggleKind = (kind: string) => {
    const next = new Set(tokens);
    const token = kindToken(kind);
    if (next.has(token)) next.delete(token);
    else next.add(token);
    onChange(next);
  };

  return (
    <div className="flex flex-col gap-2 min-w-0">
      <h3 className="gold-text text-base font-medium uppercase tracking-[0.06em]">{title}</h3>
      {note && <p className="text-white/40 text-xs">{note}</p>}

      <ul className="flex flex-col gap-1">
        {groups.map((group) => {
          const kinds = Object.keys(group.options);
          const categoryOn = tokens.has(categoryToken(group.key));
          const kindCount = kinds.filter((k) => tokens.has(kindToken(k))).length;
          const isOpen = expanded.has(group.key);

          return (
            <li key={group.key} className="rounded-card bg-white/[0.03] border border-white/5">
              <div className="flex items-center gap-2 px-3 py-2">
                <button
                  type="button"
                  onClick={() => toggleExpanded(group.key)}
                  className="text-white/50 hover:text-site-blue transition-colors shrink-0"
                  aria-label={isOpen ? 'Свернуть виды' : 'Показать виды'}
                  aria-expanded={isOpen}
                >
                  {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </button>
                <label className="flex items-center gap-2 min-w-0 flex-1 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={categoryOn}
                    onChange={() => toggleCategory(group.key, kinds)}
                    disabled={disabled}
                    className="w-4 h-4 accent-site-blue shrink-0"
                  />
                  <span className="text-sm text-white truncate">{group.label}</span>
                </label>
                {!categoryOn && kindCount > 0 && (
                  <span className="text-xs text-white/40 shrink-0">
                    {kindCount}/{kinds.length}
                  </span>
                )}
              </div>

              {isOpen && (
                <div className="grid grid-cols-1 min-[420px]:grid-cols-2 gap-x-4 gap-y-1 px-3 pb-3 pl-9">
                  {kinds.map((kind) => (
                    <label key={kind} className="flex items-center gap-2 cursor-pointer min-w-0">
                      <input
                        type="checkbox"
                        checked={categoryOn || tokens.has(kindToken(kind))}
                        onChange={() => toggleKind(kind)}
                        disabled={disabled || categoryOn}
                        className="w-4 h-4 accent-site-blue shrink-0"
                      />
                      <span className={`text-sm truncate ${categoryOn ? 'text-white/50' : 'text-white/80'}`}>
                        {group.options[kind]}
                      </span>
                    </label>
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export default HandRulesColumn;
