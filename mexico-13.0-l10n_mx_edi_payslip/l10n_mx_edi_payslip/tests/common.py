
import os
import time

from lxml import objectify

from odoo.tests.common import TransactionCase


class PayrollTransactionCase(TransactionCase):
    def setUp(self):
        super(PayrollTransactionCase, self).setUp()
        self.uid = self.env.ref('l10n_mx_edi_payslip.payroll_mx_manager')
        self.payslip_obj = self.env['hr.payslip']
        self.allocation_obj = self.env['hr.leave.allocation']
        self.mail_obj = self.env['mail.compose.message']
        self.payslip_run_obj = self.env['hr.payslip.run']
        self.wizard_batch = self.env['hr.payslip.employees']
        self.employee = self.env.ref('hr.employee_qdp')
        self.contract = self.env.ref('hr_payroll.hr_contract_gilles_gravie')
        self.contract.action_update_current_holidays()
        self.contract._compute_integrated_salary()
        self.contract.compute_integrated_salary_variable()
        self.struct = self.env.ref(
            'l10n_mx_edi_payslip.payroll_structure_data_01')
        self.cat_excempt = self.env.ref(
            'l10n_mx_edi_payslip.hr_salary_rule_category_perception_mx_exempt')

        xml_expected_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), 'expected_cfdi.xml')
        xml_expected_f = open(xml_expected_path)
        self.xml_expected = objectify.parse(xml_expected_f).getroot()
        self.partnerc = self.env.user.company_id.partner_id
        self.env.user.company_id.write({
            'l10n_mx_edi_minimum_wage': 80.04,
            'l10n_mx_edi_fiscal_regime': '601',
        })
        self.journal_id = self.env['account.journal'].sudo().search([
            ('type', '=', 'general'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        self.journal_id.default_debit_account_id = self.env.ref('l10n_mx_edi_payslip.cuenta601_08')
        self.journal_id.default_credit_account_id = self.env.ref('l10n_mx_edi_payslip.cuenta601_08')

    def create_payroll(self, date_from=None, date_to=None):
        return self.payslip_obj.create({
            'name': 'Payslip Test',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'struct_id': self.struct.id,
            'l10n_mx_edi_source_resource': 'IP',
            'date_from': date_from or '%s-%s-01' % (time.strftime('%Y'), time.strftime('%m')),
            'date_to': date_to or '%s-%s-15' % (time.strftime('%Y'), time.strftime('%m')),
            'worked_days_line_ids': [(0, 0, {
                'name': 'Normal Working Days',
                'code': 'WORK100',
                'number_of_days': 15,
                'number_of_hours': 40,
                'contract_id': self.contract.id,
                'work_entry_type_id': self.ref(
                    'hr_work_entry.work_entry_type_attendance'),
            })],
            'input_line_ids': [(0, 0, {
                'amount': 200.0,
                'contract_id': self.contract.id,
                'input_type_id': self.ref(
                    'l10n_mx_edi_payslip.hr_payslip_input_type_perception_005_e'), # noqa
            }), (0, 0, {
                'amount': 300.0,
                'contract_id': self.contract.id,
                'input_type_id': self.ref(
                    'l10n_mx_edi_payslip.hr_payslip_input_type_other_payment_003'), # noqa
            })],
        })

    def remove_leaves(self):
        leaves = self.env['hr.leave'].search([('employee_id', '=', self.employee.id)])
        leaves.action_refuse()
        leaves.action_draft()
        leaves.unlink()

    def xml2dict(self, xml):
        """Receive 1 lxml etree object and return a dict string.
        This method allow us have a precise diff output"""
        def recursive_dict(element):
            return (element.tag,
                    dict(map(recursive_dict, element.getchildren()),
                         **element.attrib))
        return dict([recursive_dict(xml)])

    def assertEqualXML(self, xml_real, xml_expected):
        """Receive 2 objectify objects and show a diff assert if exists."""
        xml_expected = self.xml2dict(xml_expected)
        xml_real = self.xml2dict(xml_real)
        # noqa "self.maxDiff = None" is used to get a full diff from assertEqual method
        # This allow us get a precise and large log message of where is failing
        # expected xml vs real xml More info:
        # noqa https://docs.python.org/2/library/unittest.html#unittest.TestCase.maxDiff
        self.maxDiff = None
        self.assertEqual(xml_real, xml_expected)
