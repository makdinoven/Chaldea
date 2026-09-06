# Chaldea Design System

Design reference for all frontend development. **Every new component MUST use these patterns.**

Source files:
- `tailwind.config.js` — design tokens (colors, shadows, radii, animations)
- `src/index.css` — `@layer components` with reusable classes
- `src/global.scss` — SCSS mixins (for legacy components only)

---

## 1. Design Philosophy

The Chaldea UI is a **dark fantasy RPG interface**:

- **Airy, not heavy** — backgrounds are often transparent or absent. Elements float over the dark background image.
- **Gold is the accent** — titles, borders, icons, active states use gold gradients.
- **Blue for interaction** — hover states, links, focus use `#76a6bd`.
- **Minimal chrome** — no heavy borders or box backgrounds unless needed. Let the background show through.
- **Elegant transitions** — 0.2s ease-in-out for everything. Subtle, not flashy.

---

## 2. Color Palette

### Tailwind tokens (use these in classes)

| Token | Value | Usage |
|-------|-------|-------|
| `text-white` | `#fff` | Primary text, icons |
| `text-gold-light` | `#fff9b8` | Gold gradient start |
| `text-gold` | `#f0d95c` | Solid gold accent |
| `text-gold-dark` | `#bcab4c` | Gold gradient end |
| `text-site-blue` | `#76a6bd` | Hover text, secondary links |
| `text-site-red` | `#F37753` | Errors, damage, alerts |
| `text-input` | `#c6c4c4` | Form input text |
| `bg-site-bg` | `rgba(9,10,16,0.62)` | Container backgrounds (затемнённые панели из мокапа, полупрозрачные) |
| `bg-site-dark` | `#1a1a2e` | Deep dark backgrounds |

Opaque floating surfaces (modals, dropdowns, context menus, tooltips) use `rgba(14,15,21,0.98)` — near-solid, NOT translucent (already baked into `modal-content`, `dropdown-menu`, `context-menu`, `site-tooltip`).

### CSS variables (for legacy SCSS)

```css
--zoloto: #fff;          /* primary text */
--zolotoReal: #f0d95c;   /* gold accent */
--blue: #76a6bd;          /* hover/interaction */
--red: #F37753;           /* error/action */
--gray-background: rgba(9, 10, 16, 0.62);
```

### Global page background

`body` uses base color `#05060a` with a **soft** dark gradient overlay on top of the background image:
`linear-gradient(180deg, rgba(5,6,10,0.35), rgba(5,6,10,0.55)), url(background-main.png)` — deliberately gentler than the mock's overlay (non-aggressive darkening). Defined in `src/index.css` (`body`), do not re-darken pages locally.

### Rules

- **Never use random colors** — always pick from the palette above.
- **Never use `text-gray-300`** for hover — use `hover:text-site-blue`.
- **Never use Tailwind default grays** for backgrounds — use `bg-site-bg` or `bg-white/[0.07]`.
- **Red (`site-red`) only for errors and damage** — not for buttons or accents.

---

## 3. Typography

| Style | Classes | Usage |
|-------|---------|-------|
| Hero title | `gold-text text-4xl font-medium uppercase` | Page titles, hero sections |
| Section title | `gold-text text-2xl font-medium uppercase` | Section headers |
| Card title | `gold-text text-xl font-medium uppercase` | Card headers |
| Nav link | `nav-link text-base` or `nav-link text-sm` | Navigation items |
| Body text | `text-white text-base font-normal` | Regular text |
| Small label | `text-white text-xs font-medium uppercase tracking-[0.06em]` | Labels, badges |
| Form text | `text-input text-base` | Input values |
| Link text | `site-link` or `text-white hover:text-site-blue transition-colors` | Interactive links |

### Font scale

- `text-4xl` (36px) — Hero titles
- `text-3xl` (30px) — Large section titles
- `text-2xl` (24px) — Section titles, gold-text standard
- `text-xl` (20px) — Card titles, button text
- `text-base` (16px) — Body, nav links
- `text-sm` (14px) — Secondary text, dropdown items
- `text-xs` (12px) — Labels, tooltips, timestamps

---

## 4. Reusable Component Classes

All defined in `src/index.css` under `@layer components`.

### Gold Text
```html
<h2 class="gold-text text-2xl font-medium uppercase">Заголовок</h2>
```
Applies gold gradient with `background-clip: text`. Works with any `text-*` size.

### Gold Outline Border
```html
<div class="gold-outline relative rounded-card">Content</div>
```
Adds a 1px gold gradient border via `::after`. **Requires `relative` and a border-radius.**

Thick variant (2px, for modals/active states):
```html
<div class="gold-outline gold-outline-thick relative rounded-card">Content</div>
```

### Gray Background
```html
<div class="gray-bg p-6">Container content</div>
```
Applies `rgba(9,10,16,0.62)` background + `border-radius: 15px`.

### Gradient Dividers
```html
<!-- Vertical divider (right side) -->
<div class="gradient-divider">Column</div>

<!-- Horizontal divider (bottom) -->
<div class="gradient-divider-h">Section</div>
```

### Hover Gold Overlay
```html
<div class="hover-gold-overlay rounded-card">
  <span class="relative z-10">Button text</span>
</div>
```
Shows a subtle gold gradient on hover. Content needs `relative z-10` to stay above overlay.

### Dark Bottom Gradient (for image cards)
```html
<div class="dark-bottom-gradient rounded-card overflow-hidden">
  <img src="..." class="w-full h-full object-cover" />
</div>
```

### Buttons
```html
<!-- Primary action button -->
<button class="btn-blue">Подтвердить</button>

<!-- Line button (top border) -->
<button class="btn-line">Действие</button>
```

### Chip Outline (toggle chips / filter pills)
```html
<!-- Filter pill (rounded-full) -->
<button class="chip-outline rounded-full px-4 py-2 text-xs font-medium">Все</button>
<button class="chip-outline chip-outline-active rounded-full px-4 py-2 text-xs font-medium">PvP</button>

<!-- Rail chip (rounded-card, e.g. craft profession rail) -->
<button class="chip-outline rounded-card px-4 py-2">Кузнец</button>
```
Framed toggle chip: subtle white border + fill, text brightens on hover; `chip-outline-active` switches to the gold state (gold gradient fill, gold border, `#fff9b8` text). Shape-agnostic — the caller picks the radius (`rounded-full` for filter pills, `rounded-card` for rail chips).

### Links
```html
<!-- Standard link with blue hover -->
<a class="site-link" href="...">Текст ссылки</a>

<!-- Nav link (uppercase, tracking) -->
<a class="nav-link text-base" href="...">НАВИГАЦИЯ</a>
```

### Dropdowns
```html
<div class="dropdown-menu">
  <a class="dropdown-item" href="...">Пункт меню</a>
  <a class="dropdown-item" href="...">Пункт меню</a>
</div>
```

### Form Elements
```html
<!-- Underline input -->
<input class="input-underline" placeholder="Введите текст" />

<!-- Bordered textarea -->
<textarea class="textarea-bordered" rows="4" placeholder="Описание" />
```

### Modals
```html
<div class="modal-overlay">
  <div class="modal-content gold-outline gold-outline-thick">
    <h2 class="gold-text text-2xl uppercase mb-4">Заголовок</h2>
    <p class="text-white">Содержимое</p>
  </div>
</div>
```

### Scrollbar
```html
<div class="gold-scrollbar overflow-y-auto max-h-[300px]">
  <!-- scrollable content -->
</div>
```

### Tooltips
```html
<div class="site-tooltip gold-outline">Подсказка</div>
```

### Image Cards
```html
<div class="image-card rounded-card shadow-card" style={{ backgroundImage: `url(...)` }}>
  <div class="dark-bottom-gradient h-full flex flex-col justify-end p-4">
    <h3 class="gold-text text-xl">Title</h3>
  </div>
</div>
```

---

## 5. Shadows & Depth

| Token | Value | Usage |
|-------|-------|-------|
| `shadow-card` | `4px 6px 4px 0 rgba(0,0,0,0.25)` | Card elevation |
| `shadow-hover` | `0 8px 10px ...` | Hover state elevation |
| `shadow-pressed` | `0 2px 4px ...` | Active/pressed state |
| `shadow-modal` | `0 0 12px ...` | Modal glow |
| `shadow-dropdown` | `0 4px 8px ...` | Dropdown menus |

---

## 6. Border Radius

| Token | Value | Usage |
|-------|-------|-------|
| `rounded-card` | 15px | Standard card, dropdown, modal |
| `rounded-card-lg` | 20px | Large buttons, dropdowns |
| `rounded-card-xl` | 29px | Detail cards |
| `rounded-map` | 40px | Map containers |
| `rounded-[16px]` | 16px | Image card containers |
| `rounded-full` | 50% | Avatars, circles |

---

## 7. Spacing Conventions

- **Content container**: `max-w-container` (1360px) — site-wide max width for the header and all page wrappers. Never hardcode `max-w-[1240px]` / `max-w-[1360px]`; the value lives in `tailwind.config.js` (`theme.extend.maxWidth.container`).
- **Page padding**: `px-5` (20px sides), handled by `#root`
- **Section gap**: `gap-[60px]` or `gap-[45px]`
- **Component gap**: `gap-5` (20px) or `gap-[30px]`
- **Inner padding**: `p-4` to `p-6` for cards
- **Margin bottom between sections**: `mb-20` (80px) or `mb-[100px]`
- **Header margin bottom**: `mb-20` (80px)

---

## 8. Animations

| Token | Duration | Usage |
|-------|----------|-------|
| `transition-colors duration-200 ease-site` | 0.2s | Color changes (hover) |
| `transition-all duration-200 ease-site` | 0.2s | Multi-property transitions |
| `transition-opacity duration-300 ease-site` | 0.3s | Fade effects |
| `animate-fade-in` | 0.2s | Modal appearance |
| `animate-spin-slow` | 2s | Rotating elements |

---

## 9. Hover & Interaction Patterns

### Link hover
```
text-white → text-site-blue (0.2s)
```
Use `site-link` class or `hover:text-site-blue transition-colors`.

### Button hover (gold overlay)
```
Use `hover-gold-overlay` class on the container.
```

### Button hover (elevation)
```
shadow-card → shadow-hover → shadow-pressed
```
Use `shadow-card hover:shadow-hover active:shadow-pressed transition-shadow`.

### Dropdown item hover
```
transparent → bg-white/[0.07] (0.2s)
```
Use `dropdown-item` class.

### Input focus
```
border-white → border-site-blue (0.2s)
```
Built into `input-underline` class.

---

## 10. Patterns to AVOID

| Bad | Good | Why |
|-----|------|-----|
| `hover:text-gray-300` | `hover:text-site-blue` | Gray is not in the palette |
| `bg-[#1a1a2e]/95` | `bg-site-bg` or `gray-bg` | Use design tokens |
| `rounded-lg` | `rounded-card` | 15px is the site standard |
| `text-blue-400` | `text-site-blue` | Use site blue, not Tailwind blue |
| `bg-red-500` | `bg-site-red` | Use site red (except notification badge which can keep red-500) |
| Random hex colors | Palette tokens | No freestyle colors |
| Heavy backgrounds everywhere | Transparent/subtle | Site is airy, not heavy |
| Custom transition timing | `duration-200 ease-site` | Consistency |
| New CSS/SCSS files | Tailwind classes or `@layer` | Migration to Tailwind |
| `font-bold` on everything | `font-medium` (500) | Site default weight |

---

## 11. Component Composition Examples

### Card with gold title and overlay
```tsx
<div className="image-card rounded-card shadow-card hover-gold-overlay"
     style={{ backgroundImage: `url(${img})` }}>
  <div className="dark-bottom-gradient h-full flex flex-col justify-end p-4">
    <h3 className="gold-text text-xl font-medium uppercase relative z-10">
      Название
    </h3>
  </div>
</div>
```

### Dropdown menu
```tsx
<div className="dropdown-menu">
  {links.map(link => (
    <Link to={link.path} className="dropdown-item">
      {link.label}
    </Link>
  ))}
</div>
```

### Section with divider
```tsx
<section className="gray-bg p-6 gradient-divider-h">
  <h2 className="gold-text text-2xl font-medium uppercase mb-4">Раздел</h2>
  <p className="text-white">Содержание раздела.</p>
</section>
```

### Modal dialog
```tsx
<div className="modal-overlay">
  <div className="modal-content gold-outline gold-outline-thick">
    <h2 className="gold-text text-2xl uppercase mb-4">Подтверждение</h2>
    <p className="text-white mb-6">Вы уверены?</p>
    <div className="flex gap-4">
      <button className="btn-blue">Да</button>
      <button className="btn-line">Отмена</button>
    </div>
  </div>
</div>
```

---

## 12. Motion Animations (framer-motion)

Library: `motion` (npm package, formerly Framer Motion). Use for page transitions, component enter/exit, interactive animations.

**Strategy: organic adoption.** Don't rewrite existing CSS transitions. Instead:
- **New components** — use Motion for enter/exit animations, layout transitions.
- **Modifying existing component** — if the task touches animations, migrate to Motion.
- **Task doesn't involve animations** — leave CSS transitions as is.

### Import

```tsx
import { motion, AnimatePresence } from 'motion/react';
```

### Standard Presets

Use these consistent patterns across the project:

#### Fade In (for page content, cards, sections)
```tsx
<motion.div
  initial={{ opacity: 0, y: 10 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.3, ease: 'easeOut' }}
>
  Content
</motion.div>
```

#### Fade In with Scale (for modals, tooltips)
```tsx
<motion.div
  initial={{ opacity: 0, scale: 0.95 }}
  animate={{ opacity: 1, scale: 1 }}
  exit={{ opacity: 0, scale: 0.95 }}
  transition={{ duration: 0.2, ease: 'easeOut' }}
>
  Modal content
</motion.div>
```

#### Stagger Children (for lists, grids)
```tsx
<motion.div
  initial="hidden"
  animate="visible"
  variants={{
    hidden: {},
    visible: { transition: { staggerChildren: 0.05 } },
  }}
>
  {items.map(item => (
    <motion.div
      key={item.id}
      variants={{
        hidden: { opacity: 0, y: 10 },
        visible: { opacity: 1, y: 0 },
      }}
    >
      {item.content}
    </motion.div>
  ))}
</motion.div>
```

#### Dropdown / Menu (with AnimatePresence)
```tsx
<AnimatePresence>
  {isOpen && (
    <motion.div
      initial={{ opacity: 0, y: -5 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -5 }}
      transition={{ duration: 0.15 }}
      className="dropdown-menu"
    >
      {children}
    </motion.div>
  )}
</AnimatePresence>
```

#### Hover Scale (for interactive cards)
```tsx
<motion.div whileHover={{ scale: 1.02 }} transition={{ duration: 0.2 }}>
  Card
</motion.div>
```

### Rules

- **Keep durations consistent** — 0.15s for micro-interactions, 0.2-0.3s for content, 0.4s max.
- **Ease: `easeOut`** for enters, `easeIn` for exits. Never `linear` for UI elements.
- **Don't over-animate** — not every element needs animation. Focus on: page enters, modals, dropdowns, lists, route transitions.
- **Always use `AnimatePresence`** for exit animations (elements being removed from DOM).
- **`layout` prop** sparingly — only for elements that change position (tabs, reorderable lists).

---

## 13. Inventory / Profile Components

New classes added for the profile and inventory page (FEAT-009).

### Color Tokens

Added to `tailwind.config.js`:

| Token | Value | Usage |
|-------|-------|-------|
| `bg-rarity-common` | `#FFFFFF` | Common items (white) |
| `bg-rarity-rare` | `#76A6BD` | Rare items (blue) |
| `bg-rarity-epic` | `#B875BD` | Epic items (purple) |
| `bg-rarity-mythical` | `#F0695B` | Mythical items (red) |
| `bg-rarity-legendary` | `#F0D95C` | Legendary items (gold) |
| `bg-stat-hp` | `#E94545` | Health bar (red) |
| `bg-stat-mana` | `#76A6BD` | Mana bar (blue) |
| `bg-stat-energy` | `#88B332` | Energy bar (green) |
| `bg-stat-stamina` | `#FFF9B8` | Stamina bar (gold) |

### Item Cell

Circular 80px cell with gold gradient border for inventory and equipment slots.

```html
<!-- Filled item cell -->
<div class="item-cell">
  <img src="item-image.png" class="w-full h-full object-cover" />
</div>

<!-- Empty item cell (darker, placeholder) -->
<div class="item-cell item-cell-empty">
  <img src="placeholder-icon.svg" class="w-8 h-8 opacity-40" />
</div>
```

### Rarity Backgrounds

Apply on `item-cell` to show rarity-colored gradient fill. Uses `linear-gradient(180deg, transparent 0%, <color> 100%)` pattern.

```html
<div class="item-cell rarity-common">...</div>
<div class="item-cell rarity-rare">...</div>
<div class="item-cell rarity-epic">...</div>
<div class="item-cell rarity-mythical">...</div>
<div class="item-cell rarity-legendary">...</div>
```

### Stat Bars

Progress bars for HP, Mana, Energy, Stamina. Container is `stat-bar`, inner fill is `stat-bar-fill` with a color class.

```html
<div class="stat-bar">
  <div class="stat-bar-fill stat-bar-hp" style="width: 75%"></div>
</div>
<div class="stat-bar">
  <div class="stat-bar-fill stat-bar-mana" style="width: 60%"></div>
</div>
<div class="stat-bar">
  <div class="stat-bar-fill stat-bar-energy" style="width: 90%"></div>
</div>
<div class="stat-bar">
  <div class="stat-bar-fill stat-bar-stamina" style="width: 50%"></div>
</div>
```

### Category Icon

Sidebar icon for inventory category filtering. 43px square, dimmed by default, bright on active.

```html
<!-- Inactive category -->
<button class="category-icon">
  <img src="sword.svg" />
</button>

<!-- Active category (gold gradient border) -->
<button class="category-icon category-icon-active">
  <img src="sword.svg" />
</button>
```

### Skill Point Dot

30px circle with radial gradient and concentric white rings. Used for stat point indicators.

```html
<div class="skill-point-dot"></div>
```

### Context Menu

Positioned dropdown for item actions. Uses gold gradient border. Combine with `dropdown-item` for menu entries.

```html
<div class="context-menu" style="top: 100px; left: 200px">
  <button class="dropdown-item">Надеть</button>
  <button class="dropdown-item">Снять</button>
  <button class="dropdown-item">Использовать</button>
  <button class="dropdown-item">Выбросить</button>
</div>
```

### Hover Divider

Shows a subtle horizontal gradient line on hover. Useful for list rows and category items.

```html
<div class="hover-divider py-2">
  Row content — divider appears on hover
</div>
```

### Gold Scrollbar Wide

Compact (8px) scrollbar with a subtle 2px faded white track and gold gradient thumb. For inventory grid scroll areas.

```html
<div class="gold-scrollbar-wide overflow-y-auto max-h-[500px]">
  <!-- scrollable inventory grid -->
</div>
```

### SVG Icons

Equipment icons located in `src/assets/icons/equipment/`:

| File | Item Type | Usage |
|------|-----------|-------|
| `sword.svg` | `main_weapon`, `additional_weapons` | Weapon slots |
| `armor.svg` | `body` | Body armor slot |
| `helmet.svg` | `head` | Head slot |
| `cloak.svg` | `cloak` | Cloak slot |
| `belt.svg` | `belt` | Belt slot |
| `necklace.svg` | `necklace` | Necklace slot |
| `potion.svg` | `consumable` | Potions / consumables |
| `scroll.svg` | `scroll` | Scrolls |
| `resource.svg` | `resource` | Resources |
| `bag.svg` | `misc` / `all` | Misc items, "all" category |
| `shield.svg` | `bracelet` | Shield / bracelet slot |
| `ring.svg` | `ring` | Ring slot |

---

## 14. Reference: Where Patterns Come From

| Pattern | Source component | Source file |
|---------|-----------------|------------|
| Gold text gradient | HomePageButton title | `HomePage/HomePageButton/HomePageButton.module.scss` |
| Gold outline border | PlayerCard, Modal | `global.scss` → `@mixin gold-outline` |
| Gray background | Stats container, modals | `global.scss` → `@mixin gray-background-br` |
| Gradient divider | Stats columns, character creation | `global.scss` → `@mixin vertical-gradient-line` |
| Hover gold overlay | HomePageButton, SmallHomePageButton | `HomePageButton.module.scss` → `.link:hover::before` |
| Blue gradient button | BlueGradientButton | `BlueGradientButton.module.scss` |
| Line button | LineButton | `LineButton.module.scss` |
| Dropdown styling | World page dropdowns | `DropdownLayout.module.scss` |
| Dark bottom gradient | PlayerCard, NeighborCard | `PlayerCard.module.scss` |

---

## 16. Lore / Book Surfaces (FEAT-154)

**The one exception to the dark UI.** Parchment surfaces represent in-world documents:
the Скиталец passport (`CharacterPassport`) and the Архив (lore wiki). Everything else in
the app stays dark. **Never mix the two languages** — no `gold-text`, `gray-bg`, `site-blue`
or `text-white` on a parchment page; use the `ink` tokens instead.

Both faces are already loaded by `index.html` — **do not add another font link.**

### Tokens (`tailwind.config.js`)

| Token | Value | Usage |
|-------|-------|-------|
| `bg-parchment-light` | `#faf1dc` | Lightest paper, highlights |
| `bg-parchment` | `#f5e6c8` | Base parchment |
| `bg-parchment-dark` | `#e3d0aa` | Aged paper, insets, borders |
| `text-ink` | `#3b2f1c` | Body text on parchment |
| `text-ink-muted` | `#6b5a3e` | Labels, captions, secondary text |
| `font-lore` | `MedievalSharp, Georgia, serif` | Headings, seals, in-world titles |
| `font-serif` | `Cormorant Garamond, Georgia, serif` | Body text on parchment |
| `shadow-page` | `inset 0 0 40px rgba(90,66,30,.18), 4px 6px 10px rgba(0,0,0,.35)` | Aged vignette + page lift |

`font-serif` intentionally overrides Tailwind's default serif stack — the whole app's serif
is Cormorant Garamond.

### Component classes (`src/index.css` → `@layer components`)

| Class | What it does |
|-------|--------------|
| `book-page` | The parchment sheet: ink text color, serif font, paper gradient with age spots. `position: relative` (so absolute children and the gutter anchor to it). CSS-only — no bitmap texture, no extra DOM layers. |
| `book-page-gutter` | Binding seam down the middle of a two-page spread. Renders **only from `md:` up**, so a spread that stacks on mobile shows no stray line. Requires a positioned parent — pair it with `book-page`. ⚠️ **Currently unused.** `CharacterPassport` dropped it: with the long free-text sections running full width under the identity block, the sheet is one page with two columns, not a spread, and the spine read as a leftover. Apply it only to a surface that really is a two-page spread; prefer `lore-divider` for separation. |
| `lore-heading` | MedievalSharp heading in ink. Size stays with Tailwind (`text-xl`, `text-2xl`, …). |
| `lore-body` | Free-text block on parchment: serif, ink, `line-height: 1.65`. Combine with `whitespace-pre-wrap` for user-entered text — **never `dangerouslySetInnerHTML`**. |
| `lore-divider` | Faded ink rule with a small diamond in the middle. |
| `wax-seal` | Round red wax stamp, 64px (76px from `sm:`), tilted −6°. Put the sigil or initials inside. |
| `passport-field` + `passport-field-label` + `passport-field-value` | Label/value row on a dashed ruling. Wraps on narrow screens, so it survives 360px. |
| `lore-badge` | Small pill marker **on parchment** — the ink twin of `chip-outline`, which is built for the dark UI and is invisible on paper. Neutral ink by default. |
| `lore-badge-warn` | Ochre variant. Attention, **not** failure — an allowed-but-unusual choice (e.g. «Редкий выбор», rule 11). |
| `lore-badge-ok` | Green-ink variant — accepted / approved. |
| `lore-badge-danger` | Red-ink variant, matched to `wax-seal` red (never `site-red`) — rejected. |

### Usage

```tsx
<article className="book-page rounded-card shadow-page p-5 sm:p-8
                    grid gap-6 md:grid-cols-2">
  <div>
    <h2 className="lore-heading text-2xl">Паспорт Скитальца</h2>
    <div className="lore-divider my-4" />

    <div className="passport-field">
      <span className="passport-field-label">Раса</span>
      <span className="passport-field-value">Рюджин</span>
    </div>
    <div className="passport-field mt-3">
      <span className="passport-field-label">Мегалинк</span>
      <span className="passport-field-value">СК-000501</span>
    </div>
  </div>

  <div className="flex flex-col items-center gap-4">
    <div className="wax-seal"><span className="text-lg">СК</span></div>
    <div className="flex flex-wrap gap-2">
      <span className="lore-badge lore-badge-warn">Редкий выбор</span>
      <span className="lore-badge lore-badge-ok">Одобрена</span>
    </div>
    <p className="lore-body whitespace-pre-wrap">{biography}</p>
  </div>
</article>
```

### Rules

- **Airy still applies** — one parchment sheet per surface. Don't nest `book-page` inside
  `book-page`, and don't stack extra beige panels on it; use `lore-divider` and
  `passport-field` rulings to separate content instead of more backgrounds.
- **Responsive from 360px** — the seal shrinks below `sm`, and
  `passport-field` wraps its value under its label. Keep spreads as `grid md:grid-cols-2`.
- **No dark-UI chips on paper** — `chip-outline` is designed for the dark background and
  disappears on parchment. Use the `lore-badge` family instead.
- **Reference surfaces:** `CommonComponents/CharacterPassport/` (the full spread and the
  compact card — the reference use of this section, `book-page-gutter` excepted) and
  `ArchiveLinkPreview.tsx` (the hover preview), built on
  `book-page` + `lore-heading`. The full Archive pages
  (`pages/ArchivePage/ArchiveArticlePage.tsx`) keep their own richer, texture-layered
  parchment — that treatment is deliberately page-specific and is not part of the system.

---

## 17. Field Hints (FEAT-154)

The small explanatory line under (or beside) a control: what to write in a field, what a
control does, what a step is for. On the character-creation wizard most of it is spoken in
the voice of the Координатор Скитальцев.

Hints are meant to be **read, not skimmed**. A `text-white/40 text-[11px]` footnote is
invisible, and on this wizard a missed instruction costs the player a rejected application.

### Classes (`src/index.css` → `@layer components`)

| Class | What it does |
|-------|--------------|
| `field-hint` | The hint line: 13px (14px from `sm:`), soft gold — the `gold` token `#f0d95c` at 0.8 alpha — `line-height: 1.5`, with a faded gold hairline down the left edge. Soft gold, **not** the `gold-text` gradient: that gradient is tuned for short uppercase headings and shouts across a multi-line paragraph. Sized **one notch under** the field's own label (`text-white text-sm sm:text-base`) on purpose — noticeable, still auxiliary. |
| `field-hint-strong` | Modifier on `field-hint` for a hint that states a **requirement** — the instruction whose absence gets the application sent back. Adds a faint gold wash and `rounded-card` backing (with the rule inset to match). The backing, not the colour, is what makes it stand out now that every hint is gold. |

### Usage

```tsx
<span className="field-hint">
  Нрав, привычки, с чем вы не миритесь.
</span>

<span className="field-hint field-hint-strong">
  Обязательно напишите, как вы стали Скитальцем — без этого заявку вернут.
</span>
```

### Rules

- **Gold marks the hint, not emphasis.** Only explanatory hint lines go gold. Data
  annotations, counters (`12/20`), kickers and empty states stay `text-white/40–60`.
- **One backed hint per surface.** `field-hint-strong` is for a stated requirement, not
  for emphasis. If every hint is backed, none of them reads as required.
- **Never louder than the field label.** The label stays pure white at
  `text-sm sm:text-base`; the hint stays below it in size.
- **Not for errors, warnings or blockers.** A validation error is `text-site-red`; a
  «why can't I continue» status stays neutral white (`text-white/50 text-[13px] sm:text-sm`);
  an allowed-but-unusual choice keeps its gold-bordered box. This family is for instructions.
- **Dark UI only.** On parchment use `lore-body` / `text-ink-muted` (§16) — the gold text
  and gold rule disappear on paper.
- **Reference surface:** `components/CreateCharacterPage/` (all six steps) and
  `components/pages/MyRequestsPage/RequestEditor.tsx`, which reuses those steps.
  ⚠️ The rest of the app still uses the old `text-white/40 text-[11px]` footnote pattern —
  bringing it onto `field-hint` is a separate, larger pass.

---

## 15. For AI Agents

When creating or modifying frontend components:

1. **Read this document first** before writing any styles.
2. **Use component classes** (`gold-text`, `gray-bg`, `dropdown-menu`, etc.) — don't reinvent.
3. **Use Tailwind tokens** (`text-site-blue`, `bg-site-bg`, `rounded-card`, `shadow-card`) — don't use raw hex values.
4. **Check the "Patterns to AVOID" table** — common mistakes are listed there.
5. **When in doubt, look at HomePage** (`src/components/HomePage/`) — it's the design reference.
6. **Keep it airy** — don't add backgrounds where none are needed. The dark background image does the work.
7. **Gold for titles, blue for hover, white for body text** — that's the whole color strategy.
8. **Use Motion** for enter/exit animations on new components — see section 12 for presets.
