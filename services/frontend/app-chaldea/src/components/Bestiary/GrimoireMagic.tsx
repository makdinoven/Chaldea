/**
 * GrimoireMagic — magical visual effects for the Hunter's Scroll.
 *
 * An ancient magical artifact — the scroll pulses with arcane energy,
 * runes glow along the margins, magical particles rise from the parchment,
 * and text appears as if written by invisible forces.
 */

/* ── Floating magical particles (motes of light) ── */
export const MagicParticles = () => (
  <div className="absolute inset-0 overflow-hidden pointer-events-none z-[6]">
    {Array.from({ length: 12 }).map((_, i) => (
      <div
        key={i}
        className="absolute rounded-full"
        style={{
          width: `${2 + (i % 3)}px`,
          height: `${2 + (i % 3)}px`,
          left: `${10 + (i * 7) % 80}%`,
          bottom: `${-3 + (i * 2) % 8}%`,
          background: i % 3 === 0
            ? 'rgba(180,150,60,0.8)'
            : i % 3 === 1
              ? 'rgba(140,180,230,0.6)'
              : 'rgba(180,150,60,0.5)',
          boxShadow: i % 3 === 0
            ? '0 0 6px 2px rgba(180,150,60,0.4)'
            : i % 3 === 1
              ? '0 0 8px 3px rgba(140,180,230,0.3)'
              : '0 0 4px 1px rgba(180,150,60,0.25)',
          animation: `scroll-float-${i % 4} ${5 + (i % 5) * 1.5}s ease-in-out infinite`,
          animationDelay: `${(i * 0.8) % 4}s`,
          opacity: 0,
        }}
      />
    ))}
    <style>{`
      @keyframes scroll-float-0 {
        0%, 100% { opacity: 0; transform: translateY(0) translateX(0); }
        15% { opacity: 0.7; }
        50% { opacity: 0.3; transform: translateY(-100px) translateX(12px); }
        85% { opacity: 0.5; }
      }
      @keyframes scroll-float-1 {
        0%, 100% { opacity: 0; transform: translateY(0) translateX(0); }
        20% { opacity: 0.5; }
        50% { opacity: 0.2; transform: translateY(-130px) translateX(-15px); }
        80% { opacity: 0.4; }
      }
      @keyframes scroll-float-2 {
        0%, 100% { opacity: 0; transform: translateY(0) scale(1); }
        10% { opacity: 0.6; }
        60% { opacity: 0.15; transform: translateY(-90px) scale(0.5); }
        90% { opacity: 0.4; }
      }
      @keyframes scroll-float-3 {
        0%, 100% { opacity: 0; transform: translateY(0) translateX(0); }
        25% { opacity: 0.4; }
        55% { opacity: 0.2; transform: translateY(-160px) translateX(-8px); }
        75% { opacity: 0.35; }
      }
    `}</style>
  </div>
);

/* ── Glowing runes along scroll margins ── */
export const ScrollMarginRunes = () => {
  const runes = [
    { char: 'ᚠ', y: '8%', side: 'left', delay: '0s' },
    { char: 'ᚦ', y: '22%', side: 'right', delay: '1.2s' },
    { char: 'ᚱ', y: '38%', side: 'left', delay: '2.5s' },
    { char: 'ᛗ', y: '52%', side: 'right', delay: '0.6s' },
    { char: 'ᛉ', y: '66%', side: 'left', delay: '1.8s' },
    { char: 'ᛟ', y: '78%', side: 'right', delay: '3s' },
    { char: 'ᚨ', y: '90%', side: 'left', delay: '0.3s' },
  ];

  return (
    <div className="absolute inset-0 pointer-events-none z-[5] overflow-hidden">
      {runes.map((r, i) => (
        <span
          key={i}
          className="absolute text-xs sm:text-sm select-none"
          style={{
            top: r.y,
            [r.side]: '6px',
            fontFamily: 'serif',
            color: 'rgba(139,105,20,0.12)',
            textShadow: '0 0 6px rgba(180,150,60,0.15), 0 0 12px rgba(180,150,60,0.08)',
            animation: 'scroll-rune-pulse 5s ease-in-out infinite',
            animationDelay: r.delay,
          }}
        >
          {r.char}
        </span>
      ))}
      <style>{`
        @keyframes scroll-rune-pulse {
          0%, 100% {
            opacity: 0.25;
            text-shadow: 0 0 3px rgba(180,150,60,0.1);
          }
          50% {
            opacity: 0.9;
            text-shadow: 0 0 10px rgba(180,150,60,0.35), 0 0 20px rgba(140,180,230,0.15);
          }
        }
      `}</style>
    </div>
  );
};

/* ── Pulsing glow on scroll rollers ── */
export const RollerGlow = () => (
  <div
    className="absolute inset-x-4 top-1/2 -translate-y-1/2 h-3 rounded-full pointer-events-none"
    style={{
      animation: 'roller-glow 3.5s ease-in-out infinite',
    }}
  >
    <style>{`
      @keyframes roller-glow {
        0%, 100% {
          box-shadow: 0 0 6px rgba(180,150,60,0.15), 0 0 12px rgba(180,150,60,0.05);
        }
        50% {
          box-shadow: 0 0 12px rgba(180,150,60,0.3), 0 0 24px rgba(180,150,60,0.15), 0 0 36px rgba(140,180,230,0.08);
        }
      }
    `}</style>
  </div>
);

/* ── Arcane energy lines flowing along scroll edges ── */
export const ScrollEnergyLines = () => (
  <div className="absolute inset-0 pointer-events-none z-[4] overflow-hidden">
    {/* Left edge energy */}
    <svg className="absolute left-0 top-0 w-3 h-full" viewBox="0 0 12 500" preserveAspectRatio="none">
      <path
        d="M6,0 Q3,50 6,100 Q9,150 6,200 Q3,250 6,300 Q9,350 6,400 Q3,450 6,500"
        stroke="url(#scrollEnergyGrad)" strokeWidth="1" fill="none"
        style={{ animation: 'scroll-energy-flow 4s ease-in-out infinite' }}
      />
      <defs>
        <linearGradient id="scrollEnergyGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="transparent" />
          <stop offset="20%" stopColor="rgba(180,150,60,0.2)" />
          <stop offset="50%" stopColor="rgba(140,180,230,0.15)" />
          <stop offset="80%" stopColor="rgba(180,150,60,0.2)" />
          <stop offset="100%" stopColor="transparent" />
        </linearGradient>
      </defs>
    </svg>
    {/* Right edge energy */}
    <svg className="absolute right-0 top-0 w-3 h-full" viewBox="0 0 12 500" preserveAspectRatio="none">
      <path
        d="M6,0 Q9,60 6,120 Q3,180 6,240 Q9,300 6,360 Q3,420 6,500"
        stroke="url(#scrollEnergyGrad)" strokeWidth="1" fill="none"
        style={{ animation: 'scroll-energy-flow 5s ease-in-out infinite', animationDelay: '1.5s' }}
      />
    </svg>
    <style>{`
      @keyframes scroll-energy-flow {
        0%, 100% { opacity: 0.3; }
        50% { opacity: 0.8; }
      }
    `}</style>
  </div>
);

/* ── Arcane seal — replaces simple lock icon for hidden content ── */
export const ArcaneSeal = ({ size = 48 }: { size?: number }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 48 48"
    className="pointer-events-none"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    style={{ animation: 'seal-pulse 4s ease-in-out infinite' }}
  >
    {/* Outer circle */}
    <circle cx="24" cy="24" r="22" stroke="rgba(139,105,20,0.25)" strokeWidth="0.8" />
    <circle cx="24" cy="24" r="19" stroke="rgba(139,105,20,0.15)" strokeWidth="0.5" strokeDasharray="3 5" />
    {/* Inner triangle */}
    <polygon points="24,8 38,34 10,34" stroke="rgba(139,105,20,0.2)" strokeWidth="0.6" fill="none" />
    {/* Center eye */}
    <ellipse cx="24" cy="24" rx="6" ry="4" stroke="rgba(139,105,20,0.25)" strokeWidth="0.6" fill="none" />
    <circle cx="24" cy="24" r="1.5" fill="rgba(139,105,20,0.2)" />
    {/* Cardinal runes */}
    <text x="24" y="6" textAnchor="middle" fontSize="5" fill="rgba(139,105,20,0.2)" fontFamily="serif">ᚠ</text>
    <text x="42" y="26" textAnchor="middle" fontSize="5" fill="rgba(139,105,20,0.2)" fontFamily="serif">ᛗ</text>
    <text x="6" y="26" textAnchor="middle" fontSize="5" fill="rgba(139,105,20,0.2)" fontFamily="serif">ᚱ</text>
    <text x="24" y="46" textAnchor="middle" fontSize="5" fill="rgba(139,105,20,0.2)" fontFamily="serif">ᛟ</text>
    <style>{`
      @keyframes seal-pulse {
        0%, 100% { opacity: 0.5; filter: drop-shadow(0 0 2px rgba(180,150,60,0.1)); }
        50% { opacity: 0.9; filter: drop-shadow(0 0 8px rgba(180,150,60,0.25)); }
      }
    `}</style>
  </svg>
);

/* ── SVG arcane rune circle watermark ── */
export const ArcaneCircle = ({ className = '', size = 120 }: { className?: string; size?: number }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 120 120"
    className={`pointer-events-none ${className}`}
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    style={{ animation: 'arcane-rotate 30s linear infinite' }}
  >
    <circle cx="60" cy="60" r="56" stroke="rgba(139,105,20,0.12)" strokeWidth="0.5" />
    <circle cx="60" cy="60" r="52" stroke="rgba(139,105,20,0.08)" strokeWidth="0.3" />
    <circle cx="60" cy="60" r="44" stroke="rgba(139,105,20,0.1)" strokeWidth="0.5" strokeDasharray="4 8 2 8" />
    <line x1="60" y1="8" x2="60" y2="112" stroke="rgba(139,105,20,0.06)" strokeWidth="0.3" />
    <line x1="8" y1="60" x2="112" y2="60" stroke="rgba(139,105,20,0.06)" strokeWidth="0.3" />
    <line x1="20" y1="20" x2="100" y2="100" stroke="rgba(139,105,20,0.04)" strokeWidth="0.2" />
    <line x1="100" y1="20" x2="20" y2="100" stroke="rgba(139,105,20,0.04)" strokeWidth="0.2" />
    <path d="M60 14 L57 20 L60 18 L63 20 Z" fill="rgba(139,105,20,0.1)" />
    <path d="M60 106 L57 100 L60 102 L63 100 Z" fill="rgba(139,105,20,0.1)" />
    <path d="M14 60 L20 57 L18 60 L20 63 Z" fill="rgba(139,105,20,0.1)" />
    <path d="M106 60 L100 57 L102 60 L100 63 Z" fill="rgba(139,105,20,0.1)" />
    <circle cx="26" cy="26" r="2" stroke="rgba(139,105,20,0.08)" strokeWidth="0.4" />
    <circle cx="94" cy="26" r="2" stroke="rgba(139,105,20,0.08)" strokeWidth="0.4" />
    <circle cx="26" cy="94" r="2" stroke="rgba(139,105,20,0.08)" strokeWidth="0.4" />
    <circle cx="94" cy="94" r="2" stroke="rgba(139,105,20,0.08)" strokeWidth="0.4" />
    <polygon points="60,24 90,80 30,80" stroke="rgba(139,105,20,0.06)" strokeWidth="0.4" fill="none" />
    <circle cx="60" cy="60" r="18" stroke="rgba(139,105,20,0.08)" strokeWidth="0.5" />
    <circle cx="60" cy="60" r="2" fill="rgba(139,105,20,0.12)" />
    <style>{`
      @keyframes arcane-rotate { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
    `}</style>
  </svg>
);

/* ── LoreShimmer — now just a passthrough, shimmer removed ── */
export const LoreShimmer = ({ children }: { children: React.ReactNode }) => (
  <>{children}</>
);

/* ── Rune watermarks densely covering the parchment ── */
export const ParchmentWatermarks = () => {
  const allRunes = 'ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃᛈᛉᛊᛏᛒᛗᛚᛞᛟ';
  const marks = [
    /* Row 1 */
    { char: allRunes[0], x: '5%', y: '3%', size: '22px', rotate: -12, delay: '0s' },
    { char: allRunes[1], x: '22%', y: '5%', size: '18px', rotate: 20, delay: '1.5s' },
    { char: allRunes[2], x: '42%', y: '2%', size: '26px', rotate: -5, delay: '3s' },
    { char: allRunes[3], x: '65%', y: '4%', size: '20px', rotate: 15, delay: '0.8s' },
    { char: allRunes[4], x: '85%', y: '3%', size: '24px', rotate: -18, delay: '2.2s' },
    /* Row 2 */
    { char: allRunes[5], x: '8%', y: '14%', size: '28px', rotate: 8, delay: '1s' },
    { char: allRunes[6], x: '32%', y: '16%', size: '16px', rotate: -22, delay: '2.8s' },
    { char: allRunes[7], x: '55%', y: '13%', size: '24px', rotate: 12, delay: '0.3s' },
    { char: allRunes[8], x: '78%', y: '15%', size: '20px', rotate: -8, delay: '1.8s' },
    /* Row 3 */
    { char: allRunes[9], x: '12%', y: '26%', size: '20px', rotate: -15, delay: '2.5s' },
    { char: allRunes[10], x: '38%', y: '28%', size: '30px', rotate: 5, delay: '0.5s' },
    { char: allRunes[11], x: '60%', y: '25%', size: '18px', rotate: -20, delay: '3.2s' },
    { char: allRunes[12], x: '82%', y: '27%', size: '22px', rotate: 10, delay: '1.2s' },
    /* Row 4 */
    { char: allRunes[13], x: '6%', y: '38%', size: '24px', rotate: 18, delay: '2s' },
    { char: allRunes[14], x: '28%', y: '40%', size: '20px', rotate: -10, delay: '0.7s' },
    { char: allRunes[15], x: '50%', y: '37%', size: '26px', rotate: 14, delay: '2.8s' },
    { char: allRunes[16], x: '72%', y: '39%', size: '18px', rotate: -25, delay: '1.5s' },
    { char: allRunes[17], x: '90%', y: '38%', size: '22px', rotate: 7, delay: '3.5s' },
    /* Row 5 */
    { char: allRunes[18], x: '15%', y: '50%', size: '26px', rotate: -8, delay: '1.3s' },
    { char: allRunes[19], x: '40%', y: '52%', size: '22px', rotate: 22, delay: '2.6s' },
    { char: allRunes[20], x: '62%', y: '49%', size: '28px', rotate: -12, delay: '0.4s' },
    { char: allRunes[0], x: '85%', y: '51%', size: '20px', rotate: 16, delay: '1.9s' },
    /* Row 6 */
    { char: allRunes[1], x: '8%', y: '62%', size: '20px', rotate: 10, delay: '3s' },
    { char: allRunes[2], x: '30%', y: '64%', size: '24px', rotate: -18, delay: '0.6s' },
    { char: allRunes[3], x: '52%', y: '61%', size: '18px', rotate: 25, delay: '2.2s' },
    { char: allRunes[4], x: '75%', y: '63%', size: '26px', rotate: -6, delay: '1.1s' },
    /* Row 7 */
    { char: allRunes[5], x: '12%', y: '74%', size: '22px', rotate: -20, delay: '2.4s' },
    { char: allRunes[6], x: '35%', y: '76%', size: '28px', rotate: 8, delay: '0.9s' },
    { char: allRunes[7], x: '58%', y: '73%', size: '20px', rotate: -14, delay: '3.1s' },
    { char: allRunes[8], x: '80%', y: '75%', size: '24px', rotate: 12, delay: '1.6s' },
    /* Row 8 */
    { char: allRunes[9], x: '6%', y: '86%', size: '18px', rotate: 15, delay: '2.7s' },
    { char: allRunes[10], x: '25%', y: '88%', size: '24px', rotate: -10, delay: '0.2s' },
    { char: allRunes[11], x: '48%', y: '85%', size: '22px', rotate: 20, delay: '1.8s' },
    { char: allRunes[12], x: '70%', y: '87%', size: '26px', rotate: -15, delay: '3.4s' },
    { char: allRunes[13], x: '88%', y: '86%', size: '20px', rotate: 5, delay: '0.8s' },
    /* Row 9 */
    { char: allRunes[14], x: '18%', y: '95%', size: '22px', rotate: -8, delay: '2.1s' },
    { char: allRunes[15], x: '45%', y: '96%', size: '20px', rotate: 18, delay: '1.4s' },
    { char: allRunes[16], x: '72%', y: '94%', size: '24px', rotate: -22, delay: '3.3s' },
  ];

  return (
    <div className="absolute inset-0 pointer-events-none z-[2] overflow-hidden">
      {marks.map((m, i) => (
        <span
          key={i}
          className="absolute select-none"
          style={{
            left: m.x,
            top: m.y,
            fontSize: m.size,
            fontFamily: 'serif',
            color: 'rgba(201,168,76,0.25)',
            transform: `rotate(${m.rotate}deg)`,
            animation: 'rune-watermark-breathe 6s ease-in-out infinite',
            animationDelay: m.delay,
          }}
        >
          {m.char}
        </span>
      ))}
      <style>{`
        @keyframes rune-watermark-breathe {
          0%, 100% { opacity: 0.4; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  );
};

/* ── Re-exports for backward compat (book components still reference these) ── */
export const ArcaneGlow = () => null;
export const CoverRunes = () => null;
export const CoverEmblem = () => null;
export const MagicThreads = ({ side: _side }: { side: 'left' | 'right' }) => null;
