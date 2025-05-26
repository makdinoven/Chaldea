import s from "./CharacterResourcesList.module.scss";
import { translateCharacterResource } from "../../../../../helpers/helpers.js";
import { RESOURCES_COLORS } from "../../../../../helpers/commonConstants.js";

const CharacterResourcesList = ({ resources }) => {
  return (
    <ul className={s.list}>
      {resources.map((res, index) => {
        const [name, data] = Object.entries(res)[0];
        const current = Math.max(0, data.current);
        const percent = Math.min(100, Math.round((current / data.max) * 100));

        return (
          <li key={index} className={s.item}>
            <div className={s.label_row}>
              <span>{translateCharacterResource(name)}</span>
              <span>
                {current}/{data.max}
              </span>
            </div>
            <div className={s.barWrapper}>
              <div
                className={s.bar}
                style={{
                  width: `${percent}%`,
                  backgroundColor: RESOURCES_COLORS[name],
                }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
};

export default CharacterResourcesList;
