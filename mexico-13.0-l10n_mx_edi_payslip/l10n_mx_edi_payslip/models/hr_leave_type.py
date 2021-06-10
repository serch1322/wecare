
from odoo import fields, models


class HrWorkEntryType(models.Model):
    _inherit = 'hr.leave.type'

    l10n_mx_edi_payslip_use_calendar_days = fields.Boolean(
        'Use Calendar Days?',
        help="If True, the holiday's related will to consider the calendar days"
    )
