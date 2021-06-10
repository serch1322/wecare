# Part of Odoo. See LICENSE file for full copyright and licensing details.
from __future__ import division

from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from odoo import _, api, fields, models


class ReportPartnerLedger(models.AbstractModel):
    _name = "hr.alimony.report"
    _inherit = "account.report"
    _description = "Alimony report"

    filter_date = {'mode': 'range', 'filter': 'this_month'}
    filter_hierarchy = None

    def _get_columns_name(self, options):
        return [
            {},
            {'name': _('Employee Code')},
            {'name': _('VAT')},
            {'name': _('Payment Date'), 'class': 'date'},
            {'name': _('Total Perceptions'), 'class': 'number'},
            {'name': _('ISR'), 'class': 'number'},
            {'name': _('Alimony'), 'class': 'number'},
            {'name': _('Beneficiary')},
            {'name': _('Payment Way')},
        ]

    @api.model
    def _get_report_name(self):
        company = self.env.user.company_id
        vat = company.vat or ''
        return _('Alimony_%s_%s') % (vat, fields.date.today().strftime('%Y%m'))

    @api.model
    def _get_lines(self, options, line_id=None):
        lines = []
        total_perceptions = total_isr = total_alimony = 0
        date_from = fields.datetime.strptime(options['date']['date_from'], DEFAULT_SERVER_DATE_FORMAT).date()
        date_to = fields.datetime.strptime(options['date']['date_to'], DEFAULT_SERVER_DATE_FORMAT).date()
        slips = self.env['hr.payslip'].search([
            ('state', '=', 'done'),
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to)
        ], order="employee_id")
        percep = self.env.ref(
            'l10n_mx_edi_payslip.hr_salary_rule_category_perception_mx_taxed') | self.env.ref(
                'l10n_mx_edi_payslip.hr_salary_rule_category_perception_mx_exempt')

        alimony_rules = self.env.ref('l10n_mx_edi_payslip.hr_rule_l10n_mx_payroll_deduction_007')
        base_ref = "l10n_mx_edi_payslip.hr_rule_l10n_mx_payroll_deduction_007%s"
        alimony_refs = ['', '_b', '_c', '_d', '_e', '_f', '_a02', '_b02', '_c02']

        for alimony_ref in alimony_refs:
            alimony_rules += self.env.ref(base_ref % alimony_ref)

        last_employee = None
        for slip in slips:
            employee = slip.employee_id
            alimony = employee.l10n_mx_edi_alimony_ids.filtered(lambda a: a.date_from <= slip.date_from and (
                not a.date_to or a.date_to and a.date_to >= slip.date_to))
            count = 0
            for line in slip.line_ids.filtered(lambda l: l.amount and l.salary_rule_id in alimony_rules):
                if employee != last_employee:
                    last_employee = employee
                    lines.append({
                        'id': employee.id,
                        'name': employee.name,
                        'columns': [{'name': ''} for x in range(8)],
                        'level': 1,
                        'unfoldable': True,
                        'unfolded': True,
                    })

                line_columns = [
                    {'name': employee.barcode or employee.id},
                    {'name': employee.address_home_id.vat},
                    {'name': fields.datetime.strftime(slip.l10n_mx_edi_payment_date, '%d-%m-%Y')},
                    {'name': sum(slip.line_ids.filtered(lambda l: l.category_id in percep).mapped('amount'))},
                    {'name': abs(sum(slip.line_ids.filtered(
                        lambda l: l.salary_rule_id.l10n_mx_edi_code == '002').mapped('amount')))},
                    {'name': abs(line.amount)},
                    {'name': alimony[count].partner_id.name},
                    {'name': alimony[count].payment_method_id.name},
                ]
                total_perceptions += line_columns[3]['name']
                total_isr += line_columns[4]['name']
                total_alimony += line_columns[5]['name']
                count += 1
                lines.append({
                    'id': '02-%s' % employee.id,
                    'parent_id': employee.id,
                    'type': 'line',
                    'name': '',
                    'footnotes': {},
                    'columns': line_columns,
                    'level': 2,
                    'unfoldable': False,
                    'unfolded': True,
                    'colspan': 1,
                })
        total_columns = [
            {'name': ''},
            {'name': ''},
            {'name': None},
            {'name': round(total_perceptions, 2)},
            {'name': round(total_isr, 2)},
            {'name': round(total_alimony, 2)},
            {'name': ''},
            {'name': ''},
        ]
        lines.append({
            'id': 'totals',
            'type': 'line',
            'name': _('Total'),
            'level': 0,
            'class': 'hierarchy_total',
            'columns': total_columns,
            'footnotes': {},
        })
        return lines
