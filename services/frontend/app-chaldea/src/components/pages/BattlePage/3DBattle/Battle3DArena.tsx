import { Canvas } from "@react-three/fiber";
import { PerspectiveCamera, OrbitControls } from "@react-three/drei";
import { Vector3 } from "three";
import BattleCardMesh from "./BattleCardMesh";
import type { CharacterData } from "../battleTypes";

interface Battle3DArenaProps {
  myTeamData: CharacterData[];
  enemyTeamData: CharacterData[];
  currentActorId: number | null;
  selectedTargetId: number | null;
  onCardClick?: (participantId: number, isEnemy: boolean) => void;
}

const Battle3DArena = ({
  myTeamData,
  enemyTeamData,
  currentActorId,
  selectedTargetId,
  onCardClick,
}: Battle3DArenaProps) => {
  console.log("[Battle3DArena] Rendering with:", {
    myTeam: myTeamData.length,
    enemyTeam: enemyTeamData.length,
    currentActor: currentActorId,
  });

  return (
    <Canvas
      style={{ width: '100%', height: '100%', display: 'block' }}
      gl={{ antialias: true, alpha: false, logarithmicDepthBuffer: true }}
      camera={{ position: [0, 2, 8], fov: 60, near: 0.1, far: 1000 }}
      onCreated={(state) => {
        console.log("[Canvas] Created successfully", {
          canvas: state.gl.domElement,
          size: state.size,
          camera: state.camera.position,
        });
      }}
    >
      <PerspectiveCamera
        makeDefault
        position={[0, 2, 8]}
        fov={60}
        near={0.1}
        far={1000}
      />

      {/* Lighting */}
      <ambientLight intensity={0.6} />
      <directionalLight position={[5, 10, 5]} intensity={1} castShadow />
      <pointLight position={[-5, 5, -5]} intensity={0.4} />

      {/* Arena floor (простой квад с текстурой) */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]} receiveShadow>
        <planeGeometry args={[20, 20]} />
        <meshStandardMaterial
          color="#2a2a3e"
          roughness={0.7}
          metalness={0.1}
        />
      </mesh>

      {/* Вспомогательный пол (видимость) */}
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[0, 0.01, 0]}
        scale={1.02}
      >
        <planeGeometry args={[20, 20]} />
        <meshStandardMaterial
          color="#1a1a2e"
          roughness={0.9}
          transparent
          opacity={0.3}
        />
      </mesh>

      {/* Команда (слева, z = 2) */}
      {myTeamData.map((character, index) => {
        const spacing = 2;
        const totalHeight = (myTeamData.length - 1) * spacing;
        const yOffset = (index * spacing) - totalHeight / 2;

        return (
          <BattleCardMesh
            key={`ally-${character.participant_id}`}
            position={new Vector3(-5, yOffset, 2)}
            character={character}
            isAlly
            isActing={currentActorId === character.participant_id}
            isSelected={selectedTargetId === character.participant_id}
            onClick={() =>
              onCardClick?.(character.participant_id as number, false)
            }
          />
        );
      })}

      {/* Враги (справа, z = -2) */}
      {enemyTeamData.map((character, index) => {
        const spacing = 2;
        const totalHeight = (enemyTeamData.length - 1) * spacing;
        const yOffset = (index * spacing) - totalHeight / 2;

        return (
          <BattleCardMesh
            key={`enemy-${character.participant_id}`}
            position={new Vector3(5, yOffset, -2)}
            character={character}
            isAlly={false}
            isActing={currentActorId === character.participant_id}
            isSelected={selectedTargetId === character.participant_id}
            onClick={() =>
              onCardClick?.(character.participant_id as number, true)
            }
          />
        );
      })}

      {/* OrbitControls для отладки (можно удалить после) */}
      <OrbitControls enableZoom={true} enablePan={true} enableRotate={true} />
    </Canvas>
  );
};

export default Battle3DArena;
