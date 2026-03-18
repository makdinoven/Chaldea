interface RequestButtonProps {
  text: string;
  onClick: () => void;
}

const RequestButton = ({ text, onClick }: RequestButtonProps) => {
  return (
    <button
      className="w-full text-base text-white p-2.5 rounded-lg bg-black/35 hover:bg-black/15 transition-colors duration-200 ease-site"
      onClick={onClick}
    >
      {text}
    </button>
  );
};

export default RequestButton;
