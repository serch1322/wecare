# Part of Odoo. See LICENSE file for full copyright and licensing details.
from __future__ import division

from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from odoo import _, api, fields, models


class ReportIdseReport(models.AbstractModel):
    _name = "hr.idse.report"
    _inherit = "account.report"
    _description = "IDSE report"

    filter_date = {'mode': 'range', 'filter': 'this_month'}
    filter_hierarchy = None

    def _get_columns_name(self, options):
        return [
            {},
            {'name': _('Employer Register')},
            {'name': _('NSS'), 'class': 'number'},
            {'name': _('SBC'), 'class': 'number'},
            {'name': _('Worker Type')},
            {'name': _('Wage type')},
            {'name': _('Working Type')},
            {'name': _('Date'), 'class': 'date'},
            {'name': _('Family Medicine Unit')},
            {'name': _('Guide')},
            {'name': _('Employee Code')},
            {'name': _('CURP')},
        ]

    def _get_reports_buttons(self):
        """Create the buttons to be used to download the required files"""
        buttons = super(ReportIdseReport, self)._get_reports_buttons()
        buttons += [{'name': _('Export IMSS (TXT)'),
                     'sequence': 3, 'action': 'print_txt', 'file_export_type': _('IMSS TXT')}]
        return buttons

    @api.model
    def _get_lines(self, options, line_id=None):
        lines = []
        contracts = self.env['hr.contract'].search([
            ('state', '=', 'open'),
            ('date_start', '>=', options['date']['date_from']),
            ('date_start', '<=',  options['date']['date_to'])])
        for contract in contracts:
            employee = contract.employee_id
            p_columns = [
                {'name': employee.l10n_mx_edi_employer_registration_id.name or employee.company_id.company_registry},
                {'name': employee.ssnid},
                {'name': self.format_value(contract.l10n_mx_edi_sbc)},
                {'name': dict(employee._fields['l10n_mx_edi_type']._description_selection(self.env)).get(
                    str(employee.l10n_mx_edi_type), ''),
                 'value': employee.l10n_mx_edi_type or ''},
                {'name': dict(contract._fields['l10n_mx_edi_salary_type']._description_selection(self.env)).get(
                    str(contract.l10n_mx_edi_salary_type), ''),
                 'value': contract.l10n_mx_edi_salary_type or ''},
                {'name': dict(contract._fields['l10n_mx_edi_working_type']._description_selection(self.env)).get(
                    str(contract.l10n_mx_edi_working_type), ''),
                 'value': contract.l10n_mx_edi_working_type or ''},
                {'name': fields.datetime.strftime(contract.date_start, '%d-%m-%Y')},
                {'name': employee.l10n_mx_edi_medical_unit},
                {'name': employee.l10n_mx_edi_employer_registration_id.guide},
                {'name': employee.barcode or employee.id},
                {'name': employee.address_home_id.l10n_mx_edi_curp},
            ]
            lines.append({
                'id': employee.id,
                'type': 'line',
                'name': employee.name,
                'footnotes': {},
                'columns': p_columns,
                'level': 2,
                'colspan': 1,
                'unfoldable': False,
                'unfolded': True,
            })
        return lines

    @api.model
    def _get_report_name(self):
        # Get the month and year from report date filters if exists
        date = fields.date.today()
        if self._context.get('report_date'):
            date = fields.datetime.strptime(
                self._context['report_date'], "%Y-%m-%d")
        company = self.env.user.company_id
        vat = company.vat or ''
        return 'IDSE_%s_%s' % (vat, date.strftime('%Y%m'))

    def get_txt(self, options):
        ctx = self._set_context(options)
        ctx.update({'no_format': True, 'print_mode': True, 'raise': True})
        return self.with_context(ctx)._l10n_mx_txt_export(options)

    def _l10n_mx_txt_export(self, options):
        txt_data = self._get_lines(options)
        lines = ''
        employee = self.env['hr.employee']
        for line in txt_data:
            if line.get('type', False) != 'line':
                continue
            columns = line.get('columns', [])
            data = [''] * 20
            employee = employee.browse(line['id'])
            data[0] = (columns[0]['name'] or '').ljust(11)
            data[1] = (columns[1]['name'] or '').ljust(11)[:11]
            data[2] = (employee.lastname or '').ljust(27)[:27].upper()
            data[3] = (employee.lastname2 or '').ljust(27)[:27].upper()
            data[4] = (employee.firstname or '').ljust(27)[:27].upper()
            data[5] = (str(columns[2]['name'] or '')).replace('.', '').zfill(6)
            data[6] = ''.ljust(6)
            data[7] = (columns[3]['value'] or ' ')
            data[8] = (columns[4]['value'] or ' ')
            data[9] = (columns[5]['value'] or ' ')
            data[10] = (columns[6]['name'] or '').replace('-', '').ljust(8)
            data[11] = (columns[7]['name'] or '').ljust(3)
            data[12] = '  '
            data[13] = '08'
            data[14] = (columns[8]['name'] or '').ljust(5)
            data[15] = (str(columns[9]['name']) or '').ljust(10)
            data[16] = ' '
            data[17] = (columns[10]['name'] or '').ljust(18)
            data[18] = '9'
            lines += ''.join(data) + '\n'
        return lines


class ReportIdseBajaReport(models.AbstractModel):
    _name = "hr.idse.baja.report"
    _inherit = "account.report"
    _description = "IDSE report Baja"

    filter_date = {'mode': 'range', 'filter': 'this_month'}
    filter_hierarchy = None

    def _get_columns_name(self, options):
        return [
            {},
            {'name': _('Employer Register')},
            {'name': _('NSS'), 'class': 'number'},
            {'name': _('Date'), 'class': 'date'},
            {'name': _('Guide')},
            {'name': _('Employee Code')},
            {'name': _('Reason')},
        ]

    def _get_reports_buttons(self):
        """Create the buttons to be used to download the required files"""
        buttons = super(ReportIdseBajaReport, self)._get_reports_buttons()
        buttons += [{
            'name': _('Export IMSS (TXT)'), 'sequence': 3, 'action': 'print_txt', 'file_export_type': _('IMSS TXT')}]
        return buttons

    @api.model
    def _get_lines(self, options, line_id=None):
        lines = []
        employees = self.env['hr.employee'].search([
            ('active', '=', False),
            ('departure_date', '>=',  options['date']['date_from']),
            ('departure_date', '<=',  options['date']['date_to'])])
        for employee in employees:
            p_columns = [
                {'name': employee.l10n_mx_edi_employer_registration_id.name or employee.company_id.company_registry},
                {'name': employee.ssnid},
                {'name': fields.datetime.strftime(employee.departure_date, '%d-%m-%Y')},
                {'name': employee.l10n_mx_edi_employer_registration_id.guide},
                {'name': employee.barcode or employee.id},
                {'name': employee.departure_reason},
            ]
            lines.append({
                'id': employee.id,
                'name': employee.name,
                'columns': p_columns,
                'level': 2,
                'unfoldable': False,
                'unfolded': True,
            })
        return lines

    @api.model
    def _get_report_name(self):
        # Get the month and year from report date filters if exists
        date = fields.date.today()
        if self._context.get('report_date'):
            date = fields.datetime.strptime(
                self._context['report_date'], "%Y-%m-%d")
        company = self.env.user.company_id
        vat = company.vat or ''
        return 'IDSE_%s_%s' % (vat, date.strftime('%Y%m'))

    def get_txt(self, options):
        ctx = self._set_context(options)
        ctx.update({'no_format': True, 'print_mode': True, 'raise': True})
        return self.with_context(ctx)._l10n_mx_txt_export(options)

    def _l10n_mx_txt_export(self, options):
        txt_data = self._get_lines(options)
        lines = ''
        employee = self.env['hr.employee']
        for line in txt_data:
            columns = line.get('columns', [])
            data = [''] * 20
            employee = employee.browse(line['id'])
            data[0] = (columns[0]['name'] or '').ljust(11)
            data[1] = (columns[1]['name'] or '').ljust(11)[:11]
            data[2] = (employee.lastname or '').ljust(27)[:27].upper()
            data[3] = (employee.lastname2 or '').ljust(27)[:27].upper()
            data[4] = (employee.firstname or '').ljust(27)[:27].upper()
            data[6] = ''.zfill(15)
            data[10] = (columns[2]['name'] or '').replace('-', '').ljust(8)
            data[12] = ''.ljust(5)
            data[13] = '02'
            data[14] = (columns[3]['name'] or '').ljust(5)
            data[15] = (str(columns[4]['name']) or '').ljust(10)
            data[16] = columns[5]['name'] or ''
            data[17] = ''.ljust(18)
            data[18] = '9'
            lines += ''.join(data) + '\n'
        return lines


class ReportIdseWageReport(models.AbstractModel):
    _name = "hr.idse.wage.report"
    _inherit = "account.report"
    _description = "IDSE report for Wage Update"

    filter_date = {'mode': 'range', 'filter': 'this_month'}
    filter_hierarchy = None

    def _get_columns_name(self, options):
        return [
            {},
            {'name': _('Employer Register')},
            {'name': _('NSS'), 'class': 'number'},
            {'name': _('SBC'), 'class': 'number'},
            {'name': _('Worker Type')},
            {'name': _('Wage type')},
            {'name': _('Working Type')},
            {'name': _('Date'), 'class': 'date'},
            {'name': _('Family Medicine Unit')},
            {'name': _('Guide')},
            {'name': _('Employee Code')},
            {'name': _('CURP')},
        ]

    def _get_reports_buttons(self):
        """Create the buttons to be used to download the required files"""
        buttons = super(ReportIdseWageReport, self)._get_reports_buttons()
        buttons += [{
            'name': _('Export IMSS (TXT)'), 'sequence': 3, 'action': 'print_txt', 'file_export_type': _('IMSS TXT')}]
        return buttons

    @api.model
    def _get_lines(self, options, line_id=None):
        lines = []
        contracts = self.env['hr.contract'].search([
            ('state', '=', 'open'),
        ])
        date_from = fields.datetime.strptime(options['date']['date_from'], DEFAULT_SERVER_DATE_FORMAT)
        date_to = fields.datetime.strptime(options['date']['date_to'], DEFAULT_SERVER_DATE_FORMAT)
        for contract in contracts:
            messages = contract.message_ids.filtered(lambda m: m.date.date() >= date_from.date() and
                                                     m.date.date() <= date_to.date() and
                                                     m.message_type == 'notification')
            if not messages:
                continue
            tracking = messages.sudo().mapped('tracking_value_ids').filtered(
                lambda t: t.field == 'l10n_mx_edi_sbc')
            if not tracking:
                continue
            employee = contract.employee_id
            p_columns = [
                {'name': employee.l10n_mx_edi_employer_registration_id.name or employee.company_id.company_registry},
                {'name': employee.ssnid},
                {'name': self.format_value(contract.l10n_mx_edi_sbc)},
                {'name': dict(employee._fields['l10n_mx_edi_type']._description_selection(self.env)).get(
                    str(employee.l10n_mx_edi_type), ''),
                 'value': employee.l10n_mx_edi_type or ''},
                {'name': dict(contract._fields['l10n_mx_edi_salary_type']._description_selection(self.env)).get(
                    str(contract.l10n_mx_edi_salary_type), ''),
                 'value': contract.l10n_mx_edi_salary_type or ''},
                {'name': dict(contract._fields['l10n_mx_edi_working_type']._description_selection(self.env)).get(
                    str(contract.l10n_mx_edi_working_type), ''),
                 'value': contract.l10n_mx_edi_working_type or ''},
                {'name': fields.datetime.strftime(
                    tracking.sorted('create_date')[-1].create_date.date(), '%d-%m-%Y')},
                {'name': employee.l10n_mx_edi_medical_unit},
                {'name': employee.l10n_mx_edi_employer_registration_id.guide},
                {'name': employee.barcode or employee.id},
                {'name': employee.address_home_id.l10n_mx_edi_curp},
            ]
            lines.append({
                'id': employee.id,
                'type': 'line',
                'name': employee.name,
                'footnotes': {},
                'columns': p_columns,
                'level': 2,
                'unfoldable': False,
                'unfolded': True,
                'colspan': 1,
            })
        return lines

    @api.model
    def _get_report_name(self):
        # Get the month and year from report date filters if exists
        date = fields.date.today()
        if self._context.get('report_date'):
            date = fields.datetime.strptime(
                self._context['report_date'], "%Y-%m-%d")
        company = self.env.user.company_id
        vat = company.vat or ''
        return 'IDSE_%s_%s' % (vat, date.strftime('%Y%m'))

    def get_txt(self, options):
        ctx = self._set_context(options)
        ctx.update({'no_format': True, 'print_mode': True, 'raise': True})
        return self.with_context(ctx)._l10n_mx_txt_export(options)

    def _l10n_mx_txt_export(self, options):
        txt_data = self._get_lines(options)
        lines = ''
        employee = self.env['hr.employee']
        for line in txt_data:
            if line.get('type', False) != 'line':
                continue
            columns = line.get('columns', [])
            data = [''] * 20
            employee = employee.browse(line['id'])
            data[0] = (columns[0]['name'] or '').ljust(11)
            data[1] = (columns[1]['name'] or '').ljust(11)[:11]
            data[2] = (employee.lastname or '').ljust(27)[:27].upper()
            data[3] = (employee.lastname2 or '').ljust(27)[:27].upper()
            data[4] = (employee.firstname or '').ljust(27)[:27].upper()
            data[5] = (str(columns[2]['name'] or '')).replace('.', '').zfill(6)
            data[6] = ''.ljust(6)
            data[7] = (columns[3]['value'] or ' ')
            data[8] = (columns[4]['value'] or ' ')
            data[9] = (columns[5]['value'] or ' ')
            data[10] = (columns[6]['name'] or '').replace('-', '').ljust(8)
            data[12] = ''.ljust(5)
            data[13] = '07'
            data[14] = (columns[8]['name'] or '').ljust(5)
            data[15] = (str(columns[9]['name']) or '').ljust(10)
            data[16] = ' '
            data[17] = (columns[10]['name'] or '').ljust(18)
            data[18] = '9'
            lines += ''.join(data) + '\n'
        return lines
