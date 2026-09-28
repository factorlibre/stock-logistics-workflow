# Copyright 2026 FactorLibre (https://factorlibre.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import split_every

_logger = logging.getLogger(__name__)


def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    backfill_sale_links(env)


def backfill_sale_links(env):
    """Link the sale orders and transfers that existed before the installation.

    The module replaces the standard ``sale.order.picking_ids`` (one2many on
    ``stock.picking.sale_id``) by a many2many computed from
    ``move_ids.group_id.sale_ids``, and relies on ``stock.move.original_group_id``
    to cancel and merge moves. Both are only filled for records created once the
    module is installed, so on an existing database the older orders lose their
    transfers, their delivery status and the cancellation of their pending
    transfers.

    This fills them the way the module would have, only adding links.
    """
    cr = env.cr
    cr.execute(
        """
        INSERT INTO procurement_group_sale_order_rel
               (procurement_group_id, sale_order_id)
        SELECT id, sale_id FROM procurement_group WHERE sale_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
    _logger.info("Linked %d procurement groups to their sale order", cr.rowcount)
    # Merged groups are left out: their moves come from several groups and
    # they only exist once the module is installed.
    cr.execute(
        """
        UPDATE stock_move sm
           SET original_group_id = sm.group_id
          FROM procurement_group pg
         WHERE pg.id = sm.group_id
           AND pg.sale_id IS NOT NULL
           AND sm.original_group_id IS NULL
           AND NOT COALESCE(pg.is_merged, false)
        """
    )
    _logger.info("Set the original procurement group on %d moves", cr.rowcount)
    cr.execute(
        """
        INSERT INTO sale_order_stock_picking_rel (order_id, picking_id)
        SELECT DISTINCT r.sale_order_id, sm.picking_id
          FROM stock_move sm
          JOIN procurement_group_sale_order_rel r
            ON r.procurement_group_id = sm.group_id
         WHERE sm.picking_id IS NOT NULL
        ON CONFLICT DO NOTHING
        RETURNING order_id
        """
    )
    order_ids = sorted({row[0] for row in cr.fetchall()})
    _logger.info("Linked the transfers of %d sale orders", len(order_ids))
    # The links were written in SQL: recompute what depends on them
    # (delivery_status, effective_date...).
    env.invalidate_all()
    for batch in split_every(1000, order_ids):
        env["sale.order"].browse(batch).modified(["picking_ids"])
        env.flush_all()
        env.invalidate_all()
