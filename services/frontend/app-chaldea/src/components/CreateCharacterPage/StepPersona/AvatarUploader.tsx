import { useState } from 'react';
import { uploadCharacterRequestAvatar } from '../../../api/characterRequests';
import { recropImage } from '../../../api/avatarCrop';
import AvatarEditor from '../../CommonComponents/AvatarEditor/AvatarEditor';

/**
 * FEAT-154 (task #18) — avatar upload for a character that does not exist yet
 * (rule 21, D4).
 *
 * The old form sent the literal `avatar: 'string'`; here the file really goes
 * to `POST /photo/upload_character_request_avatar`, which writes no DB row and
 * answers with a permanent S3 URL that the application then carries.
 *
 * The player frames the portrait in `AvatarEditor` (the whole picture is kept,
 * so the frame can be changed before and after approval).
 *
 * **The field is optional on purpose.** If the upload fails the player sees a
 * Russian message and can still submit — on approval the subrace artwork is
 * used instead. Nothing here ever blocks the wizard.
 */

/** Mirrors the backend cap (`photo-service/utils.py`); AvatarEditor checks it. */
const MAX_AVATAR_LABEL = '15 МБ';

interface AvatarUploaderProps {
  /** The uploaded S3 URL, or `null` while nothing has been uploaded. */
  value: string | null;
  onChange: (avatarUrl: string | null) => void;
  /** Subrace artwork — what the character will get if no avatar is uploaded. */
  fallbackImage?: string | null;
  characterName?: string;
}

const AvatarUploader = ({
  value,
  onChange,
  fallbackImage,
  characterName,
}: AvatarUploaderProps) => {
  const [editing, setEditing] = useState(false);
  const shown = value ?? fallbackImage ?? null;

  return (
    <div className="flex flex-col items-center gap-3 w-full">
      <button
        type="button"
        onClick={() => setEditing(true)}
        aria-label="Загрузить портрет персонажа"
        className="hover-gold-overlay w-[160px] h-[160px] sm:w-[200px] sm:h-[200px] rounded-card
                   gold-outline bg-white/5"
      >
        {shown ? (
          <img src={shown} alt="" className="w-full h-full object-cover" />
        ) : (
          <span className="w-full h-full flex items-center justify-center px-3 text-center text-white/40 text-xs">
            Нажмите, чтобы выбрать портрет
          </span>
        )}

        {characterName && (
          <span className="absolute bottom-0 left-0 w-full h-[60px] flex items-end justify-center pb-2 rounded-b-card bg-gradient-to-t from-black/90 to-transparent">
            <span className="gold-text text-xs sm:text-sm font-medium uppercase text-center px-2 truncate max-w-full">
              {characterName}
            </span>
          </span>
        )}
      </button>

      <div className="flex flex-wrap items-center justify-center gap-3">
        <button type="button" className="btn-line text-sm w-auto px-5" onClick={() => setEditing(true)}>
          {value ? 'Изменить портрет' : 'Загрузить портрет'}
        </button>
        {value && (
          <button type="button" className="site-link text-sm" onClick={() => onChange(null)}>
            Убрать
          </button>
        )}
      </div>

      <p className="field-hint text-left max-w-[260px]">
        Портрет необязателен. Без него в паспорт попадёт изображение вашей подрасы.
        Не больше {MAX_AVATAR_LABEL}.
      </p>

      {editing && (
        <AvatarEditor
          title="Портрет персонажа"
          currentUrl={value}
          onClose={() => setEditing(false)}
          onUpload={async (file, crop) => onChange((await uploadCharacterRequestAvatar(file, crop)).avatar_url)}
          onReframe={async (crop) => onChange(await recropImage(value!, crop))}
        />
      )}
    </div>
  );
};

export default AvatarUploader;
