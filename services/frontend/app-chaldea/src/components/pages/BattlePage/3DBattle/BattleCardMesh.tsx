import { useRef, useEffect, useState, Suspense } from "react";
import { useFrame } from "@react-three/fiber";
import { Vector3, Group, TextureLoader, LinearFilter, LinearMipmapLinearFilter } from "three";
import type { CharacterData } from "../battleTypes";
import type { Texture } from "three";

interface BattleCardMeshProps {
  position: Vector3;
  character: CharacterData;
  isAlly: boolean;
  isActing: boolean;
  isSelected: boolean;
  onClick?: () => void;
}

// Компонент карточки с уже загруженной текстурой
const CardMeshContent = ({
  character,
  isAlly,
  isActing,
  isSelected,
  position,
  onClick,
  avatarTexture,
}: BattleCardMeshProps & { avatarTexture: Texture | null }) => {
  const groupRef = useRef<Group>(null);
  const glowIntensityRef = useRef(0);
  const materialRef = useRef<any>(null);

  // Анимация свечения при ходе
  useEffect(() => {
    if (isActing) {
      glowIntensityRef.current = 1;
    } else {
      glowIntensityRef.current = 0;
    }
  }, [isActing]);

  // Анимация выдвижения вперед при ходе
  useFrame(() => {
    if (!groupRef.current) return;

    const targetX = isActing ? position.x * 1.3 : position.x;
    groupRef.current.position.x += (targetX - groupRef.current.position.x) * 0.1;

    // Pulsating glow — update material directly
    if (materialRef.current) {
      if (isActing && glowIntensityRef.current < 1) {
        glowIntensityRef.current = Math.min(glowIntensityRef.current + 0.05, 1);
      } else if (!isActing) {
        glowIntensityRef.current = 0;
      }
      materialRef.current.emissiveIntensity = glowIntensityRef.current;
    }
  });

  const hp = character.resources?.[0]?.health;
  const hpPercent = hp ? Math.min(100, Math.round((hp.current / hp.max) * 100)) : 100;

  return (
    <group ref={groupRef} position={position} onClick={onClick}>
      {/* Основная карточка (плоский квад) */}
      <mesh position={[0, 0, 0]} scale={[2, 2.8, 0.1]}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial
          ref={materialRef}
          color={isAlly ? "#1a5f7a" : "#8b2e2e"}
          metalness={0.3}
          roughness={0.4}
          emissive={isActing ? "#4db8ff" : "#000000"}
          emissiveIntensity={0}
        />
      </mesh>

      {/* Фото персонажа (текстура аватарки) */}
      <mesh position={[0, 0.2, 0.06]}>
        <planeGeometry args={[1.8, 2.2]} />
        <meshStandardMaterial
          map={avatarTexture}
          color="#ffffff"
          emissive="#000000"
          emissiveIntensity={0}
          metalness={0}
          roughness={1}
        />
      </mesh>

      {/* Имя над карточкой */}
      <group position={[0, 1.6, 0.1]}>
        <mesh>
          <planeGeometry args={[2, 0.4]} />
          <meshStandardMaterial color="#000000" />
        </mesh>
      </group>

      {/* Полоска ХП внизу карточки */}
      <group position={[0, -1.3, 0.1]}>
        {/* Фон полоски */}
        <mesh position={[0, 0, 0]}>
          <planeGeometry args={[1.8, 0.25]} />
          <meshStandardMaterial color="#333333" />
        </mesh>

        {/* Сама полоска (зелёная или красная) */}
        <mesh
          position={[-(1.8 * (1 - hpPercent / 100)) / 2, 0, 0.01]}
          scale={[hpPercent / 100, 1, 1]}
        >
          <planeGeometry args={[1.8, 0.25]} />
          <meshStandardMaterial
            color={
              hpPercent > 50
                ? "#22c55e"
                : hpPercent > 25
                  ? "#f59e0b"
                  : "#ef4444"
            }
          />
        </mesh>
      </group>

      {/* Рамка выделения при выборе цели */}
      {isSelected && (
        <mesh position={[0, 0, 0.11]} scale={[2.1, 2.9, 0.1]}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial
            color="transparent"
            emissive={isAlly ? "#4db8ff" : "#ff4444"}
            emissiveIntensity={0.8}
            wireframe
          />
        </mesh>
      )}
    </group>
  );
};

// Fallback компонент пока загружается текстура
const CardMeshFallback = ({
  position,
  isAlly,
  isActing,
  isSelected,
}: BattleCardMeshProps) => {
  const groupRef = useRef<Group>(null);
  const glowIntensityRef = useRef(0);
  const materialRef = useRef<any>(null);

  useEffect(() => {
    if (isActing) {
      glowIntensityRef.current = 1;
    } else {
      glowIntensityRef.current = 0;
    }
  }, [isActing]);

  useFrame(() => {
    if (!groupRef.current) return;
    const targetX = isActing ? position.x * 1.3 : position.x;
    groupRef.current.position.x += (targetX - groupRef.current.position.x) * 0.1;

    if (materialRef.current) {
      if (isActing && glowIntensityRef.current < 1) {
        glowIntensityRef.current = Math.min(glowIntensityRef.current + 0.05, 1);
      } else if (!isActing) {
        glowIntensityRef.current = 0;
      }
      materialRef.current.emissiveIntensity = glowIntensityRef.current;
    }
  });

  return (
    <group ref={groupRef} position={position}>
      <mesh position={[0, 0, 0]} scale={[2, 2.8, 0.1]}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial
          ref={materialRef}
          color={isAlly ? "#1a5f7a" : "#8b2e2e"}
          metalness={0.3}
          roughness={0.4}
          emissive={isActing ? "#4db8ff" : "#000000"}
          emissiveIntensity={0}
        />
      </mesh>

      {/* Загрузочный плейсхолдер */}
      <mesh position={[0, 0.2, 0.06]}>
        <planeGeometry args={[1.8, 2.2]} />
        <meshStandardMaterial color="#444444" />
      </mesh>

      {isSelected && (
        <mesh position={[0, 0, 0.11]} scale={[2.1, 2.9, 0.1]}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial
            color="transparent"
            emissive={isAlly ? "#4db8ff" : "#ff4444"}
            emissiveIntensity={0.8}
            wireframe
          />
        </mesh>
      )}
    </group>
  );
};

// Компонент для загрузки текстуры через TextureLoader
const CardWithTexture = (props: BattleCardMeshProps) => {
  const [texture, setTexture] = useState<Texture | null>(null);

  useEffect(() => {
    if (!props.character.avatar) {
      console.log("[CardWithTexture] No avatar URL for:", props.character.name);
      setTexture(null);
      return;
    }

    console.log("[CardWithTexture] Loading avatar:", props.character.name, "URL:", props.character.avatar);

    const loader = new TextureLoader();
    let isMounted = true;

    loader.load(
      props.character.avatar,
      (tex) => {
        if (isMounted) {
          console.log("[CardWithTexture] Loaded texture for:", props.character.name, "size:", tex.image?.width, "x", tex.image?.height);
          tex.colorSpace = "srgb"; // sRGB color space for proper colors
          tex.magFilter = LinearFilter;
          tex.minFilter = LinearMipmapLinearFilter;
          setTexture(tex);
        }
      },
      (progress) => {
        console.log("[CardWithTexture] Loading progress for", props.character.name, ":", Math.round((progress.loaded / progress.total) * 100) + "%");
      },
      (error) => {
        if (isMounted) {
          console.warn(`[CardWithTexture] Failed to load avatar: ${props.character.avatar}`, error);
          setTexture(null);
        }
      }
    );

    return () => {
      isMounted = false;
    };
  }, [props.character.avatar]);

  if (!texture && props.character.avatar) {
    return <CardMeshFallback {...props} />;
  }

  return <CardMeshContent {...props} avatarTexture={texture} />;
};

// Основной компонент с Suspense
const BattleCardMesh = (props: BattleCardMeshProps) => {
  return (
    <Suspense fallback={<CardMeshFallback {...props} />}>
      <CardWithTexture {...props} />
    </Suspense>
  );
};

export default BattleCardMesh;
