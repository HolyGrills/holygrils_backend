-- ============================================================================
-- run10_new_features.sql
-- Holy Grills — Phase 3 Features Migration
-- Paste into Supabase SQL Editor and run.
--
-- FIXES vs original draft:
--   • system_settings.value is JSONB in this database — all plain-text UPDATE/
--     INSERT values are now correctly cast:
--       plain string  → '"value"'::jsonb
--       numeric       → '5'::jsonb          (numeric literals are valid JSON)
--       JSON arrays   → '[...]'::jsonb
--       JSON objects  → '{...}'::jsonb
--       timestamp     → to_jsonb(NOW()::TEXT)
--   • Admin service_role bypass policies added to all new tables.
-- ============================================================================


-- ── 1. feature_flags ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.feature_flags (
    feature_name TEXT PRIMARY KEY,
    is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
    description   TEXT,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by    UUID REFERENCES public.profiles(id) ON DELETE SET NULL
);

COMMENT ON TABLE public.feature_flags IS
    'Per-feature on/off switches. All flags default TRUE — flip to FALSE to disable without a code deploy.';

INSERT INTO public.feature_flags (feature_name, is_active, description) VALUES
    ('leaderboard_prizes',    TRUE,  'Enables prize payout logic and winner selection after each monthly reset'),
    ('free_side_credits',     TRUE,  'Controls free side credit issuance and redemption at checkout'),
    ('exclusive_spin',        TRUE,  'Unlocks exclusive spin rewards pool for top-10 leaderboard finishers'),
    ('hall_of_fame',          TRUE,  'Activates Hall of Fame data recording and winner archiving'),
    ('badge_system',          TRUE,  'Enables badge engine — award logic, criteria checks, HP triggers'),
    ('spin_and_win',          TRUE,  'Enables regular spin mechanics and HP cost deduction'),
    ('marketplace_general',   FALSE, 'Opens marketplace to students — listings visible and purchasable'),
    ('hp_transfer',           FALSE, 'Enables peer-to-peer HP transfer with guardrails'),
    ('flash_redemptions',     FALSE, 'Enables time-limited HP discount drops on specific rewards'),
    ('squad_orders',          TRUE,  'Enables group ordering flow and squad HP bonus calculation'),
    ('referral_milestones',   TRUE,  'Activates milestone HP awards at 5, 10, 20, 30, 50 referrals'),
    ('subscription_codes',    FALSE, 'Opens subscription code redemption in rewards store'),
    ('hp_expiry_warnings',    TRUE,  'Sends depreciation warning notifications to inactive users'),
    ('birthday_hp',           TRUE,  'Enables automatic birthday HP award job'),
    ('scheduled_orders',      TRUE,  'Enables future order scheduling and delivery window pre-booking'),
    ('abandoned_cart_nudge',  FALSE, 'Enables automated recovery nudge after 30 minutes of cart inactivity'),
    ('daily_checkin',         TRUE,  'Enables explicit daily check-in button and calendar view'),
    ('event_ticket_tiers',    TRUE,  'Enables multi-tier ticket pricing for events')
ON CONFLICT (feature_name) DO NOTHING;


-- ── 2. daily_checkins ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.daily_checkins (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    checkin_date DATE NOT NULL,
    hp_awarded   INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT daily_checkins_user_date_unique UNIQUE (user_id, checkin_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_checkins_user_id ON public.daily_checkins (user_id);
CREATE INDEX IF NOT EXISTS idx_daily_checkins_date    ON public.daily_checkins (checkin_date);

COMMENT ON TABLE public.daily_checkins IS
    'One row per user per calendar day for the explicit daily check-in feature. Separate from login_streaks.';


-- ── 3. free_side_credits ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.free_side_credits (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    credits_remaining INT  NOT NULL DEFAULT 0 CHECK (credits_remaining >= 0),
    source            TEXT NOT NULL,    -- 'leaderboard_prize' | 'admin_grant'
    month             TEXT,             -- 'YYYY-MM' for leaderboard prizes
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at        TIMESTAMPTZ NOT NULL,
    used_at           TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_free_side_credits_user_id    ON public.free_side_credits (user_id);
CREATE INDEX IF NOT EXISTS idx_free_side_credits_expires_at ON public.free_side_credits (expires_at);
CREATE INDEX IF NOT EXISTS idx_free_side_credits_active
    ON public.free_side_credits (user_id, expires_at)
    WHERE credits_remaining > 0;

COMMENT ON TABLE public.free_side_credits IS
    'Free side dish credits. Decrements by 1 per use at checkout. Expires after free_side_credits_validity_days days.';


-- ── 4. exclusive_spins ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.exclusive_spins (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    spin_count INT  NOT NULL DEFAULT 0 CHECK (spin_count >= 0),
    source     TEXT NOT NULL,    -- 'leaderboard_prize' | 'purchased' | 'admin_grant'
    month      TEXT,             -- 'YYYY-MM' for leaderboard prizes
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_exclusive_spins_user_id    ON public.exclusive_spins (user_id);
CREATE INDEX IF NOT EXISTS idx_exclusive_spins_expires_at ON public.exclusive_spins (expires_at);
CREATE INDEX IF NOT EXISTS idx_exclusive_spins_active
    ON public.exclusive_spins (user_id, expires_at)
    WHERE spin_count > 0;

COMMENT ON TABLE public.exclusive_spins IS
    'Exclusive spin wheel credits. spin_count decrements per spin. Expires after exclusive_spin_validity_days days.';


-- ── 5. event_ticket_tiers ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.event_ticket_tiers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id    UUID NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    price_naira NUMERIC(12, 2) NOT NULL DEFAULT 0,
    price_hp    INT            NOT NULL DEFAULT 0,
    capacity    INT,           -- NULL = unlimited
    sold_count  INT            NOT NULL DEFAULT 0 CHECK (sold_count >= 0),
    description TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_ticket_tiers_event_id ON public.event_ticket_tiers (event_id);

COMMENT ON TABLE public.event_ticket_tiers IS
    'Ticket pricing tiers for a single event (e.g. VIP, Regular, Early Bird). Linked via tier_id on event_tickets.';

-- Add tier_id FK to event_tickets
ALTER TABLE public.event_tickets
    ADD COLUMN IF NOT EXISTS tier_id UUID REFERENCES public.event_ticket_tiers(id) ON DELETE SET NULL;


-- ── 6. leaderboard_reward_fulfillments ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.leaderboard_reward_fulfillments (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    rank         INT  NOT NULL CHECK (rank BETWEEN 1 AND 10),
    month        TEXT NOT NULL,   -- 'YYYY-MM'
    reward_type  TEXT NOT NULL DEFAULT 'leaderboard_prize',
    free_sides   INT  NOT NULL DEFAULT 0,
    free_spins   INT  NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','fulfilled','cancelled')),
    notes        TEXT,
    fulfilled_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    fulfilled_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_lb_fulfillment_user_month
    ON public.leaderboard_reward_fulfillments (user_id, month);

CREATE INDEX IF NOT EXISTS idx_lb_fulfillments_status  ON public.leaderboard_reward_fulfillments (status);
CREATE INDEX IF NOT EXISTS idx_lb_fulfillments_month   ON public.leaderboard_reward_fulfillments (month);

COMMENT ON TABLE public.leaderboard_reward_fulfillments IS
    'Admin fulfilment tracker for monthly leaderboard prizes (free sides + exclusive spins per rank).';


-- ── 7. hall_of_fame_rewards ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.hall_of_fame_rewards (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE UNIQUE,
    inducted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status       TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','box_prepared','fulfilled','cancelled')),
    notes        TEXT,
    fulfilled_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    fulfilled_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hof_rewards_status ON public.hall_of_fame_rewards (status);

COMMENT ON TABLE public.hall_of_fame_rewards IS
    'Admin fulfilment tracker for Hall of Fame inductee reward boxes. One row per inducted user.';


-- ── 8. system_settings — upsert new keys ─────────────────────────────────────
--
-- NOTE: system_settings.value is JSONB in this database.
--   • Plain strings must be quoted JSON:  '"text"'::jsonb
--   • Numbers are already valid JSON:     '5'::jsonb
--   • Arrays/objects are already valid:   '[...]'::jsonb
--
-- Fix the two stale rows that caused errors in the original draft:
UPDATE public.system_settings
    SET value = '"Holy Grills"'::jsonb
    WHERE key = 'platform_name';

UPDATE public.system_settings
    SET value = to_jsonb(NOW()::TEXT)
    WHERE key = 'launch_window_end_date';

-- Remove obsolete settings
DELETE FROM public.system_settings WHERE key IN (
    'referral_hp_reward',
    'sim_setting_order_hp',
    'sim_setting_review_hp',
    'sim_setting_referral_hp'
);

-- Insert / overwrite new settings
INSERT INTO public.system_settings (key, value, description) VALUES
    ('daily_checkin_hp',
        '5'::jsonb,
        'HP awarded per explicit daily check-in'),

    ('free_side_options',
        '["Fries","Coleslaw","Plantain","Gizzard"]'::jsonb,
        'Admin-configurable list of free side dish choices shown at checkout'),

    ('free_side_credits_validity_days',
        '60'::jsonb,
        'Days before free side credits expire after award'),

    ('exclusive_spin_extra_cost',
        '500'::jsonb,
        'HP cost to purchase one additional exclusive spin'),

    ('exclusive_spin_validity_days',
        '30'::jsonb,
        'Days before exclusive spin credits expire after award'),

    ('leaderboard_prize_rank1_sides',
        '3'::jsonb,
        'Free side credits awarded to monthly #1 finisher'),

    ('leaderboard_prize_rank2_sides',
        '2'::jsonb,
        'Free side credits awarded to monthly #2 finisher'),

    ('leaderboard_prize_rank3_sides',
        '1'::jsonb,
        'Free side credit awarded to monthly #3 finisher'),

    ('hof_induction_threshold',
        '4'::jsonb,
        'Number of top-4 leaderboard finishes required for Hall of Fame induction'),

    ('squad_order_max_items',
        '6'::jsonb,
        'Maximum total item quantity allowed in a squad order'),

    ('exclusive_spin_prizes',
        '[{"name":"HP Jackpot +750","weight":5},{"name":"HP Bolt +300","weight":20},{"name":"HP Boost +150","weight":15},{"name":"Free Sausage x2","weight":15},{"name":"Free Gizzard x3","weight":15},{"name":"Free Side","weight":10},{"name":"Free Coleslaw","weight":10},{"name":"Double HP next order","weight":10}]'::jsonb,
        'Exclusive spin prize pool (name + probability weight). Weights must sum to 100.'),

    ('order_streak_hp_rewards',
        '{"3":100,"6":200,"12":350}'::jsonb,
        'HP bonuses at order streak week milestones (JSON object: weeks→HP)'),

    ('referral_milestones',
        '{"5":150,"10":400,"20":750,"30":1200,"50":2500}'::jsonb,
        'HP rewards at referral count milestones (JSON object: count→HP)'),

    ('membership_rewards',
        '{"3":100,"6":200,"12":500,"24":750,"36":1000,"48":1250,"60":1500}'::jsonb,
        'HP rewards at membership month milestones (JSON object: months→HP)'),

    ('notification_channels_default',
        '["push","in_app"]'::jsonb,
        'Default notification channels for all non-critical notifications'),

    ('notification_channels_critical',
        '["push","in_app","email"]'::jsonb,
        'Channels used for critical notifications: order_confirmed, order_delivered, delivery_attempted, refund, hp_expiry, tier_drop')

ON CONFLICT (key) DO UPDATE
    SET value       = EXCLUDED.value,
        description = EXCLUDED.description,
        updated_at  = NOW();


-- ── 9. milestones — new trigger_meta column ───────────────────────────────────
ALTER TABLE public.milestones
    ADD COLUMN IF NOT EXISTS trigger_meta JSONB;

COMMENT ON COLUMN public.milestones.trigger_meta IS
    'Extra config for trigger_type (e.g. {"category_id":"uuid"} for item_category, {"min_total":20000} for min_order_total)';


-- ── 10. Row-Level Security ────────────────────────────────────────────────────

-- feature_flags
ALTER TABLE public.feature_flags ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "feature_flags_read_all"    ON public.feature_flags;
DROP POLICY IF EXISTS "feature_flags_admin_write" ON public.feature_flags;
DROP POLICY IF EXISTS "feature_flags_service_all" ON public.feature_flags;

CREATE POLICY "feature_flags_read_all"
    ON public.feature_flags FOR SELECT TO authenticated, anon USING (TRUE);

CREATE POLICY "feature_flags_admin_write"
    ON public.feature_flags FOR ALL
    USING (EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin'));

CREATE POLICY "feature_flags_service_all"
    ON public.feature_flags FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);


-- daily_checkins
ALTER TABLE public.daily_checkins ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "daily_checkins_own"     ON public.daily_checkins;
DROP POLICY IF EXISTS "daily_checkins_service" ON public.daily_checkins;

CREATE POLICY "daily_checkins_own"
    ON public.daily_checkins FOR ALL TO authenticated
    USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY "daily_checkins_service"
    ON public.daily_checkins FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);


-- free_side_credits
ALTER TABLE public.free_side_credits ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "free_side_credits_own"     ON public.free_side_credits;
DROP POLICY IF EXISTS "free_side_credits_admin"   ON public.free_side_credits;
DROP POLICY IF EXISTS "free_side_credits_service" ON public.free_side_credits;

CREATE POLICY "free_side_credits_own"
    ON public.free_side_credits FOR SELECT TO authenticated USING (user_id = auth.uid());

CREATE POLICY "free_side_credits_admin"
    ON public.free_side_credits FOR ALL
    USING (EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin'));

CREATE POLICY "free_side_credits_service"
    ON public.free_side_credits FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);


-- exclusive_spins
ALTER TABLE public.exclusive_spins ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "exclusive_spins_own"     ON public.exclusive_spins;
DROP POLICY IF EXISTS "exclusive_spins_admin"   ON public.exclusive_spins;
DROP POLICY IF EXISTS "exclusive_spins_service" ON public.exclusive_spins;

CREATE POLICY "exclusive_spins_own"
    ON public.exclusive_spins FOR SELECT TO authenticated USING (user_id = auth.uid());

CREATE POLICY "exclusive_spins_admin"
    ON public.exclusive_spins FOR ALL
    USING (EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin'));

CREATE POLICY "exclusive_spins_service"
    ON public.exclusive_spins FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);


-- event_ticket_tiers
ALTER TABLE public.event_ticket_tiers ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "event_tiers_read_all" ON public.event_ticket_tiers;
DROP POLICY IF EXISTS "event_tiers_admin"    ON public.event_ticket_tiers;
DROP POLICY IF EXISTS "event_tiers_service"  ON public.event_ticket_tiers;

CREATE POLICY "event_tiers_read_all"
    ON public.event_ticket_tiers FOR SELECT TO authenticated, anon USING (is_active = TRUE);

CREATE POLICY "event_tiers_admin"
    ON public.event_ticket_tiers FOR ALL
    USING (EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin'));

CREATE POLICY "event_tiers_service"
    ON public.event_ticket_tiers FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);


-- leaderboard_reward_fulfillments
ALTER TABLE public.leaderboard_reward_fulfillments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lb_fulfill_own_read" ON public.leaderboard_reward_fulfillments;
DROP POLICY IF EXISTS "lb_fulfill_admin"    ON public.leaderboard_reward_fulfillments;
DROP POLICY IF EXISTS "lb_fulfill_service"  ON public.leaderboard_reward_fulfillments;

CREATE POLICY "lb_fulfill_own_read"
    ON public.leaderboard_reward_fulfillments FOR SELECT TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY "lb_fulfill_admin"
    ON public.leaderboard_reward_fulfillments FOR ALL
    USING (EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin'));

CREATE POLICY "lb_fulfill_service"
    ON public.leaderboard_reward_fulfillments FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);


-- hall_of_fame_rewards
ALTER TABLE public.hall_of_fame_rewards ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "hof_rewards_own_read" ON public.hall_of_fame_rewards;
DROP POLICY IF EXISTS "hof_rewards_admin"    ON public.hall_of_fame_rewards;
DROP POLICY IF EXISTS "hof_rewards_service"  ON public.hall_of_fame_rewards;

CREATE POLICY "hof_rewards_own_read"
    ON public.hall_of_fame_rewards FOR SELECT TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY "hof_rewards_admin"
    ON public.hall_of_fame_rewards FOR ALL
    USING (EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin'));

CREATE POLICY "hof_rewards_service"
    ON public.hall_of_fame_rewards FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);


-- ── 11. Verify ────────────────────────────────────────────────────────────────
SELECT 'feature_flags'                   AS tbl, COUNT(*) FROM public.feature_flags
UNION ALL
SELECT 'daily_checkins',                          COUNT(*) FROM public.daily_checkins
UNION ALL
SELECT 'free_side_credits',                       COUNT(*) FROM public.free_side_credits
UNION ALL
SELECT 'exclusive_spins',                         COUNT(*) FROM public.exclusive_spins
UNION ALL
SELECT 'event_ticket_tiers',                      COUNT(*) FROM public.event_ticket_tiers
UNION ALL
SELECT 'leaderboard_reward_fulfillments',         COUNT(*) FROM public.leaderboard_reward_fulfillments
UNION ALL
SELECT 'hall_of_fame_rewards',                    COUNT(*) FROM public.hall_of_fame_rewards
UNION ALL
SELECT 'system_settings (total)',                 COUNT(*) FROM public.system_settings;

COMMENT ON SCHEMA public IS 'Holy Grills public schema — run10 applied';
