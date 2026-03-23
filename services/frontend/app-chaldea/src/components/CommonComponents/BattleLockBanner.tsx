interface BattleLockBannerProps {
  message: string;
}

const BattleLockBanner = ({ message }: BattleLockBannerProps) => {
  return (
    <div className="gold-outline rounded-card p-3 sm:p-4 flex items-center gap-3 bg-yellow-900/20">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        className="w-5 h-5 sm:w-6 sm:h-6 text-gold shrink-0"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z"
        />
      </svg>
      <span className="gold-text text-sm sm:text-base font-medium">
        {message}
      </span>
    </div>
  );
};

export default BattleLockBanner;
