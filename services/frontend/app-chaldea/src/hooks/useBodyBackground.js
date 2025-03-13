import { useEffect } from "react";

export function useBodyBackground(imageUrl) {
    useEffect(() => {
        // Сохраняем оригинальный background, чтобы можно было вернуть его обратно
        const originalBackground = document.body.style.backgroundImage;

        // Устанавливаем новый background-image
        document.body.style.backgroundImage = `url(${imageUrl})`;

        // Возвращаем оригинальный фон при размонтировании компонента
        return () => {
            document.body.style.backgroundImage = originalBackground;
        };
    }, [imageUrl]); // Хук будет срабатывать при изменении imageUrl
}
