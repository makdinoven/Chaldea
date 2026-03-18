-- Ensure admin user has role_id set after RBAC migration
-- This handles fresh installs where 02-ensure-admin.sql sets role='admin'
-- but the Alembic migration (which creates the roles table and sets role_id)
-- may have already run on a previous container start.
--
-- Safe to run multiple times (idempotent).
-- Safe if roles table doesn't exist yet (procedure checks before UPDATE).

DELIMITER //

CREATE PROCEDURE IF NOT EXISTS ensure_admin_rbac()
BEGIN
    DECLARE roles_exists INT DEFAULT 0;

    -- Check if roles table exists in this database
    SELECT COUNT(*) INTO roles_exists
    FROM information_schema.tables
    WHERE table_schema = DATABASE()
      AND table_name = 'roles';

    IF roles_exists = 1 THEN
        UPDATE users u
        SET u.role_id = (SELECT id FROM roles WHERE name = 'admin')
        WHERE u.email = 'chaldea@admin.com'
          AND u.role_id IS NULL
          AND EXISTS (SELECT 1 FROM roles WHERE name = 'admin');
    END IF;
END //

DELIMITER ;

CALL ensure_admin_rbac();

DROP PROCEDURE IF EXISTS ensure_admin_rbac;
