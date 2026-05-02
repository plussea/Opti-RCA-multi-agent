-- Add topology_id and location columns to alarm_records
-- Run after 001_init.sql

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'alarm_records'
        AND column_name = 'topology_id'
    ) THEN
        ALTER TABLE alarm_records ADD COLUMN topology_id VARCHAR(100);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'alarm_records'
        AND column_name = 'location'
    ) THEN
        ALTER TABLE alarm_records ADD COLUMN location VARCHAR(500);
    END IF;
EXCEPTION
    WHEN undefined_table THEN
        RAISE NOTICE 'alarm_records table not yet created, run SQLAlchemy first';
END $$;