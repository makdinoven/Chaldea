import s from "./BackButton.module.scss";
import { useNavigate } from "react-router-dom";

const BackButton = () => {
  const navigate = useNavigate();

  return (
    <button className={s.back_button} onClick={() => navigate(-1)}></button>
  );
};

export default BackButton;
