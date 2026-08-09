-- Holy Grills: feature cleanup and frontend compatibility migration
-- Paste this entire file into the Supabase SQL Editor.
-- All statements are safe to run more than once.

-- Flash-sale fields consumed by GET /api/rewards.
ALTER TABLE public.rewards
    ADD COLUMN IF NOT EXISTS flash_enabled BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS flash_hp_cost INTEGER,
    ADD COLUMN IF NOT EXISTS flash_max_qty INTEGER,
    ADD COLUMN IF NOT EXISTS flash_slots_remaining INTEGER,
    ADD COLUMN IF NOT EXISTS flash_starts_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS flash_ends_at TIMESTAMPTZ;

-- Admin-configurable WhatsApp support settings.
INSERT INTO public.system_settings (key, value, description)
VALUES
    ('whatsapp_support_number', '"2348000000000"', 'Support WhatsApp number, Nigeria format, no plus sign'),
    ('whatsapp_support_enabled', 'true', 'Toggle floating WhatsApp support button visibility'),
    ('whatsapp_support_message', '"Hello I need help with my order"', 'Pre-filled WhatsApp support message')
ON CONFLICT (key) DO NOTHING;

-- Remove the old half-HP event value without enabling a multiplier unexpectedly.
UPDATE public.system_settings
SET value = '1', updated_at = NOW()
WHERE key = 'hp_multiplier' AND value IN ('0.5', '0.50');