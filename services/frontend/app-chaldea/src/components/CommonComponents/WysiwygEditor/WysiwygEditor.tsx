import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";

/* ── Types ── */

interface WysiwygEditorProps {
  content: string;
  onChange: (html: string) => void;
}

/* ── Toolbar button ── */

interface ToolbarBtnProps {
  label: string;
  isActive: boolean;
  onClick: () => void;
}

const ToolbarBtn = ({ label, isActive, onClick }: ToolbarBtnProps) => (
  <button
    type="button"
    onClick={onClick}
    className={`px-2.5 py-1 text-sm rounded transition-colors duration-200 ${
      isActive
        ? "bg-site-blue/30 text-white"
        : "text-white/60 hover:text-white hover:bg-white/[0.07]"
    }`}
  >
    {label}
  </button>
);

/* ── Component ── */

const WysiwygEditor = ({ content, onChange }: WysiwygEditorProps) => {
  const editor = useEditor({
    extensions: [StarterKit, Underline],
    content,
    onUpdate: ({ editor: ed }) => {
      onChange(ed.getHTML());
    },
  });

  if (!editor) return null;

  return (
    <div className="border border-white/10 rounded-card overflow-hidden">
      {/* Toolbar */}
      <div className="flex flex-wrap gap-1 p-2 border-b border-white/10 bg-white/[0.03]">
        <ToolbarBtn
          label="B"
          isActive={editor.isActive("bold")}
          onClick={() => editor.chain().focus().toggleBold().run()}
        />
        <ToolbarBtn
          label="I"
          isActive={editor.isActive("italic")}
          onClick={() => editor.chain().focus().toggleItalic().run()}
        />
        <ToolbarBtn
          label="U"
          isActive={editor.isActive("underline")}
          onClick={() => editor.chain().focus().toggleUnderline().run()}
        />

        <span className="w-px h-6 bg-white/10 self-center mx-1" />

        <ToolbarBtn
          label="H1"
          isActive={editor.isActive("heading", { level: 1 })}
          onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
        />
        <ToolbarBtn
          label="H2"
          isActive={editor.isActive("heading", { level: 2 })}
          onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
        />
        <ToolbarBtn
          label="H3"
          isActive={editor.isActive("heading", { level: 3 })}
          onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
        />

        <span className="w-px h-6 bg-white/10 self-center mx-1" />

        <ToolbarBtn
          label="&#8226; Список"
          isActive={editor.isActive("bulletList")}
          onClick={() => editor.chain().focus().toggleBulletList().run()}
        />
        <ToolbarBtn
          label="1. Список"
          isActive={editor.isActive("orderedList")}
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
        />
      </div>

      {/* Editor area */}
      <EditorContent
        editor={editor}
        className="prose-rules p-4 min-h-[200px] text-white text-base [&_.ProseMirror]:outline-none [&_.ProseMirror]:min-h-[180px]"
      />
    </div>
  );
};

export default WysiwygEditor;
