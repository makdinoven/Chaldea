import { Link } from 'react-router-dom';

interface MegaMenuLink {
  label: string;
  path: string;
}

export interface MegaMenuCategory {
  title: string;
  links: MegaMenuLink[];
}

interface MegaMenuProps {
  categories: MegaMenuCategory[];
}

const MegaMenu = ({ categories }: MegaMenuProps) => {
  const cols = Math.min(categories.length, 5);

  return (
    <div className="bg-black/50 backdrop-blur-md rounded-[15px] overflow-hidden p-5 text-white shadow-dropdown">
      <div
        className="grid gap-6"
        style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}
      >
        {categories.map((category) => (
          <div key={category.title}>
            <h3 className="gold-text text-base font-medium uppercase tracking-[0.06em] mb-3">
              {category.title}
            </h3>
            <ul className="flex flex-col gap-2">
              {category.links.map((link) => (
                <li key={link.label}>
                  <Link
                    to={link.path}
                    className="site-link text-sm uppercase tracking-[0.06em] font-montserrat"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
};

export default MegaMenu;
