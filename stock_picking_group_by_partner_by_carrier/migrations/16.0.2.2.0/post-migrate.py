# Copyright 2026 FactorLibre (https://factorlibre.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
# pylint: disable=odoo-addons-relative-import
# (migration scripts are loaded by path: a relative import is not possible)
from odoo import SUPERUSER_ID, api

from odoo.addons.stock_picking_group_by_partner_by_carrier.hooks import (
    backfill_sale_links,
)


def migrate(cr, version):
    # Databases where the module was installed without the post_init_hook.
    backfill_sale_links(api.Environment(cr, SUPERUSER_ID, {}))
