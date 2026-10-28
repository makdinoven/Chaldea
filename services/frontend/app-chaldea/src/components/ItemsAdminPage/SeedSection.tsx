import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { ChevronDown, Sprout, X } from "lucide-react";
import { GARDEN_ROOMS, ROOM_TYPE_LABEL } from "../../api/houses";
import { searchItemsCatalog } from "../../api/adminCharacters";
import { fetchItem } from "../../api/items";
import { apiErrorMessage } from "../../api/errors";
import type { ItemData } from "../Admin/CharactersPage/types";
import {
  SEED_DEFAULT_GROW_HOURS,
  SEED_MAX_GROW_HOURS,
  SEED_MAX_QUANTITY,
  SEED_MAX_XP,
} from "./itemFormRules";

/*
  FEAT-180 stage 6a — the «Семена» block of a resource: what grows from it,
  how many, in how many hours, in which house room (garden, greenhouse,
  apiary) and the herbalism XP of a harvest. All five fields are set together
  or all cleared.
*/

const LOOKUP_DEBOUNCE_MS = 300;
const LOOKUP_PAGE_SIZE = 20;

const labelText = "text-white/50 text-xs font-medium uppercase tracking-[0.06em]";
const optionClass = "bg-site-dark text-white";

interface SeedSectionProps {
  /** The form state (raw input values). */
  item: Record<string, unknown>;
  /** Id of the edited item — it can't grow into itself. */
  ownId?: number;
  setField: (name: string, value: unknown) => void;
}

interface PickedItem {
  id: number;
  name: string;
  image: string | null;
}

const SeedSection = ({ item, ownId, setField }: SeedSectionProps) => {
  const enabled = Boolean(item.seed_room_type);
  const [open, setOpen] = useState(enabled);
  const [picked, setPicked] = useState<PickedItem | null>(null);
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<ItemData[]>([]);
  const resultId = item.seed_result_item_id ? Number(item.seed_result_item_id) : null;

  // A loaded seed opens the block and shows its result's name.
  useEffect(() => {
    if (enabled) setOpen(true);
  }, [enabled]);

  useEffect(() => {
    if (resultId == null || picked?.id === resultId) return;
    fetchItem(resultId)
      .then((d: { id: number; name: string; image?: string | null }) =>
        setPicked({ id: d.id, name: d.name, image: d.image ?? null }))
      .catch((e: unknown) => {
        setPicked({ id: resultId, name: `Предмет #${resultId}`, image: null });
        toast.error(e instanceof Error && e.message ? e.message : "Не удалось загрузить предмет урожая");
      });
  }, [resultId, picked?.id]);

  useEffect(() => {
    if (query.trim().length < 1) {
      setOptions([]);
      return undefined;
    }
    const t = setTimeout(() => {
      searchItemsCatalog(query.trim(), 1, LOOKUP_PAGE_SIZE)
        .then((list) => setOptions(list.filter((o) => o.id !== ownId)))
        .catch((e) => toast.error(apiErrorMessage(e, "Не удалось найти предметы")));
    }, LOOKUP_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [query, ownId]);

  const toggle = (on: boolean) => {
    if (on) {
      setField("seed_room_type", "garden");
      if (!item.seed_result_quantity) setField("seed_result_quantity", 1);
      if (!item.seed_grow_hours) setField("seed_grow_hours", SEED_DEFAULT_GROW_HOURS);
      if (item.seed_herbalism_xp == null || item.seed_herbalism_xp === "") setField("seed_herbalism_xp", 0);
    } else {
      setField("seed_room_type", null);
      setField("seed_result_item_id", null);
      setField("seed_result_quantity", null);
      setField("seed_grow_hours", null);
      setField("seed_herbalism_xp", null);
      setPicked(null);
    }
  };

  const pick = (o: ItemData) => {
    setField("seed_result_item_id", o.id);
    setPicked({ id: o.id, name: o.name, image: o.image });
    setQuery("");
    setOptions([]);
  };

  const numberField = (name: string, label: string, min: number, max: number) => (
    <label className="flex flex-col gap-1 min-w-0">
      <span className={labelText}>{label}</span>
      <input type="number" min={min} max={max} step={1} value={(item[name] as number | string | null) ?? ""}
        onChange={(e) => setField(name, e.target.value)} className="input-underline" />
    </label>
  );

  return (
    <fieldset className="border border-white/10 rounded-card p-4 bg-white/[0.03] min-w-0">
      <legend className="px-2">
        <button type="button" onClick={() => setOpen((v) => !v)}
          className={`${labelText} flex items-center gap-1.5 hover:text-site-blue transition-colors`}>
          <Sprout size={13} />Семена{enabled ? " · да" : ""}
          <ChevronDown size={13} className={`transition-transform ${open ? "rotate-180" : ""}`} />
        </button>
      </legend>
      {open && (
        <div className="flex flex-col gap-4 mt-2">
          <label className="flex items-start gap-3 cursor-pointer">
            <input type="checkbox" checked={enabled} onChange={(e) => toggle(e.target.checked)} className="mt-1 accent-gold" />
            <span className="flex flex-col">
              <span className="text-white text-sm">Это семена</span>
              <span className="text-white/45 text-xs">
                Их сажают в огороде, оранжерее или на пасеке дома; через заданное время вырастает урожай.
              </span>
            </span>
          </label>

          {enabled && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
              <div className="flex flex-col gap-1 min-w-0 sm:col-span-2 lg:col-span-3">
                <span className={labelText}>Что вырастет</span>
                {picked && resultId != null ? (
                  <div className="flex items-center gap-2.5 bg-black/30 border border-white/[0.07] rounded-card p-2 min-w-0">
                    <span className="w-9 h-9 rounded-[8px] overflow-hidden bg-black/40 border border-white/10 shrink-0 block">
                      {picked.image && <img src={picked.image} alt="" className="w-full h-full object-cover" />}
                    </span>
                    <span className="text-white text-sm flex-1 min-w-0 truncate">
                      {picked.name} <span className="text-white/35 text-xs">#{picked.id}</span>
                    </span>
                    <button type="button" title="Выбрать другой" onClick={() => { setField("seed_result_item_id", null); setPicked(null); }}
                      className="w-8 h-8 flex items-center justify-center text-white/40 hover:text-site-red transition-colors shrink-0">
                      <X size={15} />
                    </button>
                  </div>
                ) : (
                  <>
                    <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Название предмета"
                      className="input-underline" />
                    {options.length > 0 && (
                      <div className="bg-black/80 border border-white/10 rounded-card divide-y divide-white/5 max-h-56 overflow-y-auto gold-scrollbar">
                        {options.map((o) => (
                          <button key={o.id} type="button" onClick={() => pick(o)}
                            className="w-full text-left px-3 py-2 text-sm text-white hover:bg-white/[0.06] transition-colors flex items-center gap-2">
                            <span className="w-7 h-7 rounded-[6px] overflow-hidden bg-black/40 shrink-0 block">
                              {o.image && <img src={o.image} alt="" className="w-full h-full object-cover" />}
                            </span>
                            <span className="truncate">{o.name}</span>
                            <span className="text-white/40 text-xs shrink-0">#{o.id}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
              <label className="flex flex-col gap-1 min-w-0">
                <span className={labelText}>Где растёт</span>
                <select value={String(item.seed_room_type ?? "garden")}
                  onChange={(e) => setField("seed_room_type", e.target.value)} className="input-underline">
                  {GARDEN_ROOMS.map((t) => (
                    <option key={t} value={t} className={optionClass}>{ROOM_TYPE_LABEL[t]}</option>
                  ))}
                </select>
              </label>
              {numberField("seed_result_quantity", "Урожай, шт.", 1, SEED_MAX_QUANTITY)}
              {numberField("seed_grow_hours", "Растёт, часов", 1, SEED_MAX_GROW_HOURS)}
              {numberField("seed_herbalism_xp", "Опыт травничества", 0, SEED_MAX_XP)}
            </div>
          )}
        </div>
      )}
    </fieldset>
  );
};

export default SeedSection;
