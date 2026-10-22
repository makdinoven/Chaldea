import { useState, useRef, useEffect, useCallback } from 'react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  updateProfileSettings,
  updateUsername,
  uploadProfileBackground,
  deleteProfileBackground,
  selectSettingsUpdating,
  type UserProfile,
  type ProfileStyleSettings,
} from '../../redux/slices/userProfileSlice';
import { selectSiteBackgroundUrl, setSiteBackgroundUrl } from '../../redux/slices/userSlice';
import ColorPicker from '../common/ColorPicker';
import BackgroundPositionPicker from '../UserProfilePage/BackgroundPositionPicker';
import FramePicker from '../UserProfilePage/FramePicker';
import BackgroundPicker from '../UserProfilePage/BackgroundPicker';
import { buildColorEffectStyle, buildNicknameTextShadow, SLIDER_DEFAULTS } from '../UserProfilePage/profileStyle';
import { SettingsCard } from './SettingsControls';

const NICKNAME_FONT_OPTIONS = [
  { value: '', label: 'По умолчанию' },
  { value: 'Georgia, serif', label: 'Georgia' },
  { value: 'Impact, sans-serif', label: 'Impact' },
  { value: '"Courier New", monospace', label: 'Courier New' },
  { value: '"Trebuchet MS", sans-serif', label: 'Trebuchet MS' },
  { value: 'Palatino, serif', label: 'Palatino' },
  { value: 'Copperplate, fantasy', label: 'Copperplate' },
] as const;

const MAX_FILE_SIZE = 15 * 1024 * 1024;
const MAX_STATUS_LENGTH = 100;
const SITE_BG_URL_PATTERN = /^https?:\/\//i;

/* ── Slider infrastructure ── */

interface SliderConfig {
  key: keyof ProfileStyleSettings;
  label: string;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
}

const makeSliders = (prefix: 'post_color' | 'bg_color'): SliderConfig[] => [
  { key: `${prefix}_opacity`, label: 'Прозрачность', min: 0, max: 1, step: 0.05, format: (v) => `${Math.round(v * 100)}%` },
  { key: `${prefix}_blur`, label: 'Размытие', min: 0, max: 20, step: 1, format: (v) => `${v}px` },
  { key: `${prefix}_glow`, label: 'Свечение', min: 0, max: 20, step: 1, format: (v) => `${v}px` },
  { key: `${prefix}_saturation`, label: 'Насыщенность', min: 0, max: 2, step: 0.05, format: (v) => `${Math.round(v * 100)}%` },
];

const POST_COLOR_SLIDERS = makeSliders('post_color');
const BG_COLOR_SLIDERS = makeSliders('bg_color');

/** A single range slider row */
const SettingsSlider = ({
  config,
  value,
  onChange,
}: {
  config: SliderConfig;
  value: number;
  onChange: (key: keyof ProfileStyleSettings, val: number) => void;
}) => (
  <div className="flex items-center gap-2 sm:gap-3">
    <span className="text-white/60 text-xs w-24 sm:w-32 shrink-0">{config.label}</span>
    <input
      type="range"
      min={config.min}
      max={config.max}
      step={config.step}
      value={value}
      onChange={(e) => onChange(config.key, parseFloat(e.target.value))}
      className="flex-1 h-1.5 appearance-none rounded-full bg-white/10 cursor-pointer
        [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
        [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-site-blue [&::-webkit-slider-thumb]:shadow-md
        [&::-webkit-slider-thumb]:cursor-pointer
        [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:rounded-full
        [&::-moz-range-thumb]:bg-site-blue [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:cursor-pointer"
    />
    <span className="text-white/40 text-xs w-12 text-right tabular-nums">{config.format(value)}</span>
  </div>
);

/** Renders the 4 effect sliders for a color section with a live preview swatch */
const SliderGroup = ({
  sliders,
  color,
  prefix,
  styleSettings,
  onSliderChange,
}: {
  sliders: SliderConfig[];
  color: string;
  prefix: 'post_color' | 'bg_color';
  styleSettings: ProfileStyleSettings;
  onSliderChange: (key: keyof ProfileStyleSettings, val: number) => void;
}) => {
  const previewStyle = buildColorEffectStyle(color || '#232329', prefix, styleSettings);

  return (
    <div className="flex flex-col gap-2 mt-3">
      {sliders.map((s) => {
        const val = (styleSettings[s.key] as number | undefined) ?? (SLIDER_DEFAULTS[s.key as string] ?? 0);
        return (
          <SettingsSlider
            key={s.key}
            config={s}
            value={val}
            onChange={onSliderChange}
          />
        );
      })}
      {/* Live preview swatch */}
      {color && (
        <div className="mt-2 flex items-center gap-3">
          <span className="text-white/40 text-xs">Превью:</span>
          <div
            className="w-16 h-10 rounded-lg border border-white/10"
            style={previewStyle}
          />
        </div>
      )}
    </div>
  );
};

/* ── Main component ── */

interface ProfileAppearanceTabProps {
  profile: UserProfile;
}

/**
 * «Профиль и внешний вид»: everything the profile gear used to open, plus the
 * site background, which now lives in the account instead of the browser.
 * The form is filled once; later reloads of the profile (after an upload or a
 * nickname change) must not throw away edits that are not saved yet.
 */
const ProfileAppearanceTab = ({ profile }: ProfileAppearanceTabProps) => {
  const dispatch = useAppDispatch();
  const settingsUpdating = useAppSelector(selectSettingsUpdating);
  const accountBg = useAppSelector(selectSiteBackgroundUrl);

  const [bgColor, setBgColor] = useState(profile.profile_bg_color ?? '');
  const [nicknameColor, setNicknameColor] = useState(profile.nickname_color ?? '');
  const [statusText, setStatusText] = useState(profile.status_text ?? '');
  const [bgPosition, setBgPosition] = useState(profile.profile_bg_position ?? '50% 50%');
  const [newUsername, setNewUsername] = useState(profile.username);
  const [usernameError, setUsernameError] = useState<string | null>(null);
  const [postColor, setPostColor] = useState(profile.post_color ?? '');
  const [siteBgUrl, setSiteBgUrl] = useState(() => accountBg ?? localStorage.getItem('site_bg_url') ?? '');

  // Nickname gradient state (Task 7)
  const pss = profile.profile_style_settings;
  const [nicknameColor2, setNicknameColor2] = useState(pss?.nickname_color_2 ?? '');
  const [gradientAngle, setGradientAngle] = useState(pss?.nickname_gradient_angle ?? 90);
  const [brightness, setBrightness] = useState(pss?.nickname_brightness ?? 1.0);
  const [contrast, setContrast] = useState(pss?.nickname_contrast ?? 1.0);
  const [shimmer, setShimmer] = useState(pss?.nickname_shimmer ?? false);
  const [nicknameGlow, setNicknameGlow] = useState(pss?.nickname_glow ?? 0);
  const [nicknamePulse, setNicknamePulse] = useState(pss?.nickname_pulse ?? false);
  const [nicknameTextShadow, setNicknameTextShadow] = useState(pss?.nickname_text_shadow ?? 0);
  const [nicknameFont, setNicknameFont] = useState(pss?.nickname_font ?? '');

  // Slider values for all 3 color sections (Task 6)
  const [styleSettings, setStyleSettings] = useState<ProfileStyleSettings>(
    profile.profile_style_settings ?? {},
  );

  const bgFileInputRef = useRef<HTMLInputElement>(null);

  const handleSliderChange = useCallback((key: keyof ProfileStyleSettings, value: number) => {
    setStyleSettings((prev) => ({ ...prev, [key]: value }));
  }, []);

  // A newly uploaded profile background starts from its own saved position.
  useEffect(() => {
    setBgPosition(profile.profile_bg_position ?? '50% 50%');
  }, [profile.profile_bg_image, profile.profile_bg_position]);

  const handleSave = async () => {
    const trimmedSiteBg = siteBgUrl.trim();
    if (trimmedSiteBg && !SITE_BG_URL_PATTERN.test(trimmedSiteBg)) {
      toast.error('Ссылка на фон сайта должна начинаться с http:// или https://');
      return;
    }
    try {
      // Merge all style settings: slider values + nickname gradient values
      const mergedPss: ProfileStyleSettings = {
        ...styleSettings,
        nickname_color_2: nicknameColor2 || undefined,
        nickname_gradient_angle: gradientAngle,
        nickname_brightness: brightness,
        nickname_contrast: contrast,
        nickname_shimmer: shimmer,
        nickname_glow: nicknameGlow,
        nickname_pulse: nicknamePulse,
        nickname_text_shadow: nicknameTextShadow,
        nickname_font: nicknameFont || undefined,
      };

      await dispatch(
        updateProfileSettings({
          userId: profile.id,
          settings: {
            profile_bg_color: bgColor || null,
            nickname_color: nicknameColor || null,
            status_text: statusText || null,
            profile_bg_position: profile.profile_bg_image ? bgPosition : null,
            post_color: postColor || null,
            profile_style_settings: Object.keys(mergedPss).length > 0 ? mergedPss : null,
            site_background_url: trimmedSiteBg || null,
          },
        }),
      ).unwrap();

      // The account holds the background now; the old per-browser copy goes.
      dispatch(setSiteBackgroundUrl(trimmedSiteBg || null));
      localStorage.removeItem('site_bg_url');

      toast.success('Настройки сохранены');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось сохранить настройки');
    }
  };

  const handleUsernameChange = async () => {
    const trimmed = newUsername.trim();
    if (!trimmed) {
      setUsernameError('Никнейм не может быть пустым');
      return;
    }
    if (trimmed === profile.username) {
      setUsernameError('Никнейм не изменился');
      return;
    }
    setUsernameError(null);
    try {
      await dispatch(updateUsername({ userId: profile.id, username: trimmed })).unwrap();
      toast.success('Никнейм изменён');
    } catch (err) {
      const errorMsg = typeof err === 'string' ? err : 'Не удалось изменить никнейм';
      setUsernameError(errorMsg);
      toast.error(errorMsg);
    }
  };

  const handleBgUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';

    if (file.size > MAX_FILE_SIZE) {
      toast.error('Файл слишком большой. Максимальный размер: 15 МБ');
      return;
    }

    try {
      await dispatch(uploadProfileBackground({ userId: profile.id, file })).unwrap();
      toast.success('Фон профиля обновлён');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось загрузить фон');
    }
  };

  const handleBgDelete = async () => {
    try {
      await dispatch(deleteProfileBackground(profile.id)).unwrap();
      toast.success('Фон профиля удалён');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось удалить фон');
    }
  };

  return (
    <div className="flex flex-col gap-4 sm:gap-6">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 sm:gap-6 items-start">
        <div className="flex flex-col gap-4 sm:gap-6 min-w-0">
          <SettingsCard title="Профиль">
            <div>
              <h3 className="text-white text-sm font-medium uppercase tracking-wider mb-3">
                Никнейм
              </h3>
              <div>
                <input
                  type="text"
                  value={newUsername}
                  onChange={(e) => {
                    setNewUsername(e.target.value);
                    setUsernameError(null);
                  }}
                  className="h-10 w-full bg-white/5 text-white text-base outline-none rounded px-2 focus:bg-white/10 transition-colors placeholder:text-white/40 mb-2"
                  style={{
                    borderWidth: '0 0 2px 0',
                    borderStyle: 'solid',
                    borderColor: 'rgba(255, 255, 255, 0.5)',
                  }}
                  onFocus={(e) => {
                    e.currentTarget.style.borderColor = '#76a6bd';
                  }}
                  onBlur={(e) => {
                    e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.5)';
                  }}
                  placeholder="Введите никнейм"
                  maxLength={32}
                />
                {usernameError && (
                  <p className="text-site-red text-xs mt-1">{usernameError}</p>
                )}
                <button
                  type="button"
                  onClick={handleUsernameChange}
                  className="btn-line text-sm w-full mt-2"
                  disabled={settingsUpdating}
                >
                  Изменить
                </button>
              </div>
            </div>

            <div>
              <h3 className="text-white text-sm font-medium uppercase tracking-wider mb-3">
                Статус
              </h3>
              <input
                type="text"
                value={statusText}
                onChange={(e) => {
                  if (e.target.value.length <= MAX_STATUS_LENGTH) {
                    setStatusText(e.target.value);
                  }
                }}
                className="input-underline w-full"
                placeholder="Введите статус / девиз"
                maxLength={MAX_STATUS_LENGTH}
              />
              <p className="text-white/30 text-xs mt-1 text-right">
                {statusText.length}/{MAX_STATUS_LENGTH}
              </p>
            </div>
          </SettingsCard>

          <SettingsCard title="Оформление профиля">
            <div>
              <h3 className="text-white text-sm font-medium uppercase tracking-wider mb-3">
                Фон профиля
              </h3>
              <input
                ref={bgFileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={handleBgUpload}
              />
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => bgFileInputRef.current?.click()}
                  className="btn-blue text-sm"
                  disabled={settingsUpdating}
                >
                  Загрузить фон
                </button>
                {profile.profile_bg_image && (
                  <button
                    type="button"
                    onClick={handleBgDelete}
                    className="text-site-red text-sm hover:text-white transition-colors"
                    disabled={settingsUpdating}
                  >
                    Удалить фон
                  </button>
                )}
              </div>
              {profile.profile_bg_image && (
                <div className="mt-3">
                  <BackgroundPositionPicker
                    imageUrl={profile.profile_bg_image}
                    position={bgPosition}
                    onChange={setBgPosition}
                  />
                </div>
              )}
            </div>

            <div>
              <h3 className="text-white text-sm font-medium uppercase tracking-wider mb-3">
                Цвет подложки
              </h3>
              <ColorPicker color={bgColor || '#232329'} onChange={setBgColor} />
              <button
                type="button"
                onClick={() => setBgColor('')}
                className="mt-2 text-white/40 text-xs hover:text-site-blue transition-colors"
              >
                Сбросить
              </button>
              <SliderGroup
                sliders={BG_COLOR_SLIDERS}
                color={bgColor}
                prefix="bg_color"
                styleSettings={styleSettings}
                onSliderChange={handleSliderChange}
              />
            </div>

            <div>
              <h3 className="text-white text-sm font-medium uppercase tracking-wider mb-3">
                Цвет постов
              </h3>
              <ColorPicker color={postColor || '#232329'} onChange={setPostColor} />
              <button
                type="button"
                onClick={() => setPostColor('')}
                className="mt-2 text-white/40 text-xs hover:text-site-blue transition-colors"
              >
                Сбросить
              </button>
              <SliderGroup
                sliders={POST_COLOR_SLIDERS}
                color={postColor}
                prefix="post_color"
                styleSettings={styleSettings}
                onSliderChange={handleSliderChange}
              />
            </div>
          </SettingsCard>
        </div>

        <div className="flex flex-col gap-4 sm:gap-6 min-w-0">
          <SettingsCard title="Никнейм">
            <div>
              <h3 className="text-white text-sm font-medium uppercase tracking-wider mb-3">
                Цвет никнейма
              </h3>

              {/* Live preview */}
              <div className="mb-4 p-3 rounded-card bg-black/30 flex items-center justify-center min-h-[48px] overflow-hidden">
                <span
                  className={`text-2xl font-semibold uppercase ${
                    shimmer && nicknameColor ? 'nickname-shimmer' : ''
                  } ${nicknamePulse && !shimmer ? 'nickname-pulse' : ''}`}
                  style={(() => {
                    const style: React.CSSProperties = {};
                    if (nicknameColor) {
                      style.color = nicknameColor;
                      style.WebkitTextFillColor = nicknameColor;
                      style.backgroundImage = 'none';
                    } else {
                      style.background = 'linear-gradient(180deg, #fff9b8 0%, #bcab4c 100%)';
                      style.WebkitBackgroundClip = 'text';
                      style.WebkitTextFillColor = 'transparent';
                      (style as Record<string, unknown>).backgroundClip = 'text';
                    }
                    if (brightness !== 1 || contrast !== 1) {
                      style.filter = `brightness(${brightness}) contrast(${contrast})`;
                    }
                    const ts = buildNicknameTextShadow(nicknameColor, nicknameGlow, 0);
                    if (ts) style.textShadow = ts;
                    if (nicknameFont) style.fontFamily = nicknameFont;
                    return style;
                  })()}
                >
                  {profile.username}
                </span>
              </div>

              {/* Single color picker */}
              <div className="mb-4">
                <ColorPicker color={nicknameColor || '#f0d95c'} onChange={setNicknameColor} />
              </div>

              {/* Brightness slider */}
              <div className="mb-3">
                <div className="flex items-center justify-between mb-1">
                  <label className="text-white/60 text-xs">Яркость</label>
                  <span className="text-white/40 text-xs">{brightness.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min={0.5}
                  max={2.0}
                  step={0.05}
                  value={brightness}
                  onChange={(e) => setBrightness(Number(e.target.value))}
                  className="w-full h-1.5 rounded-full appearance-none bg-white/10 accent-gold cursor-pointer
                    [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-gold"
                />
              </div>

              {/* Contrast slider */}
              <div className="mb-3">
                <div className="flex items-center justify-between mb-1">
                  <label className="text-white/60 text-xs">Контраст</label>
                  <span className="text-white/40 text-xs">{contrast.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min={0.5}
                  max={2.0}
                  step={0.05}
                  value={contrast}
                  onChange={(e) => setContrast(Number(e.target.value))}
                  className="w-full h-1.5 rounded-full appearance-none bg-white/10 accent-gold cursor-pointer
                    [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-gold"
                />
              </div>

              {/* Shimmer toggle */}
              <label className="flex items-center gap-3 cursor-pointer mb-2">
                <div className="relative">
                  <input
                    type="checkbox"
                    checked={shimmer}
                    onChange={(e) => {
                      setShimmer(e.target.checked);
                      if (e.target.checked) setNicknamePulse(false);
                    }}
                    className="sr-only peer"
                  />
                  <div className="w-10 h-5 rounded-full bg-white/10 peer-checked:bg-site-blue/50 transition-colors" />
                  <div className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform peer-checked:translate-x-5" />
                </div>
                <span className="text-white/60 text-xs">Эффект блеска</span>
              </label>

              {/* Glow slider */}
              <div className="mb-3">
                <div className="flex items-center justify-between mb-1">
                  <label className="text-white/60 text-xs">Свечение</label>
                  <span className="text-white/40 text-xs">{nicknameGlow}px</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={20}
                  step={1}
                  value={nicknameGlow}
                  onChange={(e) => setNicknameGlow(Number(e.target.value))}
                  className="w-full h-1.5 rounded-full appearance-none bg-white/10 accent-gold cursor-pointer
                    [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-gold"
                />
              </div>

              {/* Pulse toggle */}
              <label className="flex items-center gap-3 cursor-pointer mb-3">
                <div className="relative">
                  <input
                    type="checkbox"
                    checked={nicknamePulse}
                    onChange={(e) => {
                      setNicknamePulse(e.target.checked);
                      if (e.target.checked) setShimmer(false);
                    }}
                    className="sr-only peer"
                  />
                  <div className="w-10 h-5 rounded-full bg-white/10 peer-checked:bg-site-blue/50 transition-colors" />
                  <div className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform peer-checked:translate-x-5" />
                </div>
                <span className="text-white/60 text-xs">Пульсация</span>
              </label>

              {/* Font selector */}
              <div className="mb-3">
                <label className="text-white/60 text-xs block mb-1">Шрифт</label>
                <select
                  value={nicknameFont}
                  onChange={(e) => setNicknameFont(e.target.value)}
                  className="w-full h-10 bg-white/5 text-white text-sm rounded px-2 cursor-pointer
                    outline-none focus:bg-white/10 transition-colors appearance-none
                    [&>option]:bg-[#232329] [&>option]:text-white"
                  style={{
                    borderWidth: '0 0 2px 0',
                    borderStyle: 'solid',
                    borderColor: 'rgba(255, 255, 255, 0.5)',
                  }}
                >
                  {NICKNAME_FONT_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Reset buttons */}
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setNicknameColor('');
                    setBrightness(1.0);
                    setContrast(1.0);
                    setShimmer(false);
                    setNicknameGlow(0);
                    setNicknamePulse(false);
                    setNicknameFont('');
                  }}
                  className="text-white/40 text-xs hover:text-site-blue transition-colors"
                >
                  Сбросить всё
                </button>
              </div>
            </div>
          </SettingsCard>

          <SettingsCard title="Аватар и сообщения">
            <FramePicker avatarUrl={profile.avatar} />

            {/* Section: Chat message background (DB-backed cosmetics) */}
            <BackgroundPicker />
          </SettingsCard>

          <SettingsCard title="Сайт">
            <div>
              <h3 className="text-white text-sm font-medium uppercase tracking-wider mb-3">
                Фон сайта
              </h3>
              <input
                type="url"
                value={siteBgUrl}
                onChange={(e) => setSiteBgUrl(e.target.value)}
                className="input-underline w-full"
                placeholder="https://example.com/image.jpg"
              />
              <p className="text-white/30 text-xs mt-1">
                Ссылка на изображение. Фон хранится в аккаунте и виден на любом устройстве. Оставьте пустым для стандартного фона.
              </p>
              {siteBgUrl.trim() && (
                <button
                  type="button"
                  onClick={() => setSiteBgUrl('')}
                  className="text-site-red text-xs mt-2 hover:text-site-red/80 transition-colors"
                >
                  Сбросить фон
                </button>
              )}
            </div>
          </SettingsCard>
        </div>
      </div>

      {/* Saving stays in reach however far down the page the edit was. */}
      <div className="sticky bottom-3 z-10 flex justify-end">
        <button
          type="button"
          onClick={handleSave}
          className="btn-blue w-full sm:w-auto shadow-card"
          disabled={settingsUpdating}
        >
          {settingsUpdating ? 'Сохранение...' : 'Сохранить изменения'}
        </button>
      </div>
    </div>
  );
};

export default ProfileAppearanceTab;
