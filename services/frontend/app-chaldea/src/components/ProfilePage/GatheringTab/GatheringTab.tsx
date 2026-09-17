/**
 * "Сбор" profile tab — shows the character's gathering skills
 * (mining / herbalism / woodcutting / foraging) with rank, XP progress, and bonuses.
 * Restyled per Claude Design mock (FEAT-151), moved into a single PanelShell
 * (FEAT-166); data/redux flow unchanged.
 *
 * Visible read-only on other players' profiles per FEAT-128 §2.7 #4.
 * No interactive controls — rank-up is automatic via XP gain.
 */
import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { Pickaxe } from 'lucide-react';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  loadGatheringSkills,
  selectGatheringSkills,
  selectGatheringIsLoadingSkills,
  selectGatheringError,
  clearGatheringError,
} from '../../../redux/slices/gatheringSlice';
import GatheringSkillCard from './GatheringSkillCard';
import PanelShell, { PANEL_DESKTOP_HEIGHT_CLASS } from '../PanelShell';
import EmptyState from '../shared/EmptyState';
import LoadingState from '../shared/LoadingState';
import PanelCounter from '../shared/PanelCounter';

interface GatheringTabProps {
  characterId: number;
  /**
   * Whether the profile being viewed belongs to the logged-in user.
   * Currently the tab is fully read-only, so this only affects the
   * empty-state copy. Defaults to `true`.
   */
  isOwnProfile?: boolean;
}

const GatheringTab = ({ characterId, isOwnProfile = true }: GatheringTabProps) => {
  const dispatch = useAppDispatch();
  const skills = useAppSelector(selectGatheringSkills);
  const loading = useAppSelector(selectGatheringIsLoadingSkills);
  const error = useAppSelector(selectGatheringError);
  // Sticky local flag — the slice-level error gets cleared after the toast fires
  // so we cannot rely on it for an inline empty-state message. This survives
  // until the next successful load (see the success effect below).
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    setLoadFailed(false);
    dispatch(loadGatheringSkills(characterId))
      .unwrap()
      .catch(() => {
        // The thunk already pushed a Russian message into state.error which
        // the effect below toasts. We just remember that the call failed so
        // the empty state doesn't lie about why no skills are shown.
        setLoadFailed(true);
      });
  }, [dispatch, characterId]);

  // Display load errors via toast and clear from slice so they don't linger.
  useEffect(() => {
    if (error) {
      toast.error(error);
      dispatch(clearGatheringError());
    }
  }, [error, dispatch]);

  const retryLoad = () => {
    setLoadFailed(false);
    dispatch(loadGatheringSkills(characterId))
      .unwrap()
      .catch(() => setLoadFailed(true));
  };

  const renderContent = () => {
    if (loading && skills.length === 0) {
      return <LoadingState label="Загрузка..." />;
    }

    if (!loading && skills.length === 0) {
      return (
        <EmptyState
          icon={<Pickaxe size={32} strokeWidth={1.5} className="text-white/20" />}
          message={
            loadFailed
              ? 'Не удалось загрузить навыки сбора.'
              : isOwnProfile
                ? 'Навыки сбора ещё не получены.'
                : 'У игрока пока нет навыков сбора.'
          }
          action={
            loadFailed ? (
              <button
                type="button"
                onClick={retryLoad}
                className="text-sm text-site-blue hover:text-white transition-colors duration-200 ease-site"
              >
                Попробовать снова
              </button>
            ) : undefined
          }
        />
      );
    }

    return (
      <motion.div
        initial="hidden"
        animate="visible"
        variants={{
          hidden: {},
          visible: { transition: { staggerChildren: 0.05 } },
        }}
        className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"
      >
        {skills.map((skill) => (
          <motion.div
            key={skill.skill_id}
            variants={{
              hidden: { opacity: 0, y: 10 },
              visible: { opacity: 1, y: 0 },
            }}
          >
            <GatheringSkillCard skill={skill} />
          </motion.div>
        ))}
      </motion.div>
    );
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
    >
      <PanelShell
        title="Навыки сбора"
        icon={<Pickaxe size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
        headerExtra={
          skills.length > 0 ? <PanelCounter>{skills.length}</PanelCounter> : undefined
        }
        className={PANEL_DESKTOP_HEIGHT_CLASS}
      >
        {renderContent()}
      </PanelShell>
    </motion.div>
  );
};

export default GatheringTab;
