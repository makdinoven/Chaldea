import { User } from 'react-feather';

export interface AvatarFrame {
  id: string;
  label: string;
  borderStyle: string;
  shadow: string;
}

interface AvatarFramePreviewProps {
  avatarUrl: string | null;
  frame: AvatarFrame;
}

const AvatarFramePreview = ({ avatarUrl, frame }: AvatarFramePreviewProps) => {
  const hasFrame = frame.id !== 'none' && frame.borderStyle !== 'none';

  return (
    <div
      className="w-[60px] h-[60px] rounded-[12px] overflow-hidden bg-black/30 flex items-center justify-center flex-shrink-0"
      style={
        hasFrame
          ? { border: frame.borderStyle, boxShadow: frame.shadow }
          : undefined
      }
    >
      {avatarUrl ? (
        <img src={avatarUrl} alt="preview" className="w-full h-full object-cover" />
      ) : (
        <User size={24} className="text-white/20" />
      )}
    </div>
  );
};

export default AvatarFramePreview;
