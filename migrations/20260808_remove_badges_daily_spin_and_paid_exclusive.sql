-- Holy Grills: remove badges/milestones and paid spin paths
-- Paste this whole file into the Supabase SQL Editor.
-- The statements are idempotent and preserve historical rows for auditability.

-- Disable feature switches for functionality that no longer exists.
UPDATE public.feature_flags
SET is_active = FALSE, updated_at = NOW()
WHERE feature_name IN ('badge_system', 'spin_and_win', 'referral_milestones');

-- Existing milestone definitions must not be served or awarded.
UPDATE public.milestones
SET is_active = FALSE
WHERE is_active = TRUE;

-- Do not let legacy purchased/admin credits become usable as exclusive spins.
-- Leaderboard winners remain the only eligible source.
UPDATE public.exclusive_spins
SET spin_count = 0
WHERE source IS DISTINCT FROM 'leaderboard_prize'
  AND spin_count > 0;

-- Remove the old paid-spin setting if it exists.
DELETE FROM public.system_settings
WHERE key = 'exclusive_spin_extra_cost';

-- The only supported menu HP event values are 1x (off) and 2x (active).
-- Normalize any stale half-HP or other invalid values to disabled (1x).
-- The imported schema has existed with both TEXT and JSONB value columns, so
-- select the correct literal type at runtime.
DO $$
DECLARE
    value_type TEXT;
BEGIN
    SELECT CASE WHEN udt_name = 'jsonb' THEN 'jsonb' ELSE data_type END INTO value_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'system_settings'
      AND column_name = 'value';

    IF value_type = 'jsonb' THEN
        EXECUTE $sql$
            UPDATE public.system_settings
            SET value = '1'::jsonb, updated_at = NOW()
            WHERE key = 'hp_multiplier'
              AND value::text NOT IN ('"1"', '"2"', '1', '2')
        $sql$;
    ELSE
        EXECUTE $sql$
            UPDATE public.system_settings
            SET value = '1', updated_at = NOW()
            WHERE key = 'hp_multiplier'
              AND value NOT IN ('1', '2')
        $sql$;
    END IF;
END $$;