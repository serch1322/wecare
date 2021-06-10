# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields
from odoo.tests.common import TransactionCase


class HrEmployeeIDSE(TransactionCase):

    def setUp(self):
        super(HrEmployeeIDSE, self).setUp()
        self.env['hr.contract'].search([]).write({'state': 'draft'})
        self.contract = self.env.ref('hr_payroll.hr_contract_gilles_gravie')
        self.contract.state = 'open'

    def test_001_insured(self):
        """Generated TXT for insured"""
        self.contract._compute_integrated_salary()
        report = self.env['hr.idse.report']
        options = report._get_options()
        data = report.get_txt(options)
        self.assertEqual(
            data.replace('\n', ''),
            '1203256    12345678923DEMO                                                  MARC                       '
            '076648      100{date}T21  08     {id}          PUXB571021HNELXR009'.format(date=fields.datetime.strftime(
                self.contract.date_start, '%d%m%Y'), id=self.contract.employee_id.id), 'Error with IDSE generation')

    def test_002_baja(self):
        """Generated TXT for baja"""
        self.env['hr.departure.wizard'].create({
            'departure_reason': '1',
            'employee_id': self.contract.employee_id.id,
        }).action_register_departure()
        self.contract.employee_id.toggle_active()
        report = self.env['hr.idse.baja.report']
        options = report._get_options()
        data = report.get_txt(options)
        self.assertEqual(
            data.replace('\n', ''),
            '1203256    12345678923DEMO                                                  MARC                       '
            '000000000000000{date}     02     {id}         1                  9'.format(
                date=fields.datetime.strftime(self.contract.employee_id.departure_date, '%d%m%Y'),
                id=self.contract.employee_id.id), 'Error with IDSE generation')

    def test_003_wage(self):
        """Generated TXT for wage"""
        self.contract._compute_integrated_salary()
        report = self.env['hr.idse.wage.report']
        options = report._get_options()
        data = report.get_txt(options)
        messages = self.contract.message_ids.filtered(lambda m: m.message_type == 'notification')
        tracking = messages.sudo().mapped('tracking_value_ids').filtered(
            lambda t: t.field == 'l10n_mx_edi_sbc')
        self.assertEqual(
            data.replace('\n', ''),
            '1203256    12345678923DEMO                                                  MARC                       '
            '076648      100{date}     07     {id}          PUXB571021HNELXR009'.format(
                date=fields.datetime.strftime(tracking.sorted('create_date').create_date.date(), '%d%m%Y'),
                id=self.contract.employee_id.id), 'Error with IDSE generation')
