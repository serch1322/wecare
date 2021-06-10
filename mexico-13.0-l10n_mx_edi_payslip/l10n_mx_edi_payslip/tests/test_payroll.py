# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import unittest
import time
from datetime import datetime, timedelta, date
from datetime import time as dt_time

from lxml import etree, objectify

import odoo
from odoo.exceptions import UserError
from odoo.tests.common import Form

from .common import PayrollTransactionCase


class HRPayroll(PayrollTransactionCase):

    def test_001_xml_structure(self):
        """Use XML expected to verify that is equal to generated. And SAT
        status"""
        self.contract.l10n_mx_edi_schedule_pay = '04'
        self.employee.sudo().contract_id = self.contract
        payroll = self.create_payroll()
        self.env['hr.payslip.overtime'].create({
            'employee_id': self.employee.id,
            'name': '%s-%s-01' % (time.strftime('%Y'), time.strftime('%m')),
            'hours': 1,
        })
        payroll.compute_sheet()
        payroll.action_payslip_done()
        self.assertEqual(payroll.l10n_mx_edi_pac_status, 'signed', payroll.message_ids.mapped('body'))
        payroll.l10n_mx_edi_update_sat_status()
        self.assertEqual(payroll.l10n_mx_edi_sat_status, 'not_found')
        xml = payroll.l10n_mx_edi_get_xml_etree()
        self.xml_expected.attrib['Fecha'] = xml.attrib['Fecha']
        self.xml_expected.attrib['Folio'] = xml.attrib['Folio']
        self.xml_expected.attrib['Sello'] = xml.attrib['Sello']
        node_payroll = payroll.l10n_mx_edi_get_payroll_etree(xml)
        node_expected = payroll.l10n_mx_edi_get_payroll_etree(
            self.xml_expected)
        self.assertTrue(node_payroll, 'Complement to payroll not added.')
        node_expected.Receptor.attrib['FechaInicioRelLaboral'] = node_payroll.Receptor.attrib['FechaInicioRelLaboral']  # noqa
        node_expected.attrib['FechaFinalPago'] = node_payroll.attrib['FechaFinalPago']  # noqa
        node_expected.attrib['FechaInicialPago'] = node_payroll.attrib['FechaInicialPago']  # noqa
        node_expected.attrib['FechaPago'] = node_payroll.attrib['FechaPago']
        node_expected.Receptor.attrib[u'Antig\xfcedad'] = node_payroll.Receptor.attrib[u'Antig\xfcedad']  # noqa

        # Replace node TimbreFiscalDigital
        tfd_expected = self.payslip_obj.l10n_mx_edi_get_tfd_etree(
            self.xml_expected)
        tfd_xml = objectify.fromstring(etree.tostring(
            self.payslip_obj.l10n_mx_edi_get_tfd_etree(xml)))
        self.xml_expected.Complemento.replace(tfd_expected, tfd_xml)
        self.assertEqualXML(xml, self.xml_expected)

    def test_002_perception_022(self):
        """When perception code have 022, the payroll have node
        SeparacionIndemnizacion."""
        self.struct = self.env.ref(
            'l10n_mx_edi_payslip.payroll_structure_data_03')
        payroll = self.create_payroll()
        date_start = payroll.l10n_mx_edi_payment_date - timedelta(days=380)
        self.contract.write({
            'date_start': date_start,
        })
        payroll.compute_sheet()
        payroll.action_payslip_done()
        self.assertEqual(payroll.l10n_mx_edi_pac_status, 'signed', payroll.message_ids.mapped('body'))

    def test_003_perception_039(self):
        """When perception code have 039, the payroll have node
        JubilacionPensionRetiro."""
        payroll = self.create_payroll()
        payroll.write({
            'input_line_ids': [(0, 0, {
                'code': 'pe_039',
                'name': u'Jubilaciones, pensiones o haberes de retiro',
                'amount': 1000.0,
                'contract_id': self.contract.id,
                'input_type_id': self.ref(
                    'l10n_mx_edi_payslip.hr_payslip_input_type_perception_039_e') # noqa
            })],
        })
        payroll.compute_sheet()
        payroll.action_payslip_done()
        self.assertEqual(payroll.l10n_mx_edi_pac_status, 'signed', payroll.message_ids.mapped('body'))

    def test_004_other_payment_004(self):
        """When other payment have the code 004, this must have node
        CompensacionSaldosAFavor."""
        payroll = self.create_payroll()
        payroll.write({
            'input_line_ids': [(0, 0, {
                'code': 'op_004',
                'name': u'Aplicación de saldo a favor por compensación anual.',
                'amount': 500.0,
                'contract_id': self.contract.id,
                'input_type_id': self.ref(
                    'l10n_mx_edi_payslip.hr_payslip_input_type_other_payment_004'), # noqa
            })],
            'l10n_mx_edi_balance_favor': 500.0,
            'l10n_mx_edi_comp_year': (datetime.today()).year - 1,
            'l10n_mx_edi_remaining': 500.0,
        })
        payroll.compute_sheet()
        payroll.action_payslip_done()
        self.assertEqual(payroll.l10n_mx_edi_pac_status, 'signed', payroll.message_ids.mapped('body'))

    def test_005_perception_045(self):
        """When one perception have the code 045, this must have node
        AccionesOTitulos,."""
        payroll = self.create_payroll()
        payroll.write({
            'input_line_ids': [(0, 0, {
                'code': 'pe_045',
                'name': u'Ingresos en acciones o títulos valor que representan bienes',  # noqa
                'amount': 500.0,
                'contract_id': self.contract.id,
                'input_type_id': self.ref(
                    'l10n_mx_edi_payslip.hr_payslip_input_type_perception_045_e'), # noqa
            })],
            'l10n_mx_edi_action_title_ids': [(0, 0, {
                'category_id': self.cat_excempt.id,
                'market_value': 100.0,
                'price_granted': 100.0,
            })]
        })
        payroll.compute_sheet()
        payroll.action_payslip_done()
        self.assertEqual(payroll.l10n_mx_edi_pac_status, 'signed', payroll.message_ids.mapped('body'))

    @unittest.skip('Check PDF Format')
    def test_006_print_pdf(self):
        """Verify that PDF is generated"""
        # TODO: check this test
        payroll = self.create_payroll()
        payroll.compute_sheet()
        payroll.action_payslip_done()
        self.assertEqual(payroll.l10n_mx_edi_pac_status, 'signed', payroll.message_ids.mapped('body'))
        report = odoo.report.render_report(
            self.cr, self.uid, payroll.ids, 'hr_payroll.report_payslip',
            {'model': 'hr.payslip'}, context=self.env.context)
        self.assertTrue(report, 'Report not generated.')

    def test_007_cancel_xml(self):
        """Verify that XML is cancelled"""
        payroll = self.create_payroll()
        payroll.action_payslip_cancel()
        payroll.action_payslip_draft()
        payroll.compute_sheet()
        payroll.action_payslip_done()
        self.assertEquals(payroll.l10n_mx_edi_pac_status, 'signed',
                          payroll.message_ids.mapped('body'))
        payroll._compute_cfdi_values()
        payroll.action_payslip_cancel()
        self.assertTrue(
            payroll.l10n_mx_edi_pac_status in ('to_cancel', 'cancelled'), payroll.message_ids.mapped('body'))

    @unittest.skip('Check PDF Format')
    def test_008_send_payroll_mail(self):
        """Verify that XML is attach on wizard that send mail"""
        # TODO: check this test
        payroll = self.create_payroll()
        payroll.compute_sheet()
        payroll.action_payslip_done()
        mail_data = payroll.action_payroll_sent()
        template = mail_data.get('context', {}).get('default_template_id', [])
        template = self.env['mail.template'].browse(template)
        mail = template.generate_email(payroll.ids)
        self.assertEquals(len(mail[payroll.id].get('attachments')), 2,
                          'Documents not attached')

    def test_009_batches(self):
        """Verify payroll information and confirm payslips from batches"""
        payment_date = (datetime.today() + timedelta(days=5)).strftime('%Y-%m-%d')
        self.contract.state = 'open'
        payslip_run = self.payslip_run_obj.create({
            'name': 'Payslip VX',
            'l10n_mx_edi_payment_date': payment_date,
        })
        self.wizard_batch.create({
            'employee_ids': [(6, 0, self.employee.ids)],
            'structure_id': self.struct.id,
        }).with_context(active_id=payslip_run.id).compute_sheet()
        self.assertEquals(
            payslip_run.slip_ids.l10n_mx_edi_payment_date.strftime('%Y-%m-%d'),
            payment_date, 'Payment date not assigned in the payroll created.')
        payslip_run.action_validate()
        payslip_run.action_payslips_done()
        self.assertEquals(
            payslip_run.slip_ids.l10n_mx_edi_pac_status, 'signed',
            payslip_run.slip_ids.message_ids.mapped('body'))

    def test_010_aguinaldo(self):
        """When in payslip has a perception of Christmas bonuses (Aguinaldo)"""
        self.struct = self.env.ref(
            'l10n_mx_edi_payslip.payroll_structure_data_02')
        payroll = self.create_payroll()
        start_date = payroll.l10n_mx_edi_payment_date - timedelta(days=380)
        self.contract.write({
            'date_start': start_date,
        })
        payroll.compute_sheet()
        payroll.action_payslip_done()
        self.assertEquals(payroll.l10n_mx_edi_pac_status, 'signed',
                          payroll.message_ids.mapped('body'))
        xml = payroll.l10n_mx_edi_get_xml_etree()
        node_payroll = payroll.l10n_mx_edi_get_payroll_etree(xml)
        self.assertEquals(
            '11000.00', node_payroll.get('TotalPercepciones', ''))

    def test_011_onchange_employee(self):
        """check if the company_id is set with onchange_employee"""
        # TODO: Review onchange method to only update the company when employee
        # has the company set.
        company2 = self.env['res.company'].sudo().create({'name': 'Company2'})
        company3 = self.env['res.company'].sudo().create({'name': 'Company3'})
        self.employee.sudo().company_id = company2
        self.contract.company_id = company3
        payroll = self.create_payroll()
        payroll._onchange_employee()
        # payroll company is the same that employee
        self.assertEquals(payroll.company_id, company2, 'Company is not the employee company')
        self.employee.sudo().company_id = company3
        payroll._onchange_employee()
        # payroll company is the same that contract
        self.assertEquals(payroll.company_id, company3, 'Company is not the contract company')
        self.employee.sudo().company_id = self.env.user.company_id
        payroll._onchange_employee()
        # payroll company is the default company
        self.assertEqual(payroll.company_id, self.env.user.company_id, 'Company is not the default company')

    def test_012_resign_process(self):
        """Tests the re-sign process (recovery a previously signed xml)
        """
        payroll = self.create_payroll()
        payroll.compute_sheet()
        payroll.action_payslip_done()
        self.assertEqual(payroll.l10n_mx_edi_pac_status, 'signed',
                         payroll.message_ids.mapped('body'))
        payroll.l10n_mx_edi_pac_status = 'retry'
        payroll.l10n_mx_edi_update_pac_status()
        for _x in range(10):
            if payroll.l10n_mx_edi_pac_status == 'signed':
                break
            time.sleep(2)
            payroll.l10n_mx_edi_retrieve_last_attachment().unlink()
            payroll.l10n_mx_edi_update_pac_status()
        self.assertEqual(payroll.l10n_mx_edi_pac_status, 'signed',
                         payroll.message_ids.mapped('body'))
        xml_attachs = payroll.l10n_mx_edi_retrieve_attachments()
        self.assertEqual(len(xml_attachs), 2)
        xml_1 = objectify.fromstring(base64.b64decode(xml_attachs[0].datas))
        xml_2 = objectify.fromstring(base64.b64decode(xml_attachs[1].datas))
        self.assertEqualXML(xml_1, xml_2)

    def test_013_assimilated(self):
        """Tests case when the employee is assimilated"""
        payroll = self.create_payroll()
        payroll.employee_id.sudo().l10n_mx_edi_is_assimilated = True
        payroll.employee_id.sudo().l10n_mx_edi_contract_regime_type = '09'
        payroll.contract_id.sudo().l10n_mx_edi_contract_type = '99'
        payroll.compute_sheet()
        payroll.action_payslip_done()
        self.assertEqual(payroll.l10n_mx_edi_pac_status, 'signed',
                         payroll.message_ids.mapped('body'))

    def test_014_inabilities(self):
        """Ensure that inabilities are created"""
        self.remove_leaves()
        leave = self.env['hr.leave'].create({
            'holiday_type': 'employee',
            'employee_id': self.employee.id,
            'holiday_status_id': self.env.ref('l10n_mx_edi_payslip.mexican_maternity').id,
            'date_from': '%s-%s-01' % (time.strftime('%Y'), time.strftime('%m')),
            'date_to': '%s-%s-03' % (time.strftime('%Y'), time.strftime('%m')),
        })
        leave.action_approve()
        payroll = self.create_payroll()
        self.contract.state = 'open'
        payroll = self.create_payroll()
        payroll.worked_days_line_ids.unlink()
        payroll._onchange_employee()
        payroll.compute_sheet()
        payroll.action_payslip_done()
        xml = payroll.l10n_mx_edi_get_xml_etree()
        self.assertEqual(
            '03', payroll.l10n_mx_edi_get_payroll_etree(xml).Incapacidades.Incapacidad.get('TipoIncapacidad'),
            'Inability not added.')

    def test_015_inabilities(self):
        """Ensure that inabilities are created"""
        self.remove_leaves()
        leave = self.env['hr.leave'].create({
            'holiday_type': 'employee',
            'employee_id': self.employee.id,
            'holiday_status_id': self.env.ref('l10n_mx_edi_payslip.mexican_riesgo_de_trabajo').id,
            'date_from': '%s-%s-01' % (time.strftime('%Y'), time.strftime('%m')),
            'date_to': '%s-%s-03' % (time.strftime('%Y'), time.strftime('%m')),
        })
        leave.action_approve()
        payroll = self.create_payroll()
        payroll.worked_days_line_ids.unlink()
        payroll._onchange_employee()
        payroll.compute_sheet()
        payroll.action_payslip_done()
        xml = payroll.l10n_mx_edi_get_xml_etree()
        self.assertEqual(
            '01', payroll.l10n_mx_edi_get_payroll_etree(xml).Incapacidades.Incapacidad.get('TipoIncapacidad'),
            'Inability not added.')

    def test_016_inabilities(self):
        """Ensure that inability for 'Enfermedad General' created"""
        self.remove_leaves()
        leave = self.env['hr.leave'].create({
            'holiday_type': 'employee',
            'employee_id': self.employee.id,
            'holiday_status_id': self.env.ref('l10n_mx_edi_payslip.mexican_enfermedad_general').id,
            'date_from': '%s-%s-01' % (time.strftime('%Y'), time.strftime('%m')),
            'date_to': '%s-%s-07' % (time.strftime('%Y'), time.strftime('%m')),
        })
        leave.action_approve()
        payroll = self.create_payroll()
        payroll.worked_days_line_ids.unlink()
        payroll._onchange_employee()
        payroll.compute_sheet()
        payroll.action_payslip_done()
        xml = payroll.l10n_mx_edi_get_xml_etree()
        self.assertEqual(
            '02', payroll.l10n_mx_edi_get_payroll_etree(xml).Incapacidades.Incapacidad.get('TipoIncapacidad'),
            'Inability not added.')

    def test_017_inabilities(self):
        """Ensure that inability for 'Hijos con Cancer' is created"""
        self.remove_leaves()
        leave = self.env['hr.leave'].create({
            'holiday_type': 'employee',
            'employee_id': self.employee.id,
            'holiday_status_id': self.env.ref('l10n_mx_edi_payslip.mexican_licencia_padres_hijo_cancer').id,
            'date_from': '%s-%s-01' % (time.strftime('%Y'), time.strftime('%m')),
            'date_to': '%s-%s-03' % (time.strftime('%Y'), time.strftime('%m')),
        })
        leave.action_approve()
        payroll = self.create_payroll()
        payroll.worked_days_line_ids.unlink()
        payroll._onchange_employee()
        payroll.compute_sheet()
        payroll.action_payslip_done()
        xml = payroll.l10n_mx_edi_get_xml_etree()
        self.assertEqual(
            '04', payroll.l10n_mx_edi_get_payroll_etree(xml).Incapacidades.Incapacidad.get('TipoIncapacidad'),
            'Inability not added.')

    def test_018_get_dates_on_datetime(self):
        """Ensure payslips dates are converted correctly to employee timezones"""
        self.employee.sudo().tz = "America/Mazatlan"
        payroll = self.create_payroll(date(2020, 11, 16), date(2020, 11, 30))
        date_from, date_to = payroll._get_dates_on_datetime()
        self.assertEqual(date_from, datetime(2020, 11, 16, 7, 6), 'Date from incorrectly converted')
        self.assertEqual(date_to, datetime(2020, 12, 1, 7, 5, 59), 'Date to incorrectly converted')

    def test_019_public_time_off_creation(self):
        """Correct creation of public time off"""
        # TODO: Expand this test, cover payslip affectations
        self.env.user.tz = "America/Denver"
        public_holiday = self.env['l10n_mx_edi.public.holiday'].create({
            "name": 'Thanksgiving',
            "date": date.today(),
        })
        public_holiday.action_confirm()
        self.assertEqual(public_holiday.state, 'validate', 'Public Holiday not Validated')
        global_leave = self.env['resource.calendar.leaves'].search([('name', '=', 'Thanksgiving')])[0]
        self.assertTrue(global_leave, 'Global leave not created')
        expected_date_from = datetime.combine(date.today(), dt_time(7, 0))
        self.assertEqual(global_leave.date_from, expected_date_from, 'Incorrect Date To on Leave')
        expected_date_to = expected_date_from + timedelta(days=1, seconds=-1)
        self.assertEqual(global_leave.date_to, expected_date_to, 'Incorrect Date from on Leave')

    def test_020_onchange_date_errors(self):
        payroll = self.create_payroll()
        payroll.compute_sheet()
        # Attendences to check salary rules prima dominical, septimo dia and dias de descanso trabajados
        for num in range(1, 8):
            self.env['hr.attendance'].create({
                'employee_id': self.employee.id,
                'check_in': datetime.combine(payroll.date_from.replace(day=num), dt_time(12, 0)),
                'check_out': datetime.combine(payroll.date_from.replace(day=num), dt_time(23, 59, 59)),
            })
        # Test Onchange date errors
        form = Form(payroll)
        form.date_to = payroll.date_to - timedelta(days=1)

    def test_021_allow_validate_payslip(self):
        """Test case when an employee """
        payroll = self.create_payroll()
        payroll.compute_sheet()
        # remove permission group to perform the test
        group_e = self.env.ref('l10n_mx_edi_payslip.allow_validate_payslip', False)
        group_e.sudo().write({'users': [(3, self.env.user.id)]})
        msg = "Only Managers who are allow to validate payslip can perform this operation"
        with self.assertRaises(UserError, msg=msg):
            payroll.action_payslip_done()
        # Get back permission group and finish to test normal flow
        group_e.sudo().write({'users': [(4, self.env.user.id)]})
        payroll.action_payslip_done()

    def test_022_alimony(self):
        """Test case whit alimony in the employee"""
        self.employee.sudo().l10n_mx_edi_alimony_ids = [(0, 0, {
            'name': 'Percentage over salary',
            'number': '1',
            'discount_type': 'percentage_wage',
            'discount_amount': 1,
            'date_from': '%s-%s-01' % (time.strftime('%Y'), time.strftime('%m')),
        }), (0, 0, {
            'name': 'Percentage over perceptions less ISR and SS',
            'number': '2',
            'discount_type': 'percentage_perceptions_ISR',
            'discount_amount': 1,
            'date_from': '%s-%s-01' % (time.strftime('%Y'), time.strftime('%m')),
        }), (0, 0, {
            'name': 'Amount fixed',
            'number': '3',
            'discount_type': 'amount_fixed',
            'discount_amount': 100,
            'date_from': '%s-%s-01' % (time.strftime('%Y'), time.strftime('%m')),
        }), (0, 0, {
            'name': 'Percentage over net',
            'number': '4',
            'discount_type': 'percentage_over_net',
            'discount_amount': 1,
            'date_from': '%s-%s-01' % (time.strftime('%Y'), time.strftime('%m')),
        }), (0, 0, {
            'name': 'Percentage over perceptions',
            'number': '5',
            'discount_type': 'percentage_perceptions',
            'discount_amount': 1,
            'date_from': '%s-%s-01' % (time.strftime('%Y'), time.strftime('%m')),
        }), (0, 0, {
            'name': 'Percentage over perceptions less ISR and Mortgages',
            'number': '6',
            'discount_type': 'percentage_perceptions_ISR_mortgages',
            'discount_amount': 1,
            'date_from': '%s-%s-01' % (time.strftime('%Y'), time.strftime('%m')),
        })]
        payroll = self.create_payroll()
        payroll.compute_sheet()
        payroll.action_payslip_done()
        self.assertEqual(payroll.l10n_mx_edi_pac_status, 'signed', payroll.message_ids.mapped('body'))
        # Test Report
        report = self.env['hr.alimony.report']
        options = report._get_options()
        total_line = report._get_lines(options)[-1]
        self.assertEqual(total_line['name'], 'Total', 'The last line must be the Total')
        total_perceptions = total_line['columns'][3]['name']
        total_isr = total_line['columns'][4]['name']
        total_alimony = total_line['columns'][5]['name']
        self.assertEqual(total_perceptions, 67200.0, 'Total Perceptions must be 67200.0')
        self.assertEqual(total_isr, 9831.42, 'Total Isr must be 9831.42')
        self.assertEqual(total_alimony, 588.75, 'Total Alimony must be 588.75')

    def test_023_mexican_holiday_allocation(self):
        """Test the cron for automatic Mexican Holiday allocation
        Create an allocation that is the allocation from the last year.
        Call the cron to create the new allocation.
        Check that the last year allocation now is refuse
        Check if now there are two allocations, the another one is not related so should be there.
        Check the new year allocation."""
        holiday = self.env.ref('l10n_mx_edi_payslip.mexican_holiday')
        date_mx = self.env['l10n_mx_edi.certificate'].sudo().get_mx_current_datetime().date()
        self.contract.state = 'open'
        self.contract.date_start = date_mx.replace(year=date_mx.year-1)

        # Create an allocation for the last year
        old_allocation = self.allocation_obj.create({
            'name': date_mx.year - 1,
            'holiday_status_id': holiday.id,
            'number_of_days': 5,
            'holiday_type': 'employee',
            'employee_id': self.employee.id,
            'state': 'draft',
        })
        old_allocation.action_confirm()
        old_allocation.action_approve()

        # Use Cron, update the holidays. The old allocation should be refused
        self.env.ref('l10n_mx_edi_payslip.ir_cron_create_mx_allocation').sudo().method_direct_trigger()
        self.assertEqual(old_allocation.state, 'refuse', 'The allocation should be refuse')

        allocations = self.allocation_obj.search([('employee_id', '=', self.employee.id), ('state', '=', 'validate')])

        # Two allocations because there is another one created by data, that one is representing
        # an allocation that should not be refused, that is why this line is covered
        self.assertEqual(len(allocations), 2, 'There should be Two Allocations')
        self.assertEqual(allocations[0].state, 'validate', 'The allocation created by the cron should be validated')
        self.assertEqual(allocations[0].name, str(date_mx.year),
                         'The allocation created by the cron should be named as the actual year')

    def test_024_extra_dinamic_concepts_cfdi(self):
        """Check dinamic concepts on cfdi"""
        self.contract.state = 'open'
        payroll = self.create_payroll()
        payroll.compute_sheet()
        input_type_id = self.env.ref('l10n_mx_edi_payslip.hr_payslip_input_type_perception_028_g')
        extras = self.env['hr.payslip.extra'].create({
            'name': 'Payslip Extras Test',
            'input_id': input_type_id.id,
            'date': payroll.date_to,
            'detail_ids': [(0, 0, {
                'employee_id': self.employee.id,
                'amount': 3255.0,
                'detail': 'Commission ABC',
            }), (0, 0, {
                'employee_id': self.employee.id,
                'amount': 1520.0,
                'detail': 'Commission DEF',
            })],
        })
        extras.action_approve()
        payroll.l10n_mx_edi_update_extras()
        input_line = payroll.input_line_ids.filtered(lambda l, code=input_type_id.code: l.code == code)
        self.assertTrue(input_line, 'The input for Commission was not created')
        code = input_line[0].code
        code = '%s%s' % (code.split('_')[0].upper(), code.split('_')[1])
        payslip_line = payroll.line_ids.filtered(lambda l, code=code: l.code == code)
        self.assertEquals(payslip_line.amount, 4775.0, 'The commision payslip line amount must be 4775.0')
        # Check l10n_mx_edi_dynamic_name
        self.assertEquals(payslip_line.name, payroll.l10n_mx_edi_name(payslip_line),
                          'The name returned name must be the normal line name')
        # Activate l10n_mx_edi_dynamic_name
        payroll.company_id.sudo().l10n_mx_edi_dynamic_name = True
        expected_name = '%s: %s' % (payslip_line.name, ', '.join(extras.detail_ids.mapped('detail')))
        self.assertEquals(expected_name, payroll.l10n_mx_edi_name(payslip_line),
                          'The name returned name must be %s' % expected_name)
        # Check the line string on the CFDI
        payroll.action_payslip_done()
        self.assertEqual(payroll.l10n_mx_edi_pac_status, 'signed', payroll.message_ids.mapped('body'))
        xml = payroll.l10n_mx_edi_get_xml_etree()
        node_payroll = payroll.l10n_mx_edi_get_payroll_etree(xml)
        # This is always the last because is the last input_line created
        commission_node = node_payroll.Percepciones.Percepcion[-1]
        self.assertEquals(expected_name, commission_node.attrib['Concepto'],
                          'The name returned name must be %s' % expected_name)

        # Check when the extras have not details string
        new_payroll = payroll.copy()
        extras.action_cancel()
        extras.mapped('detail_ids').write({'detail': False})
        extras.action_approve()
        new_payroll.l10n_mx_edi_update_extras()
        new_payroll.action_payslip_done()
        self.assertEqual(new_payroll.l10n_mx_edi_pac_status, 'signed', new_payroll.message_ids.mapped('body'))

    def test_025_out_of_contract(self):
        """Test out of contract worked days and recompute worked days method"""
        self.remove_leaves()
        payroll = self.create_payroll()
        # Check the contract starts much time before
        self.contract.date_start = payroll.date_from - timedelta(days=405)
        self.contract.date_end = payroll.date_to - timedelta(days=5)
        self._check_out_of_contract_config(payroll, 5)
        # Check the contract starts after payslip period and has no end
        self.contract.date_start = payroll.date_from + timedelta(days=5)
        self.contract.date_end = False
        self._check_out_of_contract_config(payroll, 5)
        # Check the contract starts after payslip period and has end after payslip period
        self.contract.date_start = payroll.date_from + timedelta(days=5)
        self.contract.date_end = payroll.date_to + timedelta(days=35)
        self._check_out_of_contract_config(payroll, 5)
        # Check if the contract ends before the period
        self.contract.date_start = payroll.date_from
        self.contract.date_end = payroll.date_to - timedelta(days=5)
        self._check_out_of_contract_config(payroll, 5)
        # Check if the contract starts after payslip period and ends before the period
        self.contract.date_start = payroll.date_from + timedelta(days=3)
        self.contract.date_end = payroll.date_to - timedelta(days=3)
        self._check_out_of_contract_config(payroll, 6)

    def _check_out_of_contract_config(self, payroll, expected_out_of_contract_days, expected_lines=2):
        total_period_days = (payroll.date_to - payroll.date_from).days + 1
        payroll.action_refresh_from_work_entries()
        worked_lines = payroll.worked_days_line_ids
        self.assertEqual(len(worked_lines), expected_lines, '%d Lines expected' % expected_lines)
        self.assertEqual(sum(worked_lines.mapped('number_of_days')), total_period_days,
                         'The total sum of number of days must be the total of days in the period, %d days' %
                         total_period_days)
        self.assertTrue(len(worked_lines.mapped('name')) == len(set(worked_lines.mapped('name'))),
                        'No concept should be repeated in worked days lines')
        self.assertFalse([item for item in worked_lines.mapped('number_of_days') if item < 1],
                         'There should be no lines with negative or zero days in the worked days')
        out_contract_line = worked_lines.filtered(lambda w: w.name == 'Out of Contract')
        self.assertTrue(out_contract_line, 'There must be an Out of Contract line')
        self.assertEqual(out_contract_line.number_of_days, expected_out_of_contract_days,
                         'There must be %s days out of contract' % expected_out_of_contract_days)

    def test_base_finiquito(self):
        """Ensure that structure base + finiquito is executed correctly."""
        self.struct = self.env.ref('l10n_mx_edi_payslip.payroll_structure_data_06')
        payroll = self.create_payroll()
        date_start = payroll.l10n_mx_edi_payment_date - timedelta(days=380)
        self.contract.write({
            'date_start': date_start,
        })
        payroll.compute_sheet()
        payroll.action_payslip_done()
        self.assertEqual(payroll.l10n_mx_edi_pac_status, 'signed', payroll.message_ids.mapped('body'))

    def test_base_viaticos(self):
        """Ensure that structure for viaticos is executed correctly."""
        self.struct = self.env.ref('l10n_mx_edi_payslip.payroll_structure_data_07')
        payroll = self.create_payroll()
        payroll.input_line_ids[-1].input_type_id = self.ref(
            'l10n_mx_edi_payslip.hr_payslip_input_type_other_payment_003_v')
        payroll.compute_sheet()
        payroll.action_payslip_done()
        self.assertEqual(payroll.l10n_mx_edi_pac_status, 'signed', payroll.message_ids.mapped('body'))

    def test_base_week(self):
        """Ensure that structure base is executed correctly for week."""
        payroll = self.create_payroll()
        self.contract.l10n_mx_edi_schedule_pay = '02'
        payroll.date_to = payroll.date_from + timedelta(days=7)
        payroll.compute_sheet()
        payroll.action_payslip_done()
        self.assertEqual(payroll.l10n_mx_edi_pac_status, 'signed', payroll.message_ids.mapped('body'))
