import { useEffect, useRef, useState, type ReactNode } from 'react';
import DungeonBoardLive from '../DungeonBoard3D/DungeonBoardLive';
import { HeaderToggle, useFullscreenPage } from '../CommonComponents/Fullscreen/fullscreen';
import type { BoardDungeon, BoardMember } from '../DungeonBoard3D/boardTypes';
import type { CorridorScene, DiceThrow, FloorSpan } from '../DungeonBoard3D/DungeonBoardScene';
import type { BoardMark } from '../DungeonBoard3D/PartyMarks';
import type { DungeonStability } from '../DungeonBoard3D/DungeonDoors';

/*
  The run page in 3D: the table fills the screen under the site header and
  everything else floats over it. Top left: the run's header, the party in a
  list of portraits with their numbers, what is happening now. Right: one
  panel with tabs — the room (its own action and, below, everything the party
  can try here), the run's loot, the chat and log. Bottom middle: where the party goes
  next. On a phone the panel is a bottom sheet with the same tabs.
*/

export type BoardTab = 'room' | 'loot' | 'chat';

const TABS: { tab: BoardTab; label: string }[] = [
  { tab: 'room', label: 'Комната' },
  { tab: 'loot', label: 'Инвентарь' },
  { tab: 'chat', label: 'Чат' },
];

const HEADER_GAP_PX = 12;

interface DungeonBoardViewProps {
  dungeon: BoardDungeon;
  party: BoardMember[];
  currentRoomId: number;
  revealed: Set<number>;
  cleared: Set<number>;
  reachable: Set<number>;
  dice: DiceThrow | null;
  /** The party halfway down a corridor (an ambush, a trap). */
  corridor?: CorridorScene | null;
  /** The whole floor's span: the rock is laid under all of it. */
  span?: FloorSpan | null;
  lowGraphics: boolean;
  stability?: DungeonStability;
  /** The floor shown on the table. */
  floor?: number;
  onPartyArrived?: (roomId: number) => void;
  /** What to say about a room under the pointer: a title and a few lines, or null for nothing. */
  describeRoom?: (roomId: number) => { title: string; lines: string[] } | null;
  onTileClick: (roomId: number) => void;
  /** The run's header: name, phase, connection, way back, the 2D/3D switch. */
  header: ReactNode;
  /** What is happening now: phase banners, the move's outcome. */
  banners: ReactNode;
  /** The current room and its own action (or the battle card). */
  roomPanel: ReactNode;
  /** Everything the party can try in this room (locks, secrets, light, search, shield, watch…); empty = none. */
  roomActions?: ReactNode;
  roomTitle: string;
  /** The run's loot (group inventory, keys) and the way out. */
  groupPanel: ReactNode;
  /** The chat and log. */
  chatPanel?: ReactNode;
  /** Lines in the chat not seen yet. */
  chatUnread?: number;
  /** The tab shown (desktop panel or phone sheet; null = the sheet folded). */
  onTabChange?: (tab: BoardTab | null) => void;
  /** Where the party goes next: the votes (bottom middle). */
  decision?: ReactNode;
  /** The current room waits for the party to do something (chest, event choice…). */
  roomHasAction?: boolean;
  /** The party in a row of portraits. */
  partyStrip?: ReactNode;
  /** The party's flags and marks on the board, and the buttons to make marks. */
  marks?: BoardMark[];
  markTools?: ReactNode;
}

const DungeonBoardView = ({
  dungeon,
  party,
  currentRoomId,
  revealed,
  cleared,
  reachable,
  dice,
  corridor,
  span,
  lowGraphics,
  stability,
  floor,
  onPartyArrived,
  describeRoom,
  onTileClick,
  header,
  banners,
  roomPanel,
  roomActions,
  roomTitle,
  groupPanel,
  chatPanel,
  chatUnread = 0,
  onTabChange,
  decision,
  roomHasAction = false,
  partyStrip,
  marks,
  markTools,
}: DungeonBoardViewProps) => {
  const { top: headerBottom, headerHidden, toggleHeader } = useFullscreenPage();
  const [panelOpen, setPanelOpen] = useState(true);
  const [panelTab, setPanelTab] = useState<BoardTab>('room');
  const [sheetTab, setSheetTab] = useState<BoardTab | null>(null);
  const [hover, setHover] = useState<{ roomId: number; x: number; y: number } | null>(null);
  const hint = hover && describeRoom ? describeRoom(hover.roomId) : null;

  // Arriving where something can be done: bring the room up (once per room). On a phone the sheet would cover the
  // table, so the room tab only lights up there.
  const [roomCalls, setRoomCalls] = useState(false);
  useEffect(() => {
    if (!roomHasAction) return;
    setPanelTab('room');
    setPanelOpen(true);
    setRoomCalls(true);
  }, [roomHasAction, currentRoomId]);

  // Tell the page what is in view (the chat's unread count clears while it is).
  const desktop = useIsDesktop();
  const shownTab = desktop ? (panelOpen ? panelTab : null) : sheetTab;
  useEffect(() => {
    onTabChange?.(shownTab);
  }, [shownTab, onTabChange]);

  const top = headerBottom + HEADER_GAP_PX;

  // The phone's bottom stack (votes, tabs, sheet): the board's buttons stand just above it.
  const phoneStack = useRef<HTMLDivElement>(null);
  const [phoneBottom, setPhoneBottom] = useState(60);
  useEffect(() => {
    const el = phoneStack.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => setPhoneBottom(el.offsetHeight));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const content = (tab: BoardTab) =>
    tab === 'room' ? (
      <>
        {roomPanel}
        {roomActions && (
          <div className="flex flex-col gap-3">
            <p className="gold-text text-xs font-medium uppercase tracking-[0.06em] border-t border-white/10 pt-3">
              Действия
            </p>
            {roomActions}
          </div>
        )}
      </>
    ) : tab === 'loot' ? (
      groupPanel
    ) : (
      chatPanel
    );
  const tabLabel = (tab: BoardTab, label: string) => (
    <>
      {label}
      {tab === 'chat' && chatUnread > 0 && (
        <span className="ml-1.5 inline-flex min-w-[18px] h-[18px] px-1 items-center justify-center rounded-full bg-site-blue text-[10px] text-white tabular-nums">
          {chatUnread > 99 ? '99+' : chatUnread}
        </span>
      )}
    </>
  );

  return (
    <div className="fixed inset-0 z-0 bg-black">
      <HeaderToggle top={headerBottom} hidden={headerHidden} onToggle={toggleHeader} />
      <DungeonBoardLive
        dungeon={dungeon}
        party={party}
        currentRoomId={currentRoomId}
        revealed={revealed}
        cleared={cleared}
        reachable={reachable}
        dice={dice}
        corridor={corridor}
        span={span}
        lowGraphics={lowGraphics}
        stability={stability}
        floor={floor}
        onPartyArrived={onPartyArrived}
        onRoomHover={setHover}
        onTileClick={onTileClick}
        marks={marks}
        extraControls={markTools}
        controlsClassName="absolute right-3 items-end lg:items-start lg:right-auto lg:left-5 lg:!bottom-5"
        controlsStyle={desktop ? undefined : { bottom: phoneBottom + 8 }}
      />

      {/* What lies under the pointer: a small card by the cursor (desktop only — a phone has no hover) */}
      {hover && hint && (
        <div
          className="hidden lg:block fixed z-10 pointer-events-none max-w-[240px] bg-black/85 backdrop-blur-sm rounded-card border border-white/10 px-3 py-2 shadow-card"
          style={{ left: hover.x + 16, top: hover.y + 16 }}
        >
          <p className="gold-text text-sm font-medium leading-tight">{hint.title}</p>
          {hint.lines.map((line) => (
            <p key={line} className="text-white/70 text-xs mt-0.5">
              {line}
            </p>
          ))}
        </div>
      )}

      {/* Top left: the run, the party, what is happening now (on a phone, out of the way while the sheet is open) */}
      <div
        className={`absolute left-3 right-3 lg:left-5 lg:right-auto lg:w-[400px] flex-col gap-2 overflow-y-auto gold-scrollbar max-h-[28vh] lg:max-h-[calc(100vh-280px)] pointer-events-none [&>*]:pointer-events-auto ${
          sheetTab ? 'hidden lg:flex' : 'flex'
        }`}
        style={{ top }}
      >
        {/* On a phone the party comes first: who is how is worth more than the run's title */}
        <div className="order-2 lg:order-none">{header}</div>
        <div className="order-1 lg:order-none">{partyStrip}</div>
        <div className="order-3 lg:order-none flex flex-col gap-2">{banners}</div>
      </div>

      {/* Desktop: where the party goes next, under the table's middle */}
      {decision && (
        <div className="hidden lg:block absolute bottom-5 left-1/2 -translate-x-1/2 w-[min(560px,calc(100vw-920px))] min-w-[360px] pointer-events-none [&>*]:pointer-events-auto">
          {decision}
        </div>
      )}

      {/* Desktop: the side panel with its tabs, can be tucked away */}
      <div
        className="hidden lg:flex absolute right-5 bottom-5 flex-col items-end gap-2 pointer-events-none"
        style={{ top }}
      >
        <div className="pointer-events-auto flex items-center gap-1 bg-black/60 backdrop-blur-sm rounded-card p-1">
          {TABS.map(({ tab, label }) => (
            <button
              key={tab}
              type="button"
              onClick={() => {
                setPanelTab(tab);
                setPanelOpen(true);
              }}
              className={`px-3 py-1.5 rounded-card text-xs font-medium transition-colors duration-200 ease-site ${
                panelOpen && panelTab === tab ? 'bg-white/10 text-white' : 'text-white/60 hover:text-site-blue'
              }`}
            >
              {tabLabel(tab, label)}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setPanelOpen((v) => !v)}
            className="px-2 py-1.5 text-xs text-white/50 hover:text-site-blue transition-colors duration-200 ease-site"
            aria-label={panelOpen ? 'Скрыть панель' : 'Показать панель'}
            title={panelOpen ? 'Скрыть панель' : 'Показать панель'}
          >
            {panelOpen ? '✕' : '☰'}
          </button>
        </div>
        {/* Mounted on one layout only: the room panel asks the server for a merchant's goods. */}
        {panelOpen && desktop && (
          <div
            className={`pointer-events-auto w-[340px] gray-bg backdrop-blur-md border border-white/10 shadow-card p-3 flex flex-col gap-4 ${
              panelTab === 'chat' ? 'flex-1 min-h-0' : 'max-h-full overflow-y-auto gold-scrollbar'
            }`}
          >
            {content(panelTab)}
          </div>
        )}
      </div>

      {/* Phone: where the party goes next above a bottom sheet with tabs */}
      <div ref={phoneStack} className="lg:hidden absolute left-0 right-0 bottom-0 flex flex-col">
        {/* Folded: the votes ride above the tabs; open, they move into the room tab (the table stays in view). */}
        {decision && !sheetTab && <div className="px-3 pb-2 max-h-[30vh] overflow-y-auto">{decision}</div>}
        <div className="flex flex-col bg-black/80 backdrop-blur-sm rounded-t-card border-t border-white/10">
          <div className="flex items-center gap-1 p-1.5">
            {TABS.map(({ tab, label }) => (
              <button
                key={tab}
                type="button"
                onClick={() => {
                  setSheetTab((current) => (current === tab ? null : tab));
                  if (tab === 'room') setRoomCalls(false);
                }}
                className={`flex-1 min-w-0 py-2.5 px-2 text-xs sm:text-sm font-medium rounded-card transition-colors duration-200 ease-site truncate ${
                  sheetTab === tab ? 'bg-white/10 text-white' : 'text-white/60 hover:text-site-blue'
                }`}
              >
                {tabLabel(tab, tab === 'room' ? roomTitle : label)}
                {tab === 'room' && roomCalls && sheetTab !== 'room' && (
                  <span className="ml-1.5 inline-block w-2 h-2 rounded-full bg-gold animate-pulse align-middle" aria-label="Здесь можно что-то сделать" />
                )}
              </button>
            ))}
            {sheetTab && (
              <button
                type="button"
                onClick={() => setSheetTab(null)}
                className="w-10 h-10 shrink-0 flex items-center justify-center text-white/60 hover:text-site-blue transition-colors duration-200 ease-site"
                aria-label="Свернуть"
              >
                ▾
              </button>
            )}
          </div>
          {sheetTab && !desktop && (
            <div
              className={`px-3 pb-4 flex flex-col gap-4 ${
                sheetTab === 'chat' ? 'h-[50vh]' : 'max-h-[50vh] overflow-y-auto gold-scrollbar'
              }`}
            >
              {sheetTab === 'room' && decision}
              {content(sheetTab)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

/** The lg breakpoint (Tailwind's 1024px): the side panel instead of the bottom sheet. */
const useIsDesktop = () => {
  const query = '(min-width: 1024px)';
  const [desktop, setDesktop] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const update = () => setDesktop(mq.matches);
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);
  return desktop;
};

export default DungeonBoardView;
