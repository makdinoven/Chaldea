import useNavigateTo from '../../../hooks/useNavigateTo';

import styles from './Textarea.module.css';

export default function Textarea({
  id,
  text,
  link,
  isRequired,
  onChange,
  value,
}) {
  const navigateTo = useNavigateTo();

  return (
    <div className={styles.textarea_wrapper}>
      <textarea
        onChange={onChange}
        required={isRequired}
        placeholder={text}
        className={styles.form_textarea}
        value={value}
        name={id}
        id={id}
      ></textarea>
      <a
        className={styles.question_mark}
        onClick={() => navigateTo({ link })}
      ></a>
    </div>
  );
}
