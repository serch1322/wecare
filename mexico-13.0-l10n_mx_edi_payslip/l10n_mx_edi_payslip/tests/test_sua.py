# Part of Odoo. See LICENSE file for full copyright and licensing details.

import time

from odoo import fields
from odoo.tests.common import TransactionCase


class HrEmployeeSUA(TransactionCase):

    def setUp(self):
        super(HrEmployeeSUA, self).setUp()
        self.contract = self.env.ref('hr_payroll.hr_contract_gilles_gravie')
        self.contract.state = 'open'

    def test_001_insured(self):
        """Generated TXT for insured"""
        report = self.env['hr.sua.report']
        options = report._get_options()
        data = report.get_txt(options)
        self.assertEqual(
            data.replace('\n', ''),
            '1203256    12345678923VAAM130719H60PUXB571021HNELXR00DEMO$$MARC                                        '
            '10{date}007664812345            CREDIT 123{date}200020000'.format(date=fields.datetime.strftime(
                self.contract.date_start, '%d%m%Y')),
            'Error with SUA generation')

    def test_002_affiliation(self):
        """Generated TXT for affiliation"""
        report = self.env['hr.sua.affiliation.report']
        options = report._get_options()
        data = report.get_txt(options)
        self.assertEqual(
            data.replace('\n', ''),
            '1203256    1234567892337180                                 11T21EXPERIENCED M0',
            'Error with SUA generation')

    def test_003_mov(self):
        """Generated TXT for movements"""
        self.contract._compute_integrated_salary()
        # Cleaning not related leaves
        leaves = self.env['hr.leave'].search([
            ('employee_id', '=', self.env.ref('hr.employee_admin').id)])
        leaves.action_refuse()
        leaves.action_draft()
        # prepering Calendar days leaves
        sick_leave = self.env.ref('hr_holidays.hr_holidays_sl_qdp')
        sick_leave.holiday_status_id.l10n_mx_edi_payslip_use_calendar_days = True
        sick_leave._onchange_leave_dates()
        # Creating specific leave
        leave = self.env['hr.leave'].create({
            'holiday_type': 'employee',
            'employee_id': self.contract.employee_id.id,
            'holiday_status_id': self.env.ref('l10n_mx_edi_payslip.mexican_faltas_injustificadas').id,
            'request_date_from': '%s-%s-10' % (time.strftime('%Y'), time.strftime('%m')),
            'request_date_to': '%s-%s-13' % (time.strftime('%Y'), time.strftime('%m')),
            'number_of_days': 1,
            'date_from': '%s-%s-10' % (time.strftime('%Y'), time.strftime('%m')),
            'date_to': '%s-%s-13' % (time.strftime('%Y'), time.strftime('%m')),
        })
        leave._onchange_request_parameters()
        leave.action_approve()
        report = self.env['hr.sua.mov.report']
        options = report._get_options()
        data = report.get_txt(options)
        messages = self.contract.message_ids.filtered(lambda m: m.message_type == 'notification')
        tracking = messages.sudo().mapped('tracking_value_ids').filtered(
            lambda t: t.field == 'l10n_mx_edi_sbc')
        self.assertEqual(
            data, '1203256    1234567892307{date}        000076648\n'
            '1203256    1234567892311{date2}        0{days}0076648\n'
            '1203256    1234567892312{date3}SICK DAY030076648\n'.format(
                date=fields.datetime.strftime(tracking.sorted('create_date').create_date.date(), '%d%m%Y'),
                date2='10%s%s' % (time.strftime('%m'), time.strftime('%Y')),
                date3=fields.datetime.strftime(self.contract.date_start, '%d%m%Y'),
                days=int(leave.number_of_days)),
            'Error with SUA generation')
