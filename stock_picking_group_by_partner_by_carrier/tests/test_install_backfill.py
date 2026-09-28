# Copyright 2026 FactorLibre (https://factorlibre.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo.tests.common import TransactionCase

from ..hooks import backfill_sale_links
from .common import TestGroupByBase


class TestInstallBackfill(TestGroupByBase, TransactionCase):
    """Sale orders confirmed before the module was installed."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse.delivery_steps = "pick_ship"

    def _get_old_sale_order(self, amount=10.0):
        """Confirm an order and strip what only the module fills, so it looks
        like one confirmed before the installation.

        Grouping is off while confirming: before the installation there are no
        merged procurement groups, every move stays in its sale order's group.
        """
        out_type = self.warehouse.out_type_id
        out_type.group_pickings = False
        sale = self._get_new_sale_order(amount=amount)
        sale.action_confirm()
        out_type.group_pickings = True
        self.assertFalse(sale.picking_ids.group_id.filtered("is_merged"))
        groups = sale.picking_ids.group_id
        pickings = sale.picking_ids
        self.env.flush_all()
        self.env.cr.execute(
            "DELETE FROM procurement_group_sale_order_rel "
            "WHERE procurement_group_id IN %s",
            (tuple(groups.ids),),
        )
        self.env.cr.execute(
            "DELETE FROM sale_order_stock_picking_rel WHERE order_id = %s",
            (sale.id,),
        )
        self.env.cr.execute(
            "UPDATE stock_move SET original_group_id = NULL WHERE group_id IN %s",
            (tuple(groups.ids),),
        )
        self.env.invalidate_all()
        self.assertFalse(sale.picking_ids)
        return sale, pickings

    def test_backfill_links_transfers(self):
        sale, pickings = self._get_old_sale_order()
        backfill_sale_links(self.env)
        self.assertEqual(sale.picking_ids, pickings)
        self.assertEqual(pickings.sale_ids, sale)
        self.assertEqual(pickings.move_ids.original_group_id, sale.procurement_group_id)

    def test_backfill_delivery_status(self):
        sale, pickings = self._get_old_sale_order()
        self._update_qty_in_location(self.warehouse.lot_stock_id, self.product, 10.0)
        backfill_sale_links(self.env)
        self.assertEqual(sale.delivery_status, "pending")
        for picking in pickings.sorted("id"):
            picking.action_assign()
            self._validate_transfer(picking)
        self.assertEqual(sale.delivery_status, "full")

    def test_backfill_cancel_sale_order(self):
        sale, pickings = self._get_old_sale_order()
        backfill_sale_links(self.env)
        sale._action_cancel()
        self.assertEqual(set(pickings.mapped("state")), {"cancel"})

    def test_backfill_decrease_quantity(self):
        """Decreasing the ordered quantity reduces the pending delivery instead
        of creating a return."""
        sale, pickings = self._get_old_sale_order(amount=10.0)
        backfill_sale_links(self.env)
        sale.order_line.product_uom_qty = 6.0
        out = pickings.filtered(lambda p: p.picking_type_id.code == "outgoing")
        self.assertFalse(
            sale.picking_ids.filtered(lambda p: p.picking_type_id.code == "incoming")
        )
        self.assertEqual(sum(out.move_ids.mapped("product_uom_qty")), 6.0)

    def test_backfill_idempotent(self):
        sale, pickings = self._get_old_sale_order()
        backfill_sale_links(self.env)
        backfill_sale_links(self.env)
        self.assertEqual(sale.picking_ids, pickings)
