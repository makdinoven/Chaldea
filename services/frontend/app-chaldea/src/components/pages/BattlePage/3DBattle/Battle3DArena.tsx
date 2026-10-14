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
        position={[0, 5, 10]}
        fov={50}
        near={0.1}
        far={1000}
        lookAt={[0, 0, 0]}
      />

      {/* Lighting - улучшенное освещение */}
      <ambientLight intensity={0.8} color="#ffffff" />
      <directionalLight
        position={[10, 15, 10]}
        intensity={1.5}
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
      />
      <pointLight position={[-10, 8, -10]} intensity={0.6} color="#4db8ff" />
      <pointLight position={[10, 8, 10]} intensity={0.6} color="#ff6b6b" />

      {/* Arena floor - основной */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]} receiveShadow>
        <planeGeometry args={[30, 30]} />
        <meshStandardMaterial
          color="#3a3a4e"
          roughness={0.6}
          metalness={0.2}
        />
      </mesh>

      {/* Декоративный пол - паттерн */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]}>
        <planeGeometry args={[30, 30]} />
        <meshStandardMaterial
          color="#2a2a3e"
          roughness={0.8}
          transparent
          opacity={0.5}
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
