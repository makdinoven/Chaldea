import axios from 'axios';

/**
 * Framing of player pictures (photo-service `avatar_crop`): the avatar is a
 * square cut from a picture that is kept whole, so the frame can be changed
 * later. The framed file is named `<whole picture>.crop-<random>.<ext>`.
 */

/** A square in the source picture's pixels. */
export interface CropArea {
  x: number;
  y: number;
  width: number;
  height: number;
}

const CROP_MARK = '.crop-';

/** The whole picture a framed avatar was cut from (or the URL itself). */
export const originalOf = (url: string): string => {
  const at = url.lastIndexOf(CROP_MARK);
  return at === -1 ? url : url.slice(0, at);
};

/**
 * Why a picked file cannot be a picture, or null. "GIFs" saved from Tenor,
 * Discord and the like are often MP4 videos named `*.gif.mp4` — the browser
 * cannot draw them and photo-service rejects them.
 */
export const notPictureMessage = (file: File): string | null => {
  if (file.type.startsWith('image/')) return null;
  return file.type.startsWith('video/')
    ? 'Это видео, а не гифка — такие часто скачиваются с Tenor и Discord. Сохраните анимацию в формате GIF и загрузите снова'
    : 'Это не картинка. Подходят JPEG, PNG, WebP и GIF';
};

/** Appends the crop square to a form, as the photo-service fields want it. */
export const appendCrop = (form: FormData, crop?: CropArea | null) => {
  if (!crop) return;
  form.append('crop_x', String(crop.x));
  form.append('crop_y', String(crop.y));
  form.append('crop_width', String(crop.width));
  form.append('crop_height', String(crop.height));
};

const cropForm = (fields: Record<string, string>, crop: CropArea) => {
  const form = new FormData();
  Object.entries(fields).forEach(([k, v]) => form.append(k, v));
  appendCrop(form, crop);
  return form;
};

export const recropUserAvatar = async (userId: number, crop: CropArea) =>
  (await axios.post<{ avatar_url: string }>('/photo/recrop_user_avatar', cropForm({ user_id: String(userId) }, crop)))
    .data.avatar_url;

export const recropCharacterAvatar = async (characterId: number, crop: CropArea) =>
  (await axios.post<{ avatar_url: string }>(
    '/photo/recrop_character_avatar', cropForm({ character_id: String(characterId) }, crop),
  )).data.avatar_url;

/** A new frame for a mini-role or character-request picture; the caller saves the URL. */
export const recropImage = async (imageUrl: string, crop: CropArea) =>
  (await axios.post<{ image_url: string }>('/photo/recrop_image', cropForm({ image_url: imageUrl }, crop)))
    .data.image_url;
