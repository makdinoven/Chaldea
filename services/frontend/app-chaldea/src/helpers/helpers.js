import { CHARACTER_RESOURCES, SKILLS_SIGNS } from "./commonConstants";

export const translateCharacterResource = (key) => {
  return CHARACTER_RESOURCES[key] || key;
};

export const translateSkillSign = (key) => {
  return SKILLS_SIGNS[key] || key;
};

export const formatTime = (totalSeconds) => {
  const hours = String(Math.floor(totalSeconds / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((totalSeconds % 3600) / 60)).padStart(
    2,
    "0",
  );
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${hours}:${minutes}:${seconds}`;
};

export const formatDateTime = (datetimeStr) => {
  const safeUtcStr = datetimeStr.split(".")[0] + "Z";
  const dateObj = new Date(safeUtcStr);

  const hours = String(dateObj.getHours()).padStart(2, "0");
  const minutes = String(dateObj.getMinutes()).padStart(2, "0");
  const day = String(dateObj.getDate()).padStart(2, "0");
  const month = String(dateObj.getMonth() + 1).padStart(2, "0");
  const year = dateObj.getFullYear();

  return `${day}.${month}.${year} ${hours}:${minutes}`;
};
