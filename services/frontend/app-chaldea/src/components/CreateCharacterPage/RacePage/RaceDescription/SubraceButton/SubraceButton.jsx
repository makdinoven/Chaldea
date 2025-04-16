import styles from './SubraceButton.module.scss';

export default function SubraceButton({
                                          text,
                                          index,
                                          isActive,
                                          setCurrentIndex,
                                      }) {
    function handleClick() {
        setCurrentIndex(index);
    }

    return (
        <button
            onClick={handleClick}
            className={isActive ? styles.active : styles.inactive}
        >
            {text}
        </button>
    );
}
