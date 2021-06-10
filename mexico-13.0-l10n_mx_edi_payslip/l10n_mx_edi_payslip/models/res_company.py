# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_mx_edi_minimum_wage = fields.Float(
        'Mexican minimum Wage',
        help='Indicates the current daily amount of the general minimum wage '
        'in Mexico')
    l10n_mx_edi_uma = fields.Float(
        'Mexican UMA', help='Indicates the current UMA in Mexico')
    l10n_mx_edi_umi = fields.Float(
        'Mexican UMI', help='Indicates the current UMI in Mexico')
    l10n_mx_edi_not_global_entry = fields.Boolean(
        'Not global entry?', help='If True, not will be generated a journal entry by month. (Odoo Process), will be '
        'generated a entry by each payslip.')
    l10n_mx_edi_dynamic_name = fields.Boolean(
        'Dynamic concepts?', help='If true, the payslip concepts based on inputs could be dynamic.\nFor example: '
        'If employee will to receive 100 MXN by concept of sale commissions, the commission input could have the '
        'name "Commissions for SO12345", and that name will be set on the CFDI.')
    l10n_mx_edi_vacation_bonus = fields.Selection([
        ('on_holidays', 'On Holidays'),
        ('on_anniversary', 'On Anniversary'),
        ('on_christmas_bonus', 'On Christmas'),
    ], 'Vacation Bonus', default='on_holidays', help='Indicate when the company will to pay the vacation bonus.')
    l10n_mx_edi_percentage_saving_fund = fields.Float(
        'Percentage of saving fund', help='If the company have the option to saving fund, indicate the percentage.')
    l10n_mx_edi_isr_annual_adjustment = fields.Boolean(
        'ISR Annual Adjustment?',
        help='If it is checked, the ISR calculation will not be adjusted in the last payroll of the month, it will '
             'be the same according to the corresponding table. You must make an annual ISR adjustment, since at '
             'the end of the year there may be differences between the effectively withheld ISR and the actual ISR.')
    l10n_mx_edi_payslip_email_alias = fields.Char(
        "Payslips Email Alias", help="Set a custom email alias for payslip. Your employees will receive their "
                                     "payslip from this alias.")
    l10n_mx_edi_payslip_email = fields.Char('Payslip Email Alias', compute="_compute_l10n_mx_edi_payslip_email",
                                            help="Custom Email to send payslip receipts")

    def _compute_l10n_mx_edi_payslip_email(self):
        for record in self:
            payslip_alias = record.l10n_mx_edi_payslip_email_alias
            alias_domain = self.env["ir.config_parameter"].sudo().get_param("mail.catchall.domain")
            email = '%s@%s' % (payslip_alias, alias_domain) if payslip_alias and alias_domain else ''
            record.l10n_mx_edi_payslip_email = email

    def write(self, values):
        """Inherit to update alimony for employees"""
        if 'l10n_mx_edi_uma' not in values and 'l10n_mx_edi_minimum_wage' not in values:
            return super(ResCompany, self).write(values)
        uma = self.l10n_mx_edi_uma
        vsm = self.l10n_mx_edi_minimum_wage
        res = super(ResCompany, self).write(values)
        if uma and uma != self.l10n_mx_edi_uma:
            factor = (self.l10n_mx_edi_uma - uma) / uma
            for ali in self.env['hr.employee.alimony'].search([('increase_based_on', '=', 'uma')]):
                ali.write({
                    'discount_amount': ali.discount_amount * (1 + factor),
                })
        if vsm and vsm != self.l10n_mx_edi_minimum_wage:
            factor = (self.l10n_mx_edi_minimum_wage - vsm) / vsm
            for ali in self.env['hr.employee.alimony'].search([('increase_based_on', '=', 'vsm')]):
                ali.write({
                    'discount_amount': ali.discount_amount * (1 + factor),
                })
        return res
