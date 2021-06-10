
from odoo import fields, models, api


class HolidaysRequest(models.Model):
    _inherit = "hr.leave"

    l10n_mx_edi_payslip_no_enjoy_days = fields.Boolean(
        'Not Enjoy Days?',
        states={
            'cancel': [('readonly', True)],
            'refuse': [('readonly', True)],
            'validate1': [('readonly', True)],
            'validate': [('readonly', True)]},
        help='Is this time off beeing paid but not enjoyed?'
    )

    @api.onchange('date_from', 'date_to', 'employee_id', 'holiday_status_id')
    def _onchange_leave_dates(self):
        super(HolidaysRequest, self)._onchange_leave_dates()
        calendar_leaves = self.filtered(lambda h: h.holiday_status_id.l10n_mx_edi_payslip_use_calendar_days
                                        and h.date_from and h.date_to)
        for holiday in calendar_leaves:
            holiday.number_of_days = (holiday.date_to - holiday.date_from).days + 1
