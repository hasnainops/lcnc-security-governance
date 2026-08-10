ALTER TABLE applications
    ALTER COLUMN external_integration DROP DEFAULT,
    ALTER COLUMN external_integration DROP NOT NULL;

UPDATE applications
SET
    external_integration = NULL,
    updated_at = NOW()
WHERE
    platform = 'appsmith'
    AND registration_status = 'unregistered'
    AND external_integration = FALSE;
