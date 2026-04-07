import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchTeleportOptions,
  executeTeleport,
  selectTeleportOptions,
  selectTeleportLoadingOptions,
  selectTeleportOptionsError,
  selectTeleportExecuting,
  selectTeleportExecuteError,
  type TeleportOption,
} from '../../../redux/slices/teleportSlice';
import { setCharacterAfterTeleport } from '../../../redux/slices/userSlice';

interface TeleportMenuProps {
  npcId: number;
  npcName: string;
}

const formatCooldown = (seconds: number): string => {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  return `${h} ч ${m} мин`;
};

const TeleportMenu = ({ npcId, npcName }: TeleportMenuProps) => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();

  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState<TeleportOption | null>(null);

  const options = useAppSelector(selectTeleportOptions(npcId));
  const loading = useAppSelector(selectTeleportLoadingOptions);
  const optionsError = useAppSelector(selectTeleportOptionsError);
  const executing = useAppSelector(selectTeleportExecuting);
  const executeError = useAppSelector(selectTeleportExecuteError);
  const cooldownSecondsRemaining = useAppSelector(
    (s) => s.teleport.cooldownSecondsRemaining,
  );

  useEffect(() => {
    if (open) {
      dispatch(fetchTeleportOptions(npcId));
    }
  }, [open, npcId, dispatch]);

  const handleOpen = () => setOpen(true);
  const handleClose = () => {
    setOpen(false);
    setConfirming(null);
  };

  const handleExecute = async () => {
    if (!confirming) return;
    const action = await dispatch(
      executeTeleport({ npcId, linkId: confirming.link_id }),
    );
    if (executeTeleport.fulfilled.match(action)) {
      const result = action.payload;
      dispatch(
        setCharacterAfterTeleport({
          new_location_id: result.new_location_id,
          new_location_name: result.new_location_name ?? confirming.to_location_name,
          currency_balance: result.currency_balance,
        }),
      );
      setConfirming(null);
      setOpen(false);
      navigate(`/location/${result.new_location_id}`);
    }
  };

  const cooldownActive = cooldownSecondsRemaining > 0;

  return (
    <>
      <button
        onClick={handleOpen}
        className="
          mt-2 w-full px-6 py-3 rounded-card
          border border-gold/50 bg-gold/10
          text-gold text-sm sm:text-base font-medium uppercase tracking-wide
          hover:bg-gold/20 hover:border-gold/80
          transition-all duration-200
          flex items-center justify-center gap-2
        "
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
        Телепорт
      </button>

      {open && (
        <div
          className="modal-overlay !bg-black/80"
          onClick={(e) => {
            if (e.target === e.currentTarget) handleClose();
          }}
        >
          <div className="modal-content gold-outline gold-outline-thick relative max-w-lg w-full mx-4">
            <button
              onClick={handleClose}
              className="absolute top-4 right-4 text-white/50 hover:text-white transition-colors z-10"
              aria-label="Закрыть"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            <h2 className="gold-text text-lg sm:text-xl font-medium uppercase text-center mb-4">
              Телепорт — {npcName}
            </h2>

            {cooldownActive && (
              <p className="text-yellow-400 text-sm text-center mb-3">
                Телепорт будет доступен через {formatCooldown(cooldownSecondsRemaining)}
              </p>
            )}

            {loading && (
              <div className="flex items-center justify-center py-8">
                <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
              </div>
            )}

            {optionsError && !loading && (
              <p className="text-site-red text-sm text-center mb-3">{optionsError}</p>
            )}

            {executeError && (
              <p className="text-site-red text-sm text-center mb-3">{executeError}</p>
            )}

            {!loading && options && options.length === 0 && (
              <p className="text-white/60 text-sm text-center py-6">
                Нет доступных направлений
              </p>
            )}

            {!loading && options && options.length > 0 && (
              <div className="flex flex-col gap-2 max-h-[60vh] overflow-y-auto gold-scrollbar pr-1">
                {options.map((opt) => (
                  <div
                    key={opt.link_id}
                    className="
                      flex flex-col sm:flex-row sm:items-center sm:justify-between
                      gap-2 p-3 rounded-card bg-white/5 border border-white/10
                    "
                  >
                    <div className="flex flex-col">
                      <span className="text-white text-sm font-medium">
                        {opt.to_location_name}
                      </span>
                      <span className="text-white/50 text-xs">{opt.to_npc_name}</span>
                    </div>
                    <div className="flex items-center gap-3 justify-between sm:justify-end">
                      <span className="gold-text text-sm font-medium whitespace-nowrap">
                        {opt.cost_gold} зол.
                      </span>
                      <button
                        onClick={() => setConfirming(opt)}
                        disabled={executing || cooldownActive}
                        className="
                          px-3 py-1.5 rounded-card text-xs sm:text-sm font-medium uppercase
                          border border-gold/50 bg-gold/10 text-gold
                          hover:bg-gold/20 hover:border-gold/80
                          transition-all duration-200
                          disabled:opacity-50 disabled:cursor-not-allowed
                        "
                      >
                        Телепортироваться
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {confirming && (
        <div
          className="modal-overlay !bg-black/90"
          onClick={(e) => {
            if (e.target === e.currentTarget) setConfirming(null);
          }}
        >
          <div className="modal-content gold-outline gold-outline-thick relative max-w-md w-full mx-4">
            <h3 className="gold-text text-lg font-medium uppercase text-center mb-4">
              Подтверждение
            </h3>
            <p className="text-white/80 text-sm text-center mb-2">
              Телепортироваться в локацию
            </p>
            <p className="text-white text-base text-center font-medium mb-2">
              {confirming.to_location_name}
            </p>
            <p className="text-white/60 text-sm text-center mb-4">
              Стоимость: <span className="gold-text font-medium">{confirming.cost_gold} зол.</span>
            </p>

            {executeError && (
              <p className="text-site-red text-sm text-center mb-3">{executeError}</p>
            )}

            <div className="flex flex-col sm:flex-row gap-2 justify-center">
              <button
                onClick={() => setConfirming(null)}
                disabled={executing}
                className="
                  flex-1 px-4 py-2 rounded-card text-sm font-medium uppercase
                  border border-white/30 text-white/80
                  hover:bg-white/10 transition-all duration-200
                  disabled:opacity-50 disabled:cursor-not-allowed
                "
              >
                Отмена
              </button>
              <button
                onClick={handleExecute}
                disabled={executing}
                className="
                  flex-1 px-4 py-2 rounded-card text-sm font-medium uppercase
                  border border-gold/50 bg-gold/10 text-gold
                  hover:bg-gold/20 hover:border-gold/80
                  transition-all duration-200
                  disabled:opacity-50 disabled:cursor-not-allowed
                "
              >
                {executing ? 'Телепортация...' : 'Подтвердить'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default TeleportMenu;
