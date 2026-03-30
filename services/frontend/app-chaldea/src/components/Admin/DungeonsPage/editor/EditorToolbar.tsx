interface EditorToolbarProps {
  isDirty: boolean;
  isSaving: boolean;
  onSave: () => void;
  onValidate: () => void;
  onAutoLayout: () => void;
  onFitView: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
}

const EditorToolbar = ({
  isDirty,
  isSaving,
  onSave,
  onValidate,
  onAutoLayout,
  onFitView,
  onZoomIn,
  onZoomOut,
}: EditorToolbarProps) => {
  return (
    <div className="flex flex-wrap items-center gap-2 px-3 py-2 gray-bg rounded-lg">
      {/* Save */}
      <button
        className="btn-blue !text-sm !px-4 !py-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
        disabled={!isDirty || isSaving}
        onClick={onSave}
      >
        {isSaving ? 'Сохранение...' : 'Сохранить'}
      </button>

      {/* Validate */}
      <button className="btn-line !text-sm !px-4 !py-1.5" onClick={onValidate}>
        Валидация
      </button>

      {/* Auto-layout */}
      <button className="btn-line !text-sm !px-4 !py-1.5" onClick={onAutoLayout}>
        Авто-раскладка
      </button>

      {/* Separator */}
      <div className="w-px h-6 bg-white/15 mx-1 hidden sm:block" />

      {/* Fit view */}
      <button
        className="btn-line !text-sm !px-3 !py-1.5"
        onClick={onFitView}
        title="По размеру"
      >
        По размеру
      </button>

      {/* Zoom controls */}
      <button
        className="btn-line !text-sm !px-2.5 !py-1.5 !min-w-[32px]"
        onClick={onZoomIn}
        title="Приблизить"
      >
        +
      </button>
      <button
        className="btn-line !text-sm !px-2.5 !py-1.5 !min-w-[32px]"
        onClick={onZoomOut}
        title="Отдалить"
      >
        −
      </button>

      {/* Unsaved changes indicator */}
      {isDirty && (
        <div className="flex items-center gap-1.5 ml-auto">
          <span className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse" />
          <span className="text-xs text-yellow-400/80">Есть несохранённые изменения</span>
        </div>
      )}
    </div>
  );
};

export default EditorToolbar;
