import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import TextAlign from "@tiptap/extension-text-align";
import TextStyle from "@tiptap/extension-text-style";
import Color from "@tiptap/extension-color";
import Highlight from "@tiptap/extension-highlight";
import Link from "@tiptap/extension-link";
import { ResizableImage } from "./ResizableImageExtension";
import { useState, useRef, useEffect, useCallback } from "react";
import {
  Bold,
  Italic,
  Underline as UnderlineIcon,
  Type,
  AlignLeft,
  AlignCenter,
  AlignRight,
  List,
  Image as ImageIcon,
  Link as LinkIcon,
} from "react-feather";
import ColorPicker from "../../common/ColorPicker";

/* ── Types ── */

interface WysiwygEditorProps {
  content: string;
  onChange: (html: string) => void;
}

interface ToolbarBtnProps {
  label?: string;
  icon?: React.ReactNode;
  isActive: boolean;
  onClick: () => void;
  title?: string;
}

/* ── Toolbar button ── */

const ToolbarBtn = ({ label, icon, isActive, onClick, title }: ToolbarBtnProps) => (
  <button
    type="button"
    onClick={onClick}
    title={title}
    className={`px-2.5 py-1 text-sm rounded transition-colors duration-200 flex items-center justify-center ${
      isActive
        ? "bg-site-blue/30 text-white"
        : "text-white/60 hover:text-white hover:bg-white/[0.07]"
    }`}
  >
    {icon || label}
  </button>
);

/* ── Separator ── */

const Separator = () => <span className="w-px h-6 bg-white/10 self-center mx-1" />;

/* ── Hook: close on click outside ── */

const useClickOutside = (ref: React.RefObject<HTMLElement | null>, onClose: () => void) => {
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [ref, onClose]);
};

/* ── Color Picker Popover ── */

interface ColorPopoverProps {
  color: string;
  onChange: (color: string) => void;
  onReset: () => void;
  onClose: () => void;
  resetLabel: string;
}

const ColorPopover = ({ color, onChange, onReset, onClose, resetLabel }: ColorPopoverProps) => {
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, onClose);

  return (
    <div
      ref={ref}
      className="absolute top-full left-0 mt-1 z-50 bg-site-bg border border-white/10 rounded-card p-3 shadow-dropdown min-w-[220px]"
    >
      <ColorPicker color={color} onChange={onChange} />
      <button
        type="button"
        onClick={onReset}
        className="mt-2 w-full text-xs text-white/60 hover:text-white transition-colors duration-200 py-1"
      >
        {resetLabel}
      </button>
    </div>
  );
};

/* ── URL Input Popover ── */

interface UrlPopoverProps {
  onSubmit: (url: string) => void;
  onClose: () => void;
  placeholder: string;
  submitLabel: string;
  initialValue?: string;
}

const UrlPopover = ({ onSubmit, onClose, placeholder, submitLabel, initialValue = "" }: UrlPopoverProps) => {
  const [url, setUrl] = useState(initialValue);
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, onClose);

  const handleSubmit = () => {
    if (url.trim()) {
      onSubmit(url.trim());
    }
    onClose();
  };

  return (
    <div
      ref={ref}
      className="absolute top-full left-0 mt-1 z-50 bg-site-bg border border-white/10 rounded-card p-3 shadow-dropdown min-w-[280px]"
    >
      <input
        type="text"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
        placeholder={placeholder}
        className="input-underline w-full text-sm mb-2"
        autoFocus
      />
      <button
        type="button"
        onClick={handleSubmit}
        className="btn-blue text-xs px-3 py-1 w-full"
      >
        {submitLabel}
      </button>
    </div>
  );
};

/* ── Component ── */

const WysiwygEditor = ({ content, onChange }: WysiwygEditorProps) => {
  const [showTextColor, setShowTextColor] = useState(false);
  const [showHighlight, setShowHighlight] = useState(false);
  const [showImageUrl, setShowImageUrl] = useState(false);
  const [showLinkUrl, setShowLinkUrl] = useState(false);

  const textColorRef = useRef<HTMLDivElement>(null);
  const highlightRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLDivElement>(null);
  const linkRef = useRef<HTMLDivElement>(null);

  const editor = useEditor({
    extensions: [
      StarterKit,
      Underline,
      ResizableImage,
      TextAlign.configure({
        types: ["heading", "paragraph"],
      }),
      TextStyle,
      Color,
      Highlight.configure({
        multicolor: true,
      }),
      Link.configure({
        openOnClick: false,
        HTMLAttributes: {
          class: "editor-link",
        },
      }),
    ],
    content,
    onUpdate: ({ editor: ed }) => {
      onChange(ed.getHTML());
    },
  });

  const togglePopover = useCallback(
    (setter: React.Dispatch<React.SetStateAction<boolean>>) => {
      const setters = [setShowTextColor, setShowHighlight, setShowImageUrl, setShowLinkUrl];
      setters.forEach((s) => {
        if (s === setter) {
          s((prev) => !prev);
        } else {
          s(false);
        }
      });
    },
    []
  );

  if (!editor) return null;

  const currentTextColor = editor.getAttributes("textStyle").color || "#ffffff";
  const currentHighlight = editor.getAttributes("highlight").color || "#f0d95c";

  return (
    <div className="border border-white/10 rounded-card overflow-hidden">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-1 p-2 border-b border-white/10 bg-white/[0.03]">
        {/* Text format: B, I, U, S */}
        <ToolbarBtn
          icon={<Bold size={15} />}
          isActive={editor.isActive("bold")}
          onClick={() => editor.chain().focus().toggleBold().run()}
          title="Жирный"
        />
        <ToolbarBtn
          icon={<Italic size={15} />}
          isActive={editor.isActive("italic")}
          onClick={() => editor.chain().focus().toggleItalic().run()}
          title="Курсив"
        />
        <ToolbarBtn
          icon={<UnderlineIcon size={15} />}
          isActive={editor.isActive("underline")}
          onClick={() => editor.chain().focus().toggleUnderline().run()}
          title="Подчёркнутый"
        />
        <ToolbarBtn
          label="S"
          isActive={editor.isActive("strike")}
          onClick={() => editor.chain().focus().toggleStrike().run()}
          title="Зачёркнутый"
        />

        <Separator />

        {/* Text color */}
        <div className="relative" ref={textColorRef}>
          <button
            type="button"
            onClick={() => togglePopover(setShowTextColor)}
            title="Цвет текста"
            className={`px-2.5 py-1 text-sm rounded transition-colors duration-200 flex flex-col items-center justify-center gap-0.5 ${
              showTextColor
                ? "bg-site-blue/30 text-white"
                : "text-white/60 hover:text-white hover:bg-white/[0.07]"
            }`}
          >
            <Type size={15} />
            <span
              className="w-4 h-1 rounded-full"
              style={{ backgroundColor: currentTextColor }}
            />
          </button>
          {showTextColor && (
            <ColorPopover
              color={currentTextColor}
              onChange={(color) => editor.chain().focus().setColor(color).run()}
              onReset={() => editor.chain().focus().unsetColor().run()}
              onClose={() => setShowTextColor(false)}
              resetLabel="Сбросить цвет"
            />
          )}
        </div>

        {/* Highlight */}
        <div className="relative" ref={highlightRef}>
          <button
            type="button"
            onClick={() => togglePopover(setShowHighlight)}
            title="Выделение фона"
            className={`px-2.5 py-1 text-sm rounded transition-colors duration-200 flex flex-col items-center justify-center gap-0.5 ${
              showHighlight
                ? "bg-site-blue/30 text-white"
                : "text-white/60 hover:text-white hover:bg-white/[0.07]"
            }`}
          >
            <span className="text-xs font-bold leading-none">A</span>
            <span
              className="w-4 h-1 rounded-full"
              style={{ backgroundColor: currentHighlight }}
            />
          </button>
          {showHighlight && (
            <ColorPopover
              color={currentHighlight}
              onChange={(color) =>
                editor.chain().focus().toggleHighlight({ color }).run()
              }
              onReset={() => editor.chain().focus().unsetHighlight().run()}
              onClose={() => setShowHighlight(false)}
              resetLabel="Убрать выделение"
            />
          )}
        </div>

        <Separator />

        {/* Headings */}
        <ToolbarBtn
          label="H1"
          isActive={editor.isActive("heading", { level: 1 })}
          onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
          title="Заголовок 1"
        />
        <ToolbarBtn
          label="H2"
          isActive={editor.isActive("heading", { level: 2 })}
          onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
          title="Заголовок 2"
        />
        <ToolbarBtn
          label="H3"
          isActive={editor.isActive("heading", { level: 3 })}
          onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
          title="Заголовок 3"
        />

        <Separator />

        {/* Alignment */}
        <ToolbarBtn
          icon={<AlignLeft size={15} />}
          isActive={
            editor.isActive({ textAlign: "left" }) ||
            editor.isActive("resizableImage", { textAlign: "left" })
          }
          onClick={() => {
            if (editor.isActive("resizableImage")) {
              editor.chain().focus().setImageAlign("left").run();
            } else {
              editor.chain().focus().setTextAlign("left").run();
            }
          }}
          title="По левому краю"
        />
        <ToolbarBtn
          icon={<AlignCenter size={15} />}
          isActive={
            editor.isActive({ textAlign: "center" }) ||
            editor.isActive("resizableImage", { textAlign: "center" })
          }
          onClick={() => {
            if (editor.isActive("resizableImage")) {
              editor.chain().focus().setImageAlign("center").run();
            } else {
              editor.chain().focus().setTextAlign("center").run();
            }
          }}
          title="По центру"
        />
        <ToolbarBtn
          icon={<AlignRight size={15} />}
          isActive={
            editor.isActive({ textAlign: "right" }) ||
            editor.isActive("resizableImage", { textAlign: "right" })
          }
          onClick={() => {
            if (editor.isActive("resizableImage")) {
              editor.chain().focus().setImageAlign("right").run();
            } else {
              editor.chain().focus().setTextAlign("right").run();
            }
          }}
          title="По правому краю"
        />

        <Separator />

        {/* Lists */}
        <ToolbarBtn
          icon={<List size={15} />}
          isActive={editor.isActive("bulletList")}
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          title="Маркированный список"
        />
        <ToolbarBtn
          label="1."
          isActive={editor.isActive("orderedList")}
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
          title="Нумерованный список"
        />

        {/* Blockquote */}
        <ToolbarBtn
          label="&#10077;"
          isActive={editor.isActive("blockquote")}
          onClick={() => editor.chain().focus().toggleBlockquote().run()}
          title="Цитата"
        />

        <Separator />

        {/* Link */}
        <div className="relative" ref={linkRef}>
          <ToolbarBtn
            icon={<LinkIcon size={15} />}
            isActive={editor.isActive("link")}
            onClick={() => {
              if (editor.isActive("link")) {
                editor.chain().focus().unsetLink().run();
              } else {
                togglePopover(setShowLinkUrl);
              }
            }}
            title="Ссылка"
          />
          {showLinkUrl && (
            <UrlPopover
              placeholder="https://example.com"
              submitLabel="Вставить ссылку"
              initialValue={editor.getAttributes("link").href || ""}
              onSubmit={(url) =>
                editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run()
              }
              onClose={() => setShowLinkUrl(false)}
            />
          )}
        </div>

        {/* Image */}
        <div className="relative" ref={imageRef}>
          <ToolbarBtn
            icon={<ImageIcon size={15} />}
            isActive={false}
            onClick={() => togglePopover(setShowImageUrl)}
            title="Изображение"
          />
          {showImageUrl && (
            <UrlPopover
              placeholder="URL изображения"
              submitLabel="Вставить изображение"
              onSubmit={(url) => editor.chain().focus().setResizableImage({ src: url }).run()}
              onClose={() => setShowImageUrl(false)}
            />
          )}
        </div>
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
