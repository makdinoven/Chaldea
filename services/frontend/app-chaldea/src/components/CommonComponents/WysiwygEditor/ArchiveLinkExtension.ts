import { Mark, mergeAttributes } from "@tiptap/core";

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    archiveLink: {
      setArchiveLink: (attrs: { slug: string; title: string }) => ReturnType;
      unsetArchiveLink: () => ReturnType;
    };
  }
}

const ArchiveLink = Mark.create({
  name: "archiveLink",
  priority: 1001,
  inclusive: false,

  addAttributes() {
    return {
      href: { default: null },
      "data-archive-slug": { default: null },
      class: { default: "archive-link" },
    };
  },

  parseHTML() {
    return [{ tag: "a[data-archive-slug]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "a",
      mergeAttributes(HTMLAttributes, { class: "archive-link" }),
      0,
    ];
  },

  addCommands() {
    return {
      setArchiveLink:
        ({ slug, title }) =>
        ({ commands, editor }) => {
          const { empty } = editor.state.selection;

          if (empty) {
            return commands.insertContent(
              `<a href="/archive/${slug}" data-archive-slug="${slug}" class="archive-link">${title}</a>`,
            );
          }

          return commands.setMark(this.name, {
            href: `/archive/${slug}`,
            "data-archive-slug": slug,
            class: "archive-link",
          });
        },

      unsetArchiveLink:
        () =>
        ({ commands }) => {
          return commands.unsetMark(this.name);
        },
    };
  },
});

export default ArchiveLink;
