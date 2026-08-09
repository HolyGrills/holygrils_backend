-- Per-item HP multipliers and efficient menu review summaries.
-- Apply after the base menu, order, and review tables exist.

ALTER TABLE public.menu_items
    ADD COLUMN IF NOT EXISTS hp_multiplier NUMERIC(3,2) NOT NULL DEFAULT 1.0
    CHECK (hp_multiplier IN (0.5, 1.0, 2.0));

ALTER TABLE public.order_items
    ADD COLUMN IF NOT EXISTS hp_multiplier_snapshot NUMERIC(3,2) NOT NULL DEFAULT 1.0;

CREATE INDEX IF NOT EXISTS idx_order_items_menu_item_id
    ON public.order_items (menu_item_id);

CREATE INDEX IF NOT EXISTS idx_order_reviews_order_id
    ON public.order_reviews (order_id);

CREATE OR REPLACE FUNCTION public.get_menu_item_review_stats(p_item_ids UUID[])
RETURNS TABLE (
    menu_item_id UUID,
    avg_rating NUMERIC,
    review_count BIGINT
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    WITH item_orders AS (
        SELECT DISTINCT oi.menu_item_id, oi.order_id
        FROM public.order_items oi
        WHERE oi.menu_item_id = ANY(p_item_ids)
    )
    SELECT
        mi.id,
        COALESCE(ROUND(AVG(r.rating)::numeric, 1), 0::numeric),
        COUNT(DISTINCT r.id)
    FROM public.menu_items mi
    LEFT JOIN item_orders io
        ON io.menu_item_id = mi.id
    LEFT JOIN public.orders o
        ON o.id = io.order_id
       AND o.status = 'delivered'
    LEFT JOIN public.order_reviews r
        ON r.order_id = o.id
       AND r.rating IS NOT NULL
    WHERE mi.id = ANY(p_item_ids)
    GROUP BY mi.id;
$$;