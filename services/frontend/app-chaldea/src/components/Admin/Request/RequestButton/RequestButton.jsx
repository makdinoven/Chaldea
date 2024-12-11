import s from './RequestButton.module.scss';

export default function RequestButton({ text, onClick }) {
  return <button onClick={onClick}>{text}</button>;
}
