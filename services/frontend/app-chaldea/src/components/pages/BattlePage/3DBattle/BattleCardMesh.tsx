import { useRef, useEffect, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { Vector3, Group } from "three";
import type { CharacterData } from "../battleTypes";

interface BattleCardMeshProps {
  position: Vector3;
  character: CharacterData;
  isAlly: boolean;
  isActing: boolean;
  isSelected: boolean;
  onClick?: () => void;
}

const BattleCardMesh = ({
  position,
  character,
  isAlly,
  isActing,
  isSelected,
  onClick,
}: BattleCardMeshProps) => {
  const groupRef = useRef<Group>(null);
  const [glowIntensity, setGlowIntensity] = useState(0);

  // Анимация свечения при ходе
  useEffect(() => {
    if (isActing) {
      setGlowIntensity(1);
    } else {
      setGlowIntensity(0);
    }
  }, [isActing]);

  // Анимация выдвижения вперед при ходе
  useFrame((state) => {
    if (!groupRef.current) return;

    const targetX = isActing ? position.x * 1.3 : position.x;
    groupRef.current.position.x += (targetX - groupRef.current.position.x) * 0.1;

    // Пульсирующее свечение
    if (isActing && glowIntensity < 1) {
      setGlowIntensity((prev) => Math.min(prev + 0.05, 1));
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
          color={isAlly ? "#1a5f7a" : "#8b2e2e"}
          metalness={0.3}
          roughness={0.4}
          emissive={isActing ? "#4db8ff" : "#000000"}
          emissiveIntensity={glowIntensity}
        />
      </mesh>

      {/* Фото персонажа (текстура) */}
      <mesh position={[0, 0.2, 0.06]}>
        <planeGeometry args={[1.8, 2.2]} />
        <meshStandardMaterial
          map={null} // TODO: загружать текстуру из character.avatar
          color={character.avatar ? "#ffffff" : "#999999"}
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
            color={hpPercent > 50 ? "#22c55e" : hpPercent > 25 ? "#f59e0b" : "#ef4444"}
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

export default BattleCardMesh;
