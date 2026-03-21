import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../../api/api';

/* ── Types ── */

interface DialogueOption {
  id: number;
  text: string;
  next_node_id: number | null;
}

interface DialogueNode {
  id: number;
  npc_text: string;
  is_end: boolean;
  action_type: string | null;
  options: DialogueOption[];
}

interface NpcDialogueModalProps {
  npcId: number;
  npcName: string;
  npcAvatar: string | null;
  onClose: () => void;
}

/* ── Component ── */

const NpcDialogueModal = ({ npcId, npcName, npcAvatar, onClose }: NpcDialogueModalProps) => {
  const [currentNode, setCurrentNode] = useState<DialogueNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [choosing, setChoosing] = useState(false);
  const [fadeIn, setFadeIn] = useState(false);

  const startDialogue = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get<DialogueNode>(`${BASE_URL}/locations/npcs/${npcId}/dialogue`);
      setCurrentNode(res.data);
      // Trigger fade-in animation
      setTimeout(() => setFadeIn(true), 50);
    } catch {
      toast.error('Не удалось начать диалог');
      onClose();
    } finally {
      setLoading(false);
    }
  }, [npcId, onClose]);

  useEffect(() => {
    startDialogue();
  }, [startDialogue]);

  const handleChooseOption = async (option: DialogueOption) => {
    if (!currentNode || choosing) return;
    setChoosing(true);
    setFadeIn(false);

    try {
      const res = await axios.post<DialogueNode>(
        `${BASE_URL}/locations/npcs/${npcId}/dialogue/${currentNode.id}/choose`,
        { option_id: option.id },
      );
      // Small delay for smooth transition
      setTimeout(() => {
        setCurrentNode(res.data);
        setFadeIn(true);
        setChoosing(false);
      }, 200);
    } catch {
      toast.error('Ошибка при выборе ответа');
      setFadeIn(true);
      setChoosing(false);
    }
  };

  const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose();
  };

  const isEnd = currentNode?.is_end || (currentNode && currentNode.options.length === 0);

  return (
    <div className="modal-overlay" onClick={handleOverlayClick}>
      <div className="relative flex flex-col w-full max-w-2xl mx-4 max-h-[90vh]">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute -top-2 -right-2 sm:top-0 sm:right-0 z-20 w-8 h-8 flex items-center justify-center rounded-full bg-black/60 text-white/50 hover:text-white transition-colors"
          aria-label="Закрыть"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
          </div>
        ) : currentNode ? (
          <div className="flex flex-col gap-4">
            {/* NPC header */}
            <div className="flex items-center gap-3 px-2">
              <div className="gold-outline relative w-14 h-14 sm:w-16 sm:h-16 rounded-full overflow-hidden bg-black/40 shrink-0">
                {npcAvatar ? (
                  <img src={npcAvatar} alt={npcName} className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-white/20">
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                  </div>
                )}
              </div>
              <h2 className="gold-text text-lg sm:text-xl font-medium uppercase tracking-wide">
                {npcName}
              </h2>
            </div>

            {/* NPC speech bubble */}
            <div
              className={`
                relative bg-black/60 rounded-card p-4 sm:p-6
                border-l-4 border-l-gold-dark
                transition-opacity duration-300 ease-in-out
                ${fadeIn ? 'opacity-100' : 'opacity-0'}
              `}
            >
              {/* Decorative quote icon */}
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="w-6 h-6 text-gold/30 absolute top-3 right-3 hidden sm:block"
                fill="currentColor"
                viewBox="0 0 24 24"
              >
                <path d="M14.017 21v-7.391c0-5.704 3.731-9.57 8.983-10.609l.995 2.151c-2.432.917-3.995 3.638-3.995 5.849h4v10h-9.983zm-14.017 0v-7.391c0-5.704 3.748-9.57 9-10.609l.996 2.151c-2.433.917-3.996 3.638-3.996 5.849h3.983v10h-9.983z" />
              </svg>
              <p className="text-white/90 text-sm sm:text-base leading-relaxed whitespace-pre-wrap">
                {currentNode.npc_text}
              </p>
            </div>

            {/* Player options */}
            <div
              className={`
                flex flex-col gap-2 transition-opacity duration-300 ease-in-out delay-100
                ${fadeIn ? 'opacity-100' : 'opacity-0'}
              `}
            >
              {isEnd ? (
                <button
                  onClick={onClose}
                  className="
                    w-full text-left px-4 py-3 rounded-card
                    border border-gold/40 bg-black/40
                    text-gold text-sm sm:text-base font-medium
                    hover:bg-gold/10 hover:border-gold/70
                    transition-all duration-200
                  "
                >
                  Завершить разговор
                </button>
              ) : (
                currentNode.options.map((option) => (
                  <button
                    key={option.id}
                    onClick={() => handleChooseOption(option)}
                    disabled={choosing}
                    className="
                      w-full text-left px-4 py-3 rounded-card
                      border border-white/20 bg-black/30
                      text-white/80 text-sm sm:text-base
                      hover:bg-white/10 hover:border-white/40 hover:text-white
                      disabled:opacity-50 disabled:cursor-not-allowed
                      transition-all duration-200
                    "
                  >
                    {option.text}
                  </button>
                ))
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default NpcDialogueModal;
