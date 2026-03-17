import { useState } from "react";
import { createRule, updateRule, uploadRuleImage } from "../../../api/rules";
import type { GameRule } from "../../../api/rules";
import WysiwygEditor from "../../CommonComponents/WysiwygEditor/WysiwygEditor";
import toast from "react-hot-toast";

/* ── Props ── */

interface RuleFormProps {
  rule?: GameRule;
  onSuccess: () => void;
  onCancel: () => void;
}

const RuleForm = ({ rule, onSuccess, onCancel }: RuleFormProps) => {
  const editMode = Boolean(rule);

  const [title, setTitle] = useState(rule?.title ?? "");
  const [sortOrder, setSortOrder] = useState(rule?.sort_order ?? 0);
  const [content, setContent] = useState(rule?.content ?? "");
  const [imgFile, setImgFile] = useState<File | undefined>();
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      toast.error("Название не может быть пустым");
      return;
    }

    setSaving(true);
    try {
      let savedRule: GameRule;

      if (editMode && rule) {
        savedRule = await updateRule(rule.id, {
          title,
          content,
          sort_order: sortOrder,
        });
      } else {
        savedRule = await createRule({
          title,
          content,
          sort_order: sortOrder,
        });
      }

      if (imgFile) {
        await uploadRuleImage(savedRule.id, imgFile);
      }

      toast.success(editMode ? "Правило сохранено" : "Правило создано");
      onSuccess();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка при сохранении";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="gray-bg p-6 flex flex-col gap-6" onSubmit={handleSubmit}>
      <h2 className="gold-text text-2xl font-medium uppercase tracking-[0.06em]">
        {editMode ? "Редактирование правила" : "Создание правила"}
      </h2>

      {/* Base fields */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
        {/* Title */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Название
          </span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            className="input-underline"
          />
        </label>

        {/* Sort order */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Порядок сортировки
          </span>
          <input
            type="number"
            value={sortOrder}
            onChange={(e) => setSortOrder(Number(e.target.value))}
            className="input-underline"
          />
        </label>
      </div>

      {/* Image upload */}
      <label className="flex flex-col gap-1">
        <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
          Изображение
        </span>
        {rule?.image_url && !imgFile && (
          <img
            src={rule.image_url}
            alt={rule.title}
            className="w-[200px] h-[120px] object-cover rounded-[10px] mb-2"
          />
        )}
        <input
          type="file"
          accept="image/*"
          onChange={(e) => setImgFile(e.target.files?.[0])}
          className="text-white text-sm file:mr-4 file:py-2 file:px-4 file:rounded-card file:border-0 file:text-sm file:font-medium file:bg-white/[0.07] file:text-white hover:file:bg-white/[0.12] file:cursor-pointer file:transition-colors"
        />
      </label>

      {/* WYSIWYG editor */}
      <div className="flex flex-col gap-1">
        <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
          Содержание
        </span>
        <WysiwygEditor content={content} onChange={setContent} />
      </div>

      {/* Buttons */}
      <div className="flex gap-4 pt-2">
        <button
          type="submit"
          disabled={saving}
          className="btn-blue !text-base !px-8 !py-2 disabled:opacity-50"
        >
          {saving
            ? "Сохранение..."
            : editMode
              ? "Сохранить"
              : "Создать"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="btn-line !w-auto !px-8"
        >
          Отмена
        </button>
      </div>
    </form>
  );
};

export default RuleForm;
