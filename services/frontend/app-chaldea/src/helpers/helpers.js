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
