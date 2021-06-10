from odoo import fields, models


class HrPayslipExtra(models.Model):
    _name = 'hr.payslip.extra'
    _description = 'Allow define many extra inputs in the payslips'
    _inherit = ['mail.thread']

    name = fields.Char(
        required=True, help='Indicate the name for this record, could be taken from the document origin',
        tracking=True, readonly=True, states={'draft': [('readonly', False)]})
    input_id = fields.Many2one(
        'hr.payslip.input.type', 'Input to define in the payslips',
        help='This input will be set on the payslip inputs for the employees related.',
        tracking=True, required=True, readonly=True, states={'draft': [('readonly', False)]})
    date = fields.Date(
        tracking=True, required=True, readonly=True, states={'draft': [('readonly', False)]},
        help='This extra will be paid on the payslip for this period')
    detail_ids = fields.One2many(
        'hr.payslip.extra.detail', 'extra_id',
        help='Indicate the employees to consider in this extra and the amount to each one.',
        readonly=True, states={'draft': [('readonly', False)]})
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
    ], help='The extra must be approved to allow pay this on the employee payslips',
        readonly=True, copy=False, default='draft', tracking=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True, default=lambda self: self.env.company)

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_cancel(self):
        self.write({'state': 'draft'})


class HrPayslipExtraDetail(models.Model):
    _name = 'hr.payslip.extra.detail'
    _description = 'Detail for each extra inputs'

    employee_id = fields.Many2one('hr.employee', 'Employee', required=True)
    amount = fields.Float()
    extra_id = fields.Many2one('hr.payslip.extra')
    detail = fields.Char(help='Indicate the detail for this input.\nExample: Commission SO1234')
