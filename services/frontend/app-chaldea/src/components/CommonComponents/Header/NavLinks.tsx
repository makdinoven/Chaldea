import { Link } from 'react-router-dom';
import MegaMenu from './MegaMenu';
import { navItems } from './navData';

const NavLinks = () => {
  return (
    <nav className="flex items-center gap-4 xl:gap-8 whitespace-nowrap">
      {navItems.map((item) =>
        item.megaMenu ? (
          <div key={item.label} className="group/nav relative pb-2 -mb-2">
            <Link to={item.path} className="nav-link text-sm">
              {item.label}
            </Link>
            {/* Invisible bridge: padding area extends hover zone down to the dropdown */}
            <div
              className={`hidden group-hover/nav:block absolute z-50 pt-2 left-0`}
              style={{ top: '100%' }}
            >
              <MegaMenu categories={item.megaMenu} />
            </div>
          </div>
        ) : (
          <Link key={item.label} to={item.path} className="nav-link text-sm">
            {item.label}
          </Link>
        ),
      )}
    </nav>
  );
};

export default NavLinks;
