import { Node, mergeAttributes } from "@tiptap/core";
import { NodeViewWrapper, ReactNodeViewRenderer } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";
import { useState, useCallback, useRef, useEffect } from "react";

/* ── Types ── */

type Alignment = "left" | "center" | "right";

interface ResizableImageAttrs {
  src: string | null;
  alt: string | null;
  width: string | null;
  textAlign: Alignment;
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    resizableImage: {
      setResizableImage: (attrs: Partial<ResizableImageAttrs>) => ReturnType;
      setImageAlign: (align: Alignment) => ReturnType;
    };
  }
}

/* ── NodeView Component ── */

const ResizableImageView = ({ node, updateAttributes, selected }: NodeViewProps) => {
  const attrs = node.attrs as ResizableImageAttrs;
  const [isResizing, setIsResizing] = useState(false);
  const [currentWidth, setCurrentWidth] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);

  const MIN_WIDTH = 100;

  const getMaxWidth = useCallback(() => {
    const wrapper = containerRef.current?.closest(".ProseMirror");
    if (wrapper) return wrapper.clientWidth;
    return 800;
  }, []);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();

      const imgEl = containerRef.current?.querySelector("img");
      if (!imgEl) return;

      startXRef.current = e.clientX;
      startWidthRef.current = imgEl.getBoundingClientRect().width;
      setIsResizing(true);
      setCurrentWidth(startWidthRef.current);
    },
    []
  );

  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      const delta = e.clientX - startXRef.current;
      const maxWidth = getMaxWidth();
      const newWidth = Math.max(MIN_WIDTH, Math.min(startWidthRef.current + delta, maxWidth));
      setCurrentWidth(Math.round(newWidth));
    };

    const handleMouseUp = () => {
      if (currentWidth !== null) {
        updateAttributes({ width: `${currentWidth}px` });
      }
      setIsResizing(false);
      setCurrentWidth(null);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizing, currentWidth, updateAttributes, getMaxWidth]);

  const displayWidth = isResizing && currentWidth !== null ? `${currentWidth}px` : attrs.width || "auto";
  const showHandles = selected || isResizing;

  return (
    <NodeViewWrapper
      data-type="resizable-image"
      data-align={attrs.textAlign || "left"}
      className="resizable-image-wrapper"
      style={{ textAlign: attrs.textAlign || "left" }}
    >
      <div
        ref={containerRef}
        className="inline-block relative"
        style={{
          width: displayWidth,
          maxWidth: "100%",
          ...(attrs.textAlign === "center" ? { margin: "0 auto" } : {}),
          ...(attrs.textAlign === "right" ? { marginLeft: "auto" } : {}),
        }}
      >
        <img
          src={attrs.src || ""}
          alt={attrs.alt || ""}
          draggable={false}
          className="block w-full h-auto rounded-lg select-none"
        />

        {showHandles && (
          <>
            {/* Selection outline */}
            <div className="absolute inset-0 rounded-lg border-2 border-site-blue/60 pointer-events-none" />

            {/* Corner handles */}
            {(["bottom-right", "bottom-left"] as const).map((pos) => (
              <div
                key={pos}
                onMouseDown={handleMouseDown}
                className={`absolute w-3 h-3 bg-site-blue border-2 border-white rounded-sm cursor-nwse-resize z-10 ${
                  pos === "bottom-right" ? "-bottom-1.5 -right-1.5" : "-bottom-1.5 -left-1.5 cursor-nesw-resize"
                }`}
              />
            ))}
          </>
        )}

        {/* Width tooltip while resizing */}
        {isResizing && currentWidth !== null && (
          <div className="absolute -top-8 left-1/2 -translate-x-1/2 bg-site-bg border border-white/20 rounded px-2 py-0.5 text-xs text-white whitespace-nowrap z-20 pointer-events-none">
            {currentWidth}px
          </div>
        )}
      </div>
    </NodeViewWrapper>
  );
};

/* ── Extension ── */

export const ResizableImage = Node.create({
  name: "resizableImage",
  group: "block",
  atom: true,
  draggable: true,

  addAttributes() {
    return {
      src: { default: null },
      alt: { default: null },
      width: { default: null },
      textAlign: { default: "left" },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'figure[data-type="resizable-image"]',
        getAttrs(dom) {
          const el = dom as HTMLElement;
          const img = el.querySelector("img");
          return {
            src: img?.getAttribute("src") || null,
            alt: img?.getAttribute("alt") || null,
            width: img?.style.width || el.querySelector("div")?.style.width || null,
            textAlign: (el.getAttribute("data-align") as Alignment) || "left",
          };
        },
      },
      {
        tag: "img[src]",
        getAttrs(dom) {
          const el = dom as HTMLImageElement;
          return {
            src: el.getAttribute("src"),
            alt: el.getAttribute("alt"),
            width: el.style.width || el.getAttribute("width") ? `${el.getAttribute("width")}px` : null,
            textAlign: "left" as Alignment,
          };
        },
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    const { src, alt, width, textAlign, ...rest } = HTMLAttributes;
    return [
      "figure",
      mergeAttributes(rest, {
        "data-type": "resizable-image",
        "data-align": textAlign || "left",
        style: `text-align: ${textAlign || "left"}`,
      }),
      [
        "div",
        {
          style: [
            `display: inline-block`,
            width ? `width: ${width}` : null,
            `max-width: 100%`,
            textAlign === "center" ? "margin: 0 auto" : null,
            textAlign === "right" ? "margin-left: auto" : null,
          ]
            .filter(Boolean)
            .join("; "),
        },
        ["img", { src, alt: alt || "", style: "width: 100%; height: auto;" }],
      ],
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(ResizableImageView);
  },

  addCommands() {
    return {
      setResizableImage:
        (attrs) =>
        ({ commands }) => {
          return commands.insertContent({
            type: this.name,
            attrs,
          });
        },
      setImageAlign:
        (align: Alignment) =>
        ({ tr, state, dispatch }) => {
          const { selection } = state;
          const node = state.doc.nodeAt(selection.from);
          if (node?.type.name === this.name) {
            if (dispatch) {
              tr.setNodeMarkup(selection.from, undefined, {
                ...node.attrs,
                textAlign: align,
              });
              dispatch(tr);
            }
            return true;
          }
          // Check if selection is inside a NodeView (selection.$from)
          const $pos = selection.$from;
          for (let depth = $pos.depth; depth >= 0; depth--) {
            const parentNode = $pos.node(depth);
            if (parentNode.type.name === this.name) {
              if (dispatch) {
                const pos = $pos.before(depth);
                tr.setNodeMarkup(pos, undefined, {
                  ...parentNode.attrs,
                  textAlign: align,
                });
                dispatch(tr);
              }
              return true;
            }
          }
          return false;
        },
    };
  },
});

export default ResizableImage;
