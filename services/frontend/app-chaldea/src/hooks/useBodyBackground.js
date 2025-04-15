import {useEffect} from "react";

export function useBodyBackground(imageUrl) {
    useEffect(() => {
        if (imageUrl) {
            const originalBackground = document.body.style.backgroundImage;
            document.body.style.backgroundImage = `url(${imageUrl})`;
            return () => {
                document.body.style.backgroundImage = originalBackground;
            };
        }

    }, [imageUrl]);
}
