import { Navigate } from 'react-router-dom';
import { useAppSelector } from '../../../redux/store';
import { selectRole, selectPermissions, selectAuthInitialized } from '../../../redux/slices/userSlice';
import { hasPermission, hasAnyPermission } from '../../../utils/permissions';

const ROLE_LEVELS: Record<string, number> = {
  user: 0,
  editor: 20,
  moderator: 50,
  admin: 100,
};

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRole?: string;
  requiredPermission?: string;
  requiredPermissions?: string[];
  fallbackPath?: string;
}

const ProtectedRoute = ({
  children,
  requiredRole,
  requiredPermission,
  requiredPermissions,
  fallbackPath = '/home',
}: ProtectedRouteProps) => {
  const role = useAppSelector(selectRole);
  const permissions = useAppSelector(selectPermissions);
  const authInitialized = useAppSelector(selectAuthInitialized);

  // Auth not yet initialized — show loading spinner
  if (!authInitialized) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-10 h-10 border-4 border-gold-dark border-t-gold rounded-full animate-spin" />
      </div>
    );
  }

  // Not logged in — redirect to login page
  if (!role) {
    return <Navigate to="/" replace />;
  }

  // Check role hierarchy
  if (requiredRole) {
    const userLevel = ROLE_LEVELS[role] ?? 0;
    const requiredLevel = ROLE_LEVELS[requiredRole] ?? 0;
    if (userLevel < requiredLevel) {
      return <Navigate to={fallbackPath} replace />;
    }
  }

  // Check specific permission
  if (requiredPermission && !hasPermission(permissions, requiredPermission)) {
    return <Navigate to={fallbackPath} replace />;
  }

  // Check any of required permissions
  if (requiredPermissions && requiredPermissions.length > 0 && !hasAnyPermission(permissions, requiredPermissions)) {
    return <Navigate to={fallbackPath} replace />;
  }

  return <>{children}</>;
};

export default ProtectedRoute;
