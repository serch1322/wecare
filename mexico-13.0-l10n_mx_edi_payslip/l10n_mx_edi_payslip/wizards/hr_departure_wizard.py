from odoo import fields, models, _
from odoo.exceptions import UserError


class HrDepartureWizard(models.TransientModel):
    _inherit = 'hr.departure.wizard'

    departure_reason = fields.Selection(selection_add=[
        ('1', 'Contract End'),
        ('2', 'Voluntary separation'),
        ('3', 'Job Abandonment'),
        ('4', 'Death'),
        ('5', 'Closure'),
        ('6', 'Other')
    ], default="1")
    departure_date = fields.Date(required=True, default=fields.Date.today)
    set_date_end = fields.Boolean(string="Set Contract End Date", default=True)

    def action_register_departure(self):
        """Set departure_date on the employee and the contract
        If set_date_end is checked, set the departure date as the end date to current running contract,
        and cancel all draft contracts from odoo V14"""
        self.employee_id.departure_date = self.departure_date
        current_contract = self.employee_id.contract_id
        if current_contract and current_contract.date_start > self.departure_date:
            raise UserError(_("Departure date can't be earlier than the start date of current contract."))

        super(HrDepartureWizard, self).action_register_departure()
        if self.set_date_end:
            self.employee_id.contract_ids.filtered(lambda c: c.state == 'draft').write({'state': 'cancel'})
            if current_contract:
                self.employee_id.contract_id.write({'date_end': self.departure_date})
