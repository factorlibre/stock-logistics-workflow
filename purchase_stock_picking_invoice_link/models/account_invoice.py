# Copyright 2019 Vicent Cubells <vicent.cubells@tecnativa.com>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import api, models


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    @api.model
    def _get_moves_from_po_line(self, purchase_line_id):
        moves = self.env["stock.move"]
        po_moves = self.env['stock.move'].search([
            ('purchase_line_id', '=', purchase_line_id),
        ])
        if 0 < len(po_moves):
            moves = po_moves._get_moves()
        return moves

    @api.onchange('invoice_line_ids')
    def onchange_invoice_lines_get_po_moves(self):
        pickings = self.env["stock.picking"]
        if "in_" in self.type:
            for line in self.invoice_line_ids:
                if line.purchase_line_id and not line.move_line_ids:
                    moves = self._get_moves_from_po_line(line.purchase_line_id.id)
                    moves = moves.filtered(lambda x: not x.invoice_line_ids)
                    line.move_line_ids = [(6, 0, moves.ids)]
                    pickings |= moves.mapped("picking_id")
            if pickings:
                self.picking_ids = [(6, 0, pickings.ids)]

    def purchase_order_change(self):
        res = super().purchase_order_change()
        self.onchange_invoice_lines_get_po_moves()
        return res

    @api.model
    def create(self, values):
        pickings = self.env['stock.picking']
        if 'invoice_line_ids' not in values or "in_" not in values.get("type", ""):
            return super().create(values)
        for item in values.get('invoice_line_ids'):
            if not item[2] or not item[2].get('purchase_line_id'):
                continue
            moves = self._get_moves_from_po_line(item[2]['purchase_line_id'])
            moves = moves.filtered(lambda x: not x.invoice_line_ids)
            item[2]['move_line_ids'] = [(6, 0, moves.ids)]
            pickings |= moves.mapped('picking_id')
        values['picking_ids'] = [(6, 0, pickings.ids)]
        return super().create(values)
