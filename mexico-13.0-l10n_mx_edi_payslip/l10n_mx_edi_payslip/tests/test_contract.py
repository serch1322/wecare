from odoo.tests.common import TransactionCase


class HRContract(TransactionCase):

    def test_001_gross_salary(self):
        """Ensure gross salary is correct"""
        contract = self.env.ref('hr_payroll.hr_contract_gilles_gravie')
        self.env['hr.contract.gross.salary'].with_context(active_ids=contract.ids).create(
            {'net_salary': 50000}).set_wage()
        self.assertEqual(contract.wage, 64599.22, 'Wage not assigned correctly.')

    def test_002_net_gross_salary(self):
        """Ensure that gross salary is calculated correctly"""
        contract = self.env.ref('hr_payroll.hr_contract_gilles_gravie')
        contract.company_id.l10n_mx_edi_minimum_wage = 102.68
        contract.company_id.l10n_mx_edi_uma = 84.49
        self.env['hr.contract.gross.salary'].with_context(active_ids=contract.ids).create({
            'net_salary': 50000,
        }).set_wage()
        self.assertEqual(contract.wage, 64599.22, 'Incorrect wage calculated')

    def test_003_net_gross_salary_imss(self):
        """Ensure that gross salary with IMSS is calculated correctly"""
        contract = self.env.ref('hr_payroll.hr_contract_gilles_gravie')
        contract.company_id.l10n_mx_edi_minimum_wage = 102.68
        contract.company_id.l10n_mx_edi_uma = 84.49
        self.env['hr.contract.gross.salary'].with_context(active_ids=contract.ids).create({
            'net_salary': 50000,
            'include_imss': True,
        }).set_wage()
        self.assertEqual(contract.wage, 67067.83, 'Incorrect wage calculated')

    def test_004_net_gross_salary_subsidy(self):
        """Ensure that gross salary with IMSS + subsidy is calculated correctly"""
        contract = self.env.ref('hr_payroll.hr_contract_gilles_gravie')
        contract.company_id.l10n_mx_edi_minimum_wage = 102.68
        contract.company_id.l10n_mx_edi_uma = 84.49
        self.env['hr.contract.gross.salary'].with_context(active_ids=contract.ids).create({
            'net_salary': 6000.00,
            'include_imss': True,
            'include_subsidy': True,
        }).set_wage()
        self.assertEqual(contract.wage, 6316.52, 'Incorrect wage calculated')
