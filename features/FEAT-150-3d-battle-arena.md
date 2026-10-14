# FEAT-150 — 3D Battle Arena

## 1. Feature Brief (Требование)

**Назначение:** красивая 3D-арена для пошаговых боёв в духе фентези-мира игры: текстуры, освещение, атмосфера.

**Контекст:** прошлая 3D-версия (R3F, `components/pages/BattlePage/3DBattle/`) удалена в 718b412 из-за бесконечного рендера и ошибок типов. Первая попытка в этой фиче (raw three.js в `src/features/battle3d/`) была нерабочей: гигантская табличка с именем закрывала экран, персонажи-кубы, серая коробка, дубли персонажей каждый ход, утечки слушателей, SCSS и английский UI. Она полностью заменена.

**Успех:** 3D — это режим отображения того же боя, в нём можно полноценно играть (выбор навыков, цели, передача хода), работает на мобильных.

---

## 2. Analysis

- Вся логика боя живёт в `BattlePage.tsx` (локальный state + `useBattleWebSocket` + HTTP fallback, очередь состояний с паузой 1100 мс).
- Аватарки лежат на внешнем S3 (Backblaze) **без CORS-заголовков** → WebGL-текстурой их загрузить нельзя (canvas taint). Проверено запросом с `Origin`.
- three 0.160.1, @react-three/fiber 8.18, @react-three/drei 9.122 уже стояли в зависимостях.

## 3. Architecture

3D — **режим `BattlePage`**, а не отдельная страница. Маршрут `/location/:id/battle3d/:battleId(/spectate)` рендерит тот же `BattlePage`; флаг `is3D` берётся из пути. Вся боевая логика, панель хода (`BattlePageBar`), баннеры и модалки общие; в 3D вместо колонок карточек рисуется сцена.

```
components/pages/BattlePage/Arena3D/
├── ArenaScene.tsx       # <Canvas>, камера под ширину экрана, расстановка команд (lazy-чанк)
├── ArenaEnvironment.tsx # пол, рунный круг, колонны, факелы с мерцанием, искры, туман, свет
├── Fighter3D.tsx        # постамент + кольцо состояния + столб света, тряска/вспышка при уроне
├── FighterCard.tsx      # DOM-карточка (drei <Html>): портрет, имя, HP/мана/энергия, эффекты, цифры урона
├── textures.ts          # процедурные canvas-текстуры (камень пола/колонн, руны) — без внешних картинок
├── arenaTypes.ts
└── webgl.ts             # проверка WebGL → иначе обычный 2D с предупреждением
```

Решения:
- **Портреты — HTML поверх сцены** (`<Html>` из drei): обходит отсутствие CORS у S3, стилизуется Tailwind, кликабелен для выбора цели. `zIndexRange [30,0]` — под модалками (z 1000).
- **Без Redux** — анимации локальны в `Fighter3D` (сравнение HP с прошлым значением).
- **three.js в отдельном lazy-чанке** — 2D-бой его не грузит (основной бандл 3.9 МБ → 3.4 МБ).
- Края канваса растворяются в фоне страницы через CSS `mask-image` («воздушный» дизайн).

### 3.1 HUD (full-width 3D layout)

- Control-panel logic extracted from `BattlePageBar.tsx` into `BattlePageBar/useBattleBar.tsx` (slots, picker, turn queue, history, logs + formatting, autobattle speed/feedback). `BattlePageBar` (2D) keeps its markup and renders from the hook; `AvatarCircle` moved to its own file.
- `Arena3D/hud/`: `ArenaHud` (full-bleed layout, owns the hook), `TurnBanner` (turn №, actor, status, countdown, queue), `ActionBar` + `SlotMedallion` + `TurnSeal` (rune-ring "Передать ход"), `AutobattleControls`, `Chronicle` («Летопись боя»: history strip + selected turn log), `HudFrame` (leather/gilt panel skin using `/textures/dark-leather.png`).
- Desktop (lg+): arena is 100vw × (100vh − header); banner top-centre, notices under it, action bar bottom-centre, chronicle right (open by default), 2D/3D toggle top-left. `<html>` gets `overflow-x: clip` while mounted (100vw includes the scrollbar).
- Phone/tablet: arena 56vh; slots + seal + autobattle pinned to the bottom of the screen; chronicle opens as a bottom sheet.
- Tailwind keyframes added: `seal-glow`, `spin-rune` (reuses `spin-slow`).

### 3.2 Battle effects

- `Arena3D/BattleEffects.tsx`: `AimArc` (drei `QuadraticBezierLine`, marching dashes; red = attack target, green = ally target; anchored on pedestal front lips because DOM cards cover the canvas), `Projectile` (bolt + own ghost-sphere wake — drei `Trail` drew offset inside a moving group), `ImpactBurst` (expanding ring + light flash).
- `ArenaScene.useStrikes`: an HP drop on anyone but the previously acting fighter = a strike from that fighter. Detected **during render** (`useMemo`) so the victim card keeps its old HP/death state until the bolt lands (`FLIGHT_MS` 450, must stay below BattlePage `MIN_TURN_GAP_MS` 1100). Attacker card lunges toward the target (`Fighter3D` `lunge` prop).
- Rune circle = turn clock: dim full circle + lit sector (`CircleGeometry` thetaLength) burning down; red pulse under 10%. Total length `TURN_DURATION_MS` mirrors battle-service `TURN_TIMEOUT_HOURS` (24h default) — client constant, see risk below.
- `CameraRig` drifts look-at/position toward the acting fighter (30% of their x).

Known limits: periodic effect damage (bleeding etc.) on a non-actor will also be drawn as a bolt from the actor; if `TURN_TIMEOUT_HOURS` is changed in env, the rune clock will be off (decorative only).

### 3.3 Table of fates (replaces the stone arena)

Art direction agreed with the user: a dark table on which gods play with mortals' fates, Hearthstone-style top-down board.
- `ArenaEnvironment`: dark plank table (procedural, radial fade), board with an engraved gold star-chart texture (near half cold, far half crimson), brass rim with corner knobs, 4 candle clusters with flickering light, spotlight from above, dust motes, rune-circle clock in the centre. Board is 12×9 landscape, 9×12 portrait on phones (`boardSize`, `PORTRAIT_QUERY` max-width 767px).
- Camera ~72° pitch, distance fitted to board + candles (`fitDistance`), gentle drift toward the acting fighter. Viewer's team on the near row, opponents on the far row.
- Cards: no slots/pedestals; contact shadow + state-coloured glow pool on the board. `FighterCard` is a heavy gilded card (edge thickness, bevelled frame, corner studs, name plate, HP/mana/energy gems, "Вы" marker). Card size tied to canvas height (`CARD_SCALE_PER_PX`) because drei `<Html>` scales by camera distance only.
- Desktop HUD: turn banner + vertical action panel (2×2 medallions, seal, autobattle) on the left, chronicle on the right.
- Static camera (no sway/drift); re-framed only on resize. Canvas edges dissolve via two intersected CSS masks (radial + vertical) so there is no hard line under the site header.
- **Location art on the board**: `BattlePage` fetches `GET /locations/{id}/details` (public, ~1 KB) in 3D mode; `image_url` is rewritten by `sameOriginMedia.ts` to `/s3-media/fallofgods/…` and painted into the board canvas texture (cover-fit, desaturated, darkened, vignetted) under the star chart.
- **Infra**: new read-only nginx route `/s3-media/fallofgods/` in `nginx.conf` **and** `nginx.prod.conf` → Backblaze bucket. GET/HEAD only (POST → 403), host resolved per request via Docker DNS (`127.0.0.11`) so a DNS failure can't stop the gateway from booting, cookies/auth stripped, `Cache-Control: public, max-age=604800`. Verified locally: image → 200 `image/webp`; `..`/`%2e%2e` traversal never leaves the route (falls through to the SPA). The bucket has no CORS and the user has no access to its settings — that's why it's a proxy. Prod needs the gateway image rebuilt (CI's `up --build` does it).
- **Candles** (`ArenaEnvironment`): brass dish + short matte candles with melted rim, wick and drip; flame = additive teardrop sprite + opaque core + halo; warm light pool on the table; point light off to the side so wax tops aren't burnt white from above.
- **Table props** (`TableProps.tsx`, landscape only — the portrait board has no room beside it): bone **dice of fate** that tumble in and land on double six on a **critical hit** (crit = a `damage` event with `critical` in the live turn's log, detected in `ArenaHud.useCriticalHitMoment`; the turn already on screen at page load never replays), gold **coin** stacks and loose coins with a struck crown, and a brass **hourglass** whose sand drains with the turn timer (open ring on top so the sand shows from above).
- **Table edge to edge**: the plank table is 90×44 world units and fully opaque; it runs under both HUD columns and darkens naturally away from the candles. The canvas keeps only the vertical (top/bottom) CSS fade.
- **More decor** (`TableProps.tsx`): two face-down decks of fate (one per side, a couple of cards cast beside yours), a brass goblet with wine and a spilled drop, a green-glass inkwell with a brass collar and a quill, a parchment letter under a red wax seal, carved rune stones. Dagger and skull deliberately skipped — they'd need real models.
- **Table scars with meaning** (`createTableScarsTexture`, a non-repeating transparent layer over the table, all screen sizes): knife gouges, four parallel claw marks, cup rings, scorch marks round the candles, a crude knife-cut rune in a circle, fine scratches, and the **gods' old score** in the lower-right corner — two rows of tallies split by a line. Placed only where the table is actually visible (far edge and the area under the left HUD are off-screen/covered).
- **Live turn tally** (`TurnTally`, landscape): one notch per completed turn (`runtime.turn_number`), groups of five, cut as pale raw wood; the newest notch glows gold for ~2.6 s. The count already on screen at page load doesn't glow.
- Spectate mode in 3D verified live (battle 241): "Наблюдение" banner, no action panel, chronicle works, board art switches to that location's image.
- **Worn board rim** (`BrassRim` + `createWornBrassTextures`): colour/bump/roughness maps with tarnish heavier at the corners, verdigris creeping from the ends, bright hand-rubbed patches, ~140 scratches, dents and four deep blade nicks. All bars are built along x and turned into place so the wear runs along each bar; each bar is a hair off true (tiny tilt/sag) and one corner knob is squashed. Rim widened to 0.34 so the wear reads on screen.
- **Dagger** (`TableProps.Dagger`): extruded leaf blade with fuller, iron crossguard, banded leather grip, pommel; driven at a slant through the sealed letter (`PinnedLetter`), split-wood decal round the entry point.
- **Hit feedback reworked** (user disliked the ring and the numbers): ring burst replaced with small **embers** (44 soft sprites) shed from the struck card's outline — not its centre, the DOM card would hide them — that hop a little, fall onto the board and cool from white-hot through orange to dull coal over ~2.2 s, each at its own pace (user rejected the earlier big, side-coloured "rainbow" sparks); a blade slash streak wipes across the struck portrait (`animate-slash`); damage numbers are Cormorant Garamond 600 with **lining** numerals (old-style "1" read as "I"), metal gradient fill, dark rim and coloured glow, slam-in/settle/rise animation (`animate-damage-pop`, 2.3 s).
- **Slower effects**: bolt flight 850 ms, sparks 1.4 s, lunge 650 ms, card hit 1.2 s; BattlePage turn pacing `MIN_TURN_GAP_MS` is **2600 ms in 3D** (1100 in 2D) so the next state doesn't cut the previous turn's effects short.
- Dev gotcha: the `frontend` container's Tailwind does **not** pick up `tailwind.config.js` edits (bind mount, no file events) — custom keyframes (`seal-glow`, `float-up`, …) silently compiled to nothing until `docker restart frontend` (+ `nginx -s reload` in api-gateway for the new container IP). Prod builds are unaffected.
- **Active effects on cards** (`EffectRunes.tsx`): a column of rune stones down the card's right edge, one per effect (green = beneficial, red = harmful, per `describeEffect().positive`), each showing turns left (∞ if no duration); up to 4, then "+N". Hover (desktop) or tap (touch, `stopPropagation` so it doesn't pick a target) opens a panel listing label + detail for every effect. A newly applied effect pings once; effects already present at page load don't. `ArenaFighter.effectNames` replaced by structured `effects: ArenaEffect[]`. Verified live: "Магический щит" → green rune "1", panel "Изменение защиты — 1 ход, 5%".
- Tried and dropped (user feedback): a seated faceless god beyond the far edge with a perspective camera — enemy row and resources became unreadable.

## 4. Tasks

- [x] Удалить первую реализацию (`src/features/battle3d/` перенесена в scratchpad, слайс `arena3d` убран из store)
- [x] Маршруты battle3d → `BattlePage`
- [x] Сцена, окружение, бойцы, карточки
- [x] Выбор цели/союзника кликом по карточке в 3D
- [x] Переключатель 2D/3D на `chip-outline`, в потоке (раньше перекрывал карточку врага), сохраняет `/spectate`
- [x] keyframe `float-up` в `tailwind.config.js`

## 5. Verification

Проверено вживую (Claude in Chrome, локальный стек, бой 235: Арлекино vs Дикий Волк):
- 3D-сцена рендерится, ошибок в консоли нет.
- Сделаны 2 реальных хода из 3D: урон отображается (−43 по волку, −20 по Арлекино) — красная вспышка, тряска, всплывающая цифра; цифры удаляются после анимации; столб света переходит к текущему актору.
- Выбор навыка открывается поверх арены.
- Мобильная ширина 390px: обе карточки и арена помещаются.
- 2D-режим после рефакторинга рендерится как раньше.
- `tsc --noEmit` — 0 ошибок; `vite build` — успешно.

HUD (2026-10-15, бой 238): ход из 3D через медальон → выбор навыка → печать: навык подсвечен, слоты защиты/поддержки заперты правилом первого круга, ход ушёл, летопись заполнилась. 390px: нижняя панель в одну строку, шторка летописи открывается. 2D после выноса логики в хук: рендер + полный ход — работает. Консоль без ошибок, `tsc` 0, `vite build` ок.

Не проверено вживую: режим наблюдения в 3D (логика общая с 2D), групповой бой 3+ на сторону (раскладка дугой рассчитана, но не смотрелась), смерть персонажа (серость/наклон карточки).

## 6. Logging

```
[LOG] 2026-10-14 — PM: создан feature file
[LOG] 2026-10-14 — Frontend: первая реализация (raw three.js) — нерабочая, см. Brief
[LOG] 2026-10-15 — Frontend: переделано с нуля на R3F как режим BattlePage; проверено в браузере
[LOG] 2026-10-15 — Frontend: новый интерфейс 3D (во всю ширину, медальоны, печать хода, летопись), логика панели вынесена в useBattleBar
```

[LOG] 2026-10-15 — Frontend: руны эффектов на картах с панелью описаний; искры заменены угольками
[LOG] 2026-10-15 — Frontend: кинжал, пригвоздивший письмо; искры и росчерк вместо кольца; новые цифры урона; эффекты и пауза между ходами в 3D медленнее. Тестовый бой 244 (763 vs 764) создан локально
[LOG] 2026-10-15 — Frontend: потёртая латунная окантовка доски — патина, окись, царапины, вмятины, зарубки, лёгкая кривизна
[LOG] 2026-10-15 — Frontend: царапины на столе со смыслом (счёт богов, когти, ножи, круги от кубков), живые зарубки ходов; проверен режим наблюдения. Тестовые бои 241, 242 созданы локально, Арлекино (706) вылечена в локальной БД по просьбе пользователя
[LOG] 2026-10-15 — Frontend: стол до краёв экрана под панелями; декор — колоды судеб, кубок, чернильница с пером, письмо с печатью, руны
[LOG] 2026-10-15 — Frontend: свечи на латунных блюдцах; кости судьбы (бросок на крит, проверено с временно включённым «каждое попадание = крит», затем возвращено), монеты, песочные часы
[LOG] 2026-10-15 — DevSecOps/Frontend: прокси /s3-media/ в nginx (dev+prod), роспись локации на доске; камера статична, убрана полоса под шапкой
[LOG] 2026-10-15 — Frontend: «стол судеб» — доска сверху в духе Hearthstone, тяжёлые карты с самоцветами, панель действий слева, вертикальная доска на телефоне; бог за столом опробован и убран по отзыву
[LOG] 2026-10-15 — Frontend: эффекты — дуга прицела, снаряд с выпадом и вспышкой, урон по попаданию, руны-таймер, камера к ходящему; проверено в браузере (полёт замедлялся до 3 с для съёмки и возвращён на 450 мс)

## 7. Summary

3D-арена переделана с нуля и проверена в браузере на настоящем бою. Каменная круглая арена с рунным кругом, колоннами и факелами, синий свет со стороны игрока и красный со стороны врага. Персонажи — карточки-портреты на светящихся постаментах. Есть анимации урона, подсветка хода и выбор цели кликом. Играть в 3D можно полноценно: используется та же логика, что в 2D.

---

## Статус: REVIEW (ждёт просмотра пользователем, не закоммичено)
