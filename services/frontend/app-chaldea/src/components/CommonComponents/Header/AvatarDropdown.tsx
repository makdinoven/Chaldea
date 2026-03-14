import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { DropdownLink } from './types';

interface AvatarDropdownProps {
  imageSrc: string;
  altText: string;
  size?: number;
  links: DropdownLink[];
  placeholderIcon?: ReactNode;
}

const AvatarDropdown = ({
  imageSrc,
  altText,
  size = 64,
  links,
  placeholderIcon,
}: AvatarDropdownProps) => {
  return (
    <div className="relative group/avatar">
      <div
        className="rounded-full overflow-hidden bg-white/10 flex-shrink-0 cursor-pointer flex items-center justify-center"
        style={{ width: size, height: size }}
      >
        {imageSrc ? (
          <img
            src={imageSrc}
            alt={altText}
            className="w-full h-full object-cover"
          />
        ) : (
          placeholderIcon ?? <div className="w-full h-full bg-white/10" />
        )}
      </div>

      {/* pt-0 to eliminate gap between avatar and dropdown */}
      <div className="absolute top-full left-1/2 -translate-x-1/2 pt-0 z-50 hidden group-hover/avatar:block">
        <div className="dropdown-menu mt-2">
          {links.map((link) =>
            link.onClick ? (
              <button
                key={link.label}
                onClick={link.onClick}
                className="dropdown-item w-full text-left"
              >
                {link.label}
              </button>
            ) : (
              <Link
                key={link.label}
                to={link.path}
                className="dropdown-item"
              >
                {link.label}
              </Link>
            ),
          )}
        </div>
      </div>
    </div>
  );
};

export default AvatarDropdown;
