ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS shadow_it_candidate BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_applications_shadow_it_candidate
    ON applications(shadow_it_candidate)
    WHERE shadow_it_candidate = TRUE;
