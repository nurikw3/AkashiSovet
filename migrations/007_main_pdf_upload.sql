-- Main uploaded PDF for application.
-- Stores user-provided primary PDF key and original filename.

ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS main_pdf_s3_key TEXT;

ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS main_pdf_filename TEXT;
