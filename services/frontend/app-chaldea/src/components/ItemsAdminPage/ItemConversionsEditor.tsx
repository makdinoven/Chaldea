/**
 * FEAT-165 — refining config of a raw resource: per profession, how many
 * source items give how many of which result item. The parent form saves it
 * (PUT replaces the whole set) right after the item itself is saved.
 */
import { useEffect, useMemo, useState } from "react";
import { fetchAllItems } from "../../api/items";
import { fetchItemConversions } from "../../api/professions";
import type { ItemConversionInput, RefiningRule } from "../../types/professions";
import {
  CONVERSION_QTY_MAX,
  CONVERSION_QTY_MIN,
  REFINING_DEFAULT_RATIOS,
  RESOURCE_SUBCATEGORY_LABELS,
  type ResourceSubcategory,
} from "../../constants/professions";

export interface ConversionsDraft {
  /** Existing config loaded (or nothing to load for a new item) */
  ready: boolean;
  /** The admin changed something: the set must be saved */
  dirty: boolean;
  conversions: ItemConversionInput[];
  /** Russian message when an enabled row is incomplete */
  invalid: string | null;
}

interface RowState {
  enabled: boolean;
  source_quantity: string;
  result_quantity: string;
  result_item_id: string;
}

interface ResultOption {
  id: number;
  name: string;
}

interface ItemConversionsEditorProps {
  /** Source item id when editing; undefined for a new item */
  itemId?: number;
  subcategory: ResourceSubcategory;
  /** Refining rules from GET refining-rules (loaded by the form); null while loading */
  rules: RefiningRule[] | null;
  rulesError: string | null;
  onChange: (draft: ConversionsDraft) => void;
  /** Error of the last save attempt, shown inline */
  saveError: string | null;
}

const labelText = "text-white/50 text-xs font-medium uppercase tracking-[0.06em]";
const optionClass = "bg-site-dark text-white";

const errorText = (e: unknown, fallback: string) => (e instanceof Error && e.message ? e.message : fallback);

const emptyRow = (): RowState => ({ enabled: false, source_quantity: "1", result_quantity: "1", result_item_id: "" });

const qtyValid = (v: string) => {
  const n = Number(v);
  return Number.isInteger(n) && n >= CONVERSION_QTY_MIN && n <= CONVERSION_QTY_MAX;
};

const ItemConversionsEditor = ({
  itemId,
  subcategory,
  rules,
  rulesError,
  onChange,
  saveError,
}: ItemConversionsEditorProps) => {
  const [rows, setRows] = useState<Record<number, RowState>>({});
  const [loaded, setLoaded] = useState(!itemId);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [options, setOptions] = useState<Record<string, ResultOption[]>>({});
  const [optionsError, setOptionsError] = useState<string | null>(null);

  // Existing config of the edited item
  useEffect(() => {
    if (!itemId) return;
    setLoaded(false);
    setLoadError(null);
    fetchItemConversions(itemId)
      .then((res) => {
        const next: Record<number, RowState> = {};
        for (const c of res.conversions ?? []) {
          next[c.profession_id] = {
            enabled: true,
            source_quantity: String(c.source_quantity),
            result_quantity: String(c.result_quantity),
            result_item_id: String(c.result_item.id),
          };
        }
        setRows(next);
        setDirty(false);
        setLoaded(true);
      })
      .catch((e) => setLoadError(errorText(e, "Не удалось загрузить настройки переработки")));
  }, [itemId]);

  const matching = useMemo(
    () => (rules ?? []).filter((r) => r.source_subcategory === subcategory),
    [rules, subcategory],
  );

  // Result pickers: items of each needed result subcategory
  const neededSubcategories = useMemo(
    () => Array.from(new Set(matching.map((r) => r.result_subcategory))),
    [matching],
  );
  useEffect(() => {
    const missing = neededSubcategories.filter((s) => !options[s]);
    if (missing.length === 0) return;
    let cancelled = false;
    Promise.all(
      missing.map((s) =>
        fetchAllItems({ itemTypes: ["resource"], resourceSubcategory: s }).then((list: ResultOption[]) => [
          s,
          list
            .map(({ id, name }) => ({ id, name }))
            .sort((a, b) => a.name.localeCompare(b.name, "ru")),
        ] as const),
      ),
    )
      .then((pairs) => {
        if (cancelled) return;
        setOptions((prev) => ({ ...prev, ...Object.fromEntries(pairs) }));
      })
      .catch((e) => {
        if (!cancelled) setOptionsError(errorText(e, "Не удалось загрузить список предметов-результатов"));
      });
    return () => {
      cancelled = true;
    };
  }, [neededSubcategories, options]);

  // Report the draft to the parent form
  useEffect(() => {
    const conversions: ItemConversionInput[] = [];
    let invalid: string | null = null;
    for (const rule of matching) {
      const row = rows[rule.profession_id];
      if (!row?.enabled) continue;
      if (!row.result_item_id) {
        invalid = `Переработка (${rule.profession_name}): выберите предмет-результат`;
        continue;
      }
      if (!qtyValid(row.source_quantity) || !qtyValid(row.result_quantity)) {
        invalid = `Переработка (${rule.profession_name}): количество должно быть от ${CONVERSION_QTY_MIN} до ${CONVERSION_QTY_MAX}`;
        continue;
      }
      conversions.push({
        profession_id: rule.profession_id,
        source_quantity: Number(row.source_quantity),
        result_item_id: Number(row.result_item_id),
        result_quantity: Number(row.result_quantity),
      });
    }
    if (!invalid && loadError) invalid = "Настройки переработки не загружены — сохранение невозможно";
    onChange({ ready: loaded && rules !== null, dirty, conversions, invalid });
  }, [matching, rows, dirty, loaded, rules, loadError, onChange]);

  const updateRow = (rule: RefiningRule, patch: Partial<RowState>) => {
    setDirty(true);
    setRows((prev) => {
      const current = prev[rule.profession_id] ?? emptyRow();
      const next = { ...current, ...patch };
      // Pre-fill the default ratio the first time a profession is enabled
      if (patch.enabled && !prev[rule.profession_id]) {
        const ratio = REFINING_DEFAULT_RATIOS[rule.profession_slug];
        if (ratio) {
          next.source_quantity = String(ratio.source);
          next.result_quantity = String(ratio.result);
        }
      }
      return { ...prev, [rule.profession_id]: next };
    });
  };

  const renderBody = () => {
    if (rulesError) return <p className="text-site-red text-sm">{rulesError}</p>;
    if (!rules) return <p className="text-white/40 text-sm">Загрузка правил переработки…</p>;
    if (matching.length === 0) {
      return <p className="text-white/40 text-sm">Эта подкатегория пока не перерабатывается.</p>;
    }
    if (loadError) return <p className="text-site-red text-sm">{loadError}</p>;
    if (!loaded) return <p className="text-white/40 text-sm">Загрузка настроек…</p>;

    return (
      <div className="flex flex-col gap-4">
        {matching.map((rule) => {
          const row = rows[rule.profession_id] ?? emptyRow();
          const resultOptions = options[rule.result_subcategory];
          const resultLabel = RESOURCE_SUBCATEGORY_LABELS[rule.result_subcategory] ?? rule.result_subcategory;
          return (
            <div key={rule.profession_id} className="flex flex-col gap-3 border-t border-white/10 pt-3 first:border-t-0 first:pt-0">
              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={row.enabled}
                  onChange={(e) => updateRow(rule, { enabled: e.target.checked })}
                  className="w-5 h-5 accent-site-blue shrink-0"
                />
                <span className="text-sm text-white">
                  {rule.profession_name}: настроить переработку
                  <span className="text-white/40"> → {resultLabel.toLowerCase()}</span>
                </span>
              </label>

              {row.enabled && (
                <div className="grid grid-cols-1 sm:grid-cols-[repeat(2,minmax(0,8rem))_minmax(0,1fr)] gap-4 sm:pl-8">
                  <label className="flex flex-col gap-1 min-w-0">
                    <span className={labelText}>Сырья, шт.</span>
                    <input
                      type="number"
                      inputMode="numeric"
                      min={CONVERSION_QTY_MIN}
                      max={CONVERSION_QTY_MAX}
                      value={row.source_quantity}
                      onChange={(e) => updateRow(rule, { source_quantity: e.target.value })}
                      className="input-underline"
                    />
                  </label>
                  <label className="flex flex-col gap-1 min-w-0">
                    <span className={labelText}>Результата, шт.</span>
                    <input
                      type="number"
                      inputMode="numeric"
                      min={CONVERSION_QTY_MIN}
                      max={CONVERSION_QTY_MAX}
                      value={row.result_quantity}
                      onChange={(e) => updateRow(rule, { result_quantity: e.target.value })}
                      className="input-underline"
                    />
                  </label>
                  <label className="flex flex-col gap-1 min-w-0">
                    <span className={labelText}>Результат ({resultLabel})</span>
                    <select
                      value={row.result_item_id}
                      onChange={(e) => updateRow(rule, { result_item_id: e.target.value })}
                      disabled={!resultOptions}
                      className="input-underline"
                    >
                      <option value="" className={optionClass}>
                        {resultOptions ? "—" : "Загрузка…"}
                      </option>
                      {resultOptions
                        ?.filter((o) => o.id !== itemId)
                        .map((o) => (
                          <option key={o.id} value={o.id} className={optionClass}>
                            {o.name}
                          </option>
                        ))}
                    </select>
                    {resultOptions && resultOptions.length === 0 && (
                      <span className="text-white/40 text-xs">
                        Нет ресурсов с подкатегорией «{resultLabel}» — создайте их сначала.
                      </span>
                    )}
                  </label>
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <fieldset className="border border-white/10 rounded-card p-4 bg-white/[0.03] min-w-0">
      <legend className={`${labelText} px-2`}>Переработка</legend>
      <div className="mt-2 flex flex-col gap-3">
        {renderBody()}
        {optionsError && <p className="text-site-red text-sm">{optionsError}</p>}
        {saveError && <p className="text-site-red text-sm">{saveError}</p>}
        <p className="text-white/40 text-xs">
          Настройки сохраняются вместе с предметом. Качество результата задаётся выбранным предметом.
        </p>
      </div>
    </fieldset>
  );
};

export default ItemConversionsEditor;
