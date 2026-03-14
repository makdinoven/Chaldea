import { Link } from 'react-router-dom';
import { Shield } from 'react-feather';

interface AdminMenuProps {
  role: string | null;
}

const AdminMenu = ({ role }: AdminMenuProps) => {
  if (role !== 'admin') return null;

  return (
    <Link
      to="/admin"
      className="p-1 text-white hover:text-site-blue transition-colors duration-200 ease-site"
      aria-label="Админка"
    >
      <Shield size={32} strokeWidth={2} />
    </Link>
  );
};

export default AdminMenu;
