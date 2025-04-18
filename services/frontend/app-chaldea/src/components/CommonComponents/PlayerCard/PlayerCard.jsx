import s from "./PlayerCard.module.scss";

const PlayerCard = ({ title, name, img }) => {
  return (
    <div className={s.card_wrapper}>
      <div style={{ backgroundImage: `url("${img}")` }} className={s.card}>
        <div className={s.names}>
          <span className={s.card_name}>{name ? name : "name"}</span>
          {title && <span className={s.card_title}>{title}</span>}
        </div>
      </div>
    </div>
  );
};

export default PlayerCard;
