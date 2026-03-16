import s from "./CountdownTimer.module.scss";
import { useEffect, useRef, useState } from "react";
import { formatTime } from "../../../../../helpers/helpers";

const CountdownTimer = ({ startMilliseconds, onComplete }) => {
  const [secondsLeft, setSecondsLeft] = useState(
    Math.floor(startMilliseconds / 1000),
  );
  const intervalId = useRef(null);

  useEffect(() => {
    setSecondsLeft(Math.floor(startMilliseconds / 1000));
  }, [startMilliseconds]);

  useEffect(() => {
    intervalId.current = setInterval(() => {
      setSecondsLeft((prev) => {
        if (prev <= 1) {
          clearInterval(intervalId.current);
          intervalId.current = null;
          if (onComplete) onComplete();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (intervalId.current) {
        clearInterval(intervalId.current);
      }
    };
  }, [onComplete]);

  return <span className={s.timer}>{formatTime(secondsLeft)}</span>;
};

export default CountdownTimer;
