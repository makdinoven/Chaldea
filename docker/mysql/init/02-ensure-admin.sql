-- Ensure user chaldea@admin.com has admin role
-- Idempotent: only updates if user exists and role is not already 'admin'

UPDATE `users`
SET `role` = 'admin'
WHERE `email` = 'chaldea@admin.com'
  AND `role` != 'admin';
