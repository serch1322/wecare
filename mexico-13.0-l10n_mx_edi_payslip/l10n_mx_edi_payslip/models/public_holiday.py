
from datetime import time
from pytz import timezone

from odoo import fields, models, _
from odoo.exceptions import ValidationError


class L10nPublicHoliday(models.Model):
    _name = 'l10n_mx_edi.public.holiday'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = """Create Public holidays"""

    name = fields.Char('Reason', required=True, states={'validate': [('readonly', True)]}, tracking=True,
                       help="What is the public time off?")

    company_ids = fields.Many2many('res.company', default=lambda self: self.env.company, required=True,
                                   states={'validate': [('readonly', True)]},
                                   help="Which companies enjoy this public time off?")

    date = fields.Date(required=True, tracking=True, help="What day will be the time off?",
                       states={'validate': [('readonly', True)], 'reverted': [('readonly', True)]})

    state = fields.Selection([('draft', 'Draft'), ('validate', 'Approved')], default='draft',
                             required=True, tracking=True)

    def action_confirm(self):
        """Confirm public holiday, and create the global time off for the corresponding companies"""
        if not self.env.user.tz:
            raise ValidationError(_('Please, set you a timezone to continue this operation. To set a timezone, '
                                  'go to your user, on the upper right corner and select My Profile'))

        global_time_off_obj = self.env['create.company.global.time.off']
        work_entry_type_id = self.env.ref('l10n_mx_edi_payslip.work_entry_type_public_holiday_l10n_mx_payroll')

        for record in self:
            for company in record.company_ids:
                tz = timezone(self.env.user.tz)
                date_from = fields.datetime.combine(record.date, time(0, 0), tz)
                date_to = fields.datetime.combine(record.date, time(23, 59, 59), tz)
                date_from = date_from.astimezone().replace(tzinfo=None)
                date_to = date_to.astimezone().replace(tzinfo=None)
                vals = {
                    'name': record.name,
                    'company_id': company.id,
                    'work_entry_type_id': work_entry_type_id.id,
                    'date_from': date_from,
                    'date_to': date_to
                }
                global_time_off = global_time_off_obj.sudo().create(vals)
                global_time_off.sudo().action_confirm()
            record.state = 'validate'
