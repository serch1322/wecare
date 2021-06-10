
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_mx_edi_minimum_wage = fields.Float(
        related='company_id.l10n_mx_edi_minimum_wage',
        string='Mexican minimum salary', readonly=False,
        help='Indicates the current daily amount of the general minimum wage '
        'in Mexico')
    l10n_mx_edi_uma = fields.Float(
        related='company_id.l10n_mx_edi_uma',
        string='Mexican UMA', readonly=False,
        help='Indicates the current UMA in Mexico')
    l10n_mx_edi_umi = fields.Float(
        related='company_id.l10n_mx_edi_umi',
        string='Mexican UMI', readonly=False, help='Indicates the current UMI in Mexico')
    l10n_mx_edi_not_global_entry = fields.Boolean(
        'Not global entry?', help='If True, not will be generated a journal entry by month. (Odoo Process), will be '
        'generated a entry by each payslip.', related='company_id.l10n_mx_edi_not_global_entry', readonly=False)
    l10n_mx_edi_dynamic_name = fields.Boolean(
        'Dynamic concepts?', readonly=False, related='company_id.l10n_mx_edi_dynamic_name',
        help='If true, the payslip concepts based on inputs could be dynamic.\nFor example: '
        'If employee will to receive 100 MXN by concept of sale commissions, the commission input could have the '
        'name "Commissions for SO12345", and that name will be set on the CFDI.')
    l10n_mx_edi_vacation_bonus = fields.Selection(
        'Vacation Bonus', readonly=False, related='company_id.l10n_mx_edi_vacation_bonus',
        help='Indicate when the company will to pay the vacation bonus.')
    l10n_mx_edi_percentage_saving_fund = fields.Float(
        'Percentage of saving fund', readonly=False, related='company_id.l10n_mx_edi_percentage_saving_fund',
        help='If the company have the option to saving fund, indicate the percentage.')
    l10n_mx_edi_isr_annual_adjustment = fields.Boolean(
        'ISR Annual Adjustment?', readonly=False, related='company_id.l10n_mx_edi_isr_annual_adjustment',
        help='If it is checked, the ISR calculation will not be adjusted in the last payroll of the month, it will '
             'be the same according to the corresponding table. You must make an annual ISR adjustment, since at '
             'the end of the year there may be differences between the effectively withheld ISR and the actual ISR.')
    l10n_mx_edi_payslip_email_alias = fields.Char(
        "Payslips Email Alias", readonly=False, related='company_id.l10n_mx_edi_payslip_email_alias',
        help="Set a custom email alias for payslip. Your employees will receive their payslip from this alias.")
