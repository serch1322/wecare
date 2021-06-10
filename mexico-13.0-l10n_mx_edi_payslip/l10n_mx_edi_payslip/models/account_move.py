
from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    l10n_mx_edi_payslip_line_ids = fields.Many2many(
        'hr.payslip.line',
        string="Payslip Line",
        readonly=True,
        copy=False,
        help="Payslip lines where the move line come from"
    )
