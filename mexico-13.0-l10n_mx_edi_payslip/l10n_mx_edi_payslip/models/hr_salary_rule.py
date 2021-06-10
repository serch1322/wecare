from odoo import fields, models


class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'

    l10n_mx_edi_code = fields.Char(
        'SAT Code', help='Code defined by the SAT catalog in this salary rule. It will be used on the CFDI.')
    l10n_mx_group_entry = fields.Boolean(
        'Group Entry Lines', default=True, help="If True, when a payslip batch is validated, all payslip lines using "
        "the rule will be grouped in just one journal item in the journal entry created by the batch(Odoo process).\n"
        "If False, when a payslip batch is validated, each payslip line using the rule will create its own journal "
        "item in the journal entry created.\n"
        "In either case, a reference between the journal items and the payslip lines will be generated.")


class HrPayrollStructureType(models.Model):
    _inherit = 'hr.payroll.structure.type'

    l10n_mx_edi_type = fields.Selection([
        ('O', 'Ordinary'),
        ('E', 'Extraordinary'),
    ], 'Payroll type', help="Value to assign in the attribute 'TipoNomina' in the CFDI.")
