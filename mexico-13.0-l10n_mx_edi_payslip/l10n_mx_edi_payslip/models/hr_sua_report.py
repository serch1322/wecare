# Part of Odoo. See LICENSE file for full copyright and licensing details.
from __future__ import division

from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from odoo import _, api, fields, models


class ReportSuaReport(models.AbstractModel):
    _name = "hr.sua.report"
    _inherit = "account.report"
    _description = "SUA report"

    filter_date = {'mode': 'range', 'filter': 'this_month'}
    filter_hierarchy = None

    def _get_columns_name(self, options):
        return [
            {},
            {'name': _('Employer Register')},
            {'name': _('NSS'), 'class': 'number'},
            {'name': _('VAT')},
            {'name': _('CURP')},
            {'name': _('Worker Type')},
            {'name': _('Working Type')},
            {'name': _('Date'), 'class': 'date'},
            {'name': _('SDI'), 'class': 'number'},
            {'name': _('Employee Key')},
            {'name': _('Infonavit Number')},
            {'name': _('Date Start of Credit'), 'class': 'date'},
            {'name': _('Discount Type')},
            {'name': _('Discount Amount'), 'class': 'number'},
        ]

    def _get_reports_buttons(self):
        """Create the buttons to be used to download the required files"""
        buttons = super(ReportSuaReport, self)._get_reports_buttons()
        buttons += [{'name': _('Export IMSS (TXT)'),
                     'sequence': 3, 'action': 'print_txt', 'file_export_type': _('IMSS TXT')}]
        return buttons

    @api.model
    def _get_lines(self, options, line_id=None):
        lines = []
        contracts = self.env['hr.contract'].search([
            ('state', '=', 'open'),
        ])
        date_from = fields.datetime.strptime(options['date']['date_from'], DEFAULT_SERVER_DATE_FORMAT).date()
        date_to = fields.datetime.strptime(options['date']['date_to'], DEFAULT_SERVER_DATE_FORMAT).date()
        for contract in contracts:
            employee = contract.employee_id
            loan = employee.loan_ids.filtered(lambda l: l.loan_type == 'infonavit' and (
                l.payment_term == -1 or l.payslips_count < l.payment_term) and (
                    not l.date_from or l.date_from <= date_from) and (not l.date_to or l.date_to >= date_to))
            if not loan or not (contract.date_start >= date_from and contract.date_start <= date_to):
                continue
            p_columns = [
                {'name': employee.l10n_mx_edi_employer_registration_id.name or employee.company_id.company_registry},
                {'name': employee.ssnid},
                {'name': employee.address_home_id.vat},
                {'name': employee.address_home_id.l10n_mx_edi_curp},
                {'name': dict(employee._fields['l10n_mx_edi_type']._description_selection(self.env)).get(
                    str(employee.l10n_mx_edi_type), ''),
                 'value': employee.l10n_mx_edi_type or ''},
                {'name': dict(contract._fields['l10n_mx_edi_working_type']._description_selection(self.env)).get(
                    str(contract.l10n_mx_edi_working_type), ''),
                 'value': contract.l10n_mx_edi_working_type or ''},
                {'name': fields.datetime.strftime(contract.date_start, '%d-%m-%Y')},
                {'name': self.format_value(contract.l10n_mx_edi_sdi_total)},
                {'name': employee.pin},
                {'name': loan.name},
                {'name': fields.datetime.strftime(loan.date_from, '%d-%m-%Y') if loan else False},
                {'name': dict(loan._fields['infonavit_type']._description_selection(self.env)).get(
                    str(loan.infonavit_type), ''),
                 'value': loan.infonavit_type.replace('percentage', '1').replace('fixed_amount', '2').replace(
                     'vsm', '3')},
                {'name': loan.monthly_withhold},
            ]
            lines.append({
                'id': employee.id,
                'name': employee.name,
                'type': 'line',
                'footnotes': {},
                'columns': p_columns,
                'unfoldable': False,
                'unfolded': True,
                'colspan': 1,
                'level': 2,
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
        return 'SUA_%s_%s' % (vat, date.strftime('%Y%m'))

    def get_txt(self, options):
        ctx = self._set_context(options)
        ctx.update({'no_format': True, 'print_mode': True, 'raise': True})
        return self.with_context(ctx)._l10n_mx_txt_export(options)

    def _l10n_mx_txt_export(self, options):
        lines = ''
        txt_data = self._get_lines(options)
        employee = self.env['hr.employee']
        for line in txt_data:
            if line.get('type', False) != 'line':
                continue
            columns = line.get('columns', [])
            data = [''] * 14
            employee = employee.browse(line['id'])
            data[0] = (columns[0]['name'] or '').ljust(11).upper()
            data[1] = (columns[1]['name'] or '').ljust(11)[:11]
            data[2] = (columns[2]['name'] or '').ljust(13).upper()
            data[3] = (columns[3]['name'] or '').ljust(18).upper()
            data[4] = ('%s$%s$%s' % (employee.lastname or employee.lastname2 or '',
                                     employee.lastname2 or '' if employee.lastname else '',
                                     employee.firstname or '')).ljust(50)[:50].upper()
            data[5] = (columns[4]['value'] or ' ')
            data[6] = (columns[5]['value'] or ' ')
            data[7] = (columns[6]['name'] or '').replace('-', '').ljust(8)
            data[8] = (str(columns[7]['name'] or '')).replace('.', '').zfill(7)
            data[9] = (columns[8]['name'] or ' ').ljust(17).upper()
            data[10] = (columns[9]['name'] or '').ljust(10)[:10]
            data[11] = (columns[10]['name'] or '').replace('-', '').zfill(8)
            data[12] = (columns[11]['value'] or '0')
            data[13] = (str(columns[12]['name'] or '')).replace('.', '').zfill(8)
            lines += ''.join(data).upper() + '\n'
        return lines


class ReportSuaAffiliationReport(models.AbstractModel):
    _name = "hr.sua.affiliation.report"
    _inherit = "account.report"
    _description = "SUA report Affiliation"

    filter_date = {'mode': 'range', 'filter': 'this_month'}
    filter_hierarchy = None

    def _get_columns_name(self, options):
        return [
            {},
            {'name': _('Employer Register')},
            {'name': _('NSS'), 'class': 'number'},
            {'name': _('ZIP')},
            {'name': _('Birthday'), 'class': 'date'},
            {'name': _('Birthplace')},
            {'name': _('State Birthplace')},
            {'name': _('Family Medicine Unit')},
            {'name': _('Occupation')},
            {'name': _('Gender')},
            {'name': _('Salary Type')},
        ]

    def _get_reports_buttons(self):
        """Create the buttons to be used to download the required files"""
        buttons = super(ReportSuaAffiliationReport, self)._get_reports_buttons()
        buttons += [{
            'name': _('Export IMSS (TXT)'), 'sequence': 3, 'action': 'print_txt', 'file_export_type': _('IMSS TXT')}]
        return buttons

    @api.model
    def _get_lines(self, options, line_id=None):
        lines = []
        contracts = self.env['hr.contract'].search([
            ('state', '=', 'open'),
        ])
        date_from = fields.datetime.strptime(options['date']['date_from'], DEFAULT_SERVER_DATE_FORMAT).date()
        date_to = fields.datetime.strptime(options['date']['date_to'], DEFAULT_SERVER_DATE_FORMAT).date()
        states = {
            'AGU': '01', 'BCN': '02', 'BCS': '03', 'CAM': '04', 'COA': '05', 'COL': '06', 'CHP': '07', 'CHH': '08',
            'DIF': '09', 'DUR': '10', 'GUA': '11', 'GRO': '12', 'HID': '13', 'JAL': '14', 'MEX': '15', 'MIC': '16',
            'MOR': '17', 'NAY': '18', 'NLE': '19', 'OAX': '20', 'PUE': '21', 'QUE': '22', 'ROO': '23', 'SLP': '24',
            'SIN': '25', 'SON': '26', 'TAB': '27', 'TAM': '28', 'TLA': '29', 'VER': '30', 'YUC': '31', 'ZAC': '32',
        }

        for contract in contracts:
            employee = contract.employee_id
            loan = employee.loan_ids.filtered(lambda l: l.loan_type == 'infonavit' and (
                l.payment_term == -1 or l.payslips_count < l.payment_term) and (
                    not l.date_from or l.date_from <= date_from) and (not l.date_to or l.date_to >= date_to))
            if not loan or not (contract.date_start >= date_from and contract.date_start <= date_to):
                continue
            p_columns = [
                {'name': employee.l10n_mx_edi_employer_registration_id.name or employee.company_id.company_registry},
                {'name': employee.ssnid},
                {'name': employee.address_home_id.zip},
                {'name': fields.datetime.strftime(employee.birthday, '%d-%m-%Y') if employee.birthday else False},
                {'name': employee.place_of_birth},
                {'name': employee.l10n_mx_birth_state_id.name,
                 'value': (states.get(employee.l10n_mx_birth_state_id.code))},
                {'name': employee.l10n_mx_edi_medical_unit},
                {'name': employee.job_title},
                {'name': employee.gender},
                {'name': dict(contract._fields['l10n_mx_edi_salary_type']._description_selection(self.env)).get(
                    str(contract.l10n_mx_edi_salary_type), ''),
                 'value': contract.l10n_mx_edi_salary_type or ''},
            ]
            lines.append({
                'id': employee.id,
                'type': 'line',
                'level': 2,
                'name': employee.name,
                'footnotes': {},
                'columns': p_columns,
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
        return 'SUA_%s_%s' % (vat, date.strftime('%Y%m'))

    def get_txt(self, options):
        ctx = self._set_context(options)
        ctx.update({'no_format': True, 'print_mode': True, 'raise': True})
        return self.with_context(ctx)._l10n_mx_txt_export(options)

    def _l10n_mx_txt_export(self, options):
        lines = ''
        txt_data = self._get_lines(options)
        employee = self.env['hr.employee']
        for line in txt_data:
            columns = line.get('columns', [])
            data = [''] * 10
            employee = employee.browse(line['id'])
            data[0] = (columns[0]['name'] or '').ljust(11)
            data[1] = (columns[1]['name'] or '').ljust(11)[:11]
            data[2] = (columns[2]['name'] or '').ljust(5)
            data[3] = (columns[3]['name'] or '').replace('-', '').ljust(8)
            data[4] = (columns[4]['name'] or '').ljust(25)[:25]
            data[5] = (columns[5]['value'] or '  ')
            data[6] = columns[6]['name'] or '   '
            data[7] = (columns[7]['name'] or '').ljust(12)[:12]
            data[8] = (columns[8]['name'] or ' ')[0].upper()
            data[9] = columns[9]['value'] or ' '
            lines += ''.join(data).upper() + '\n'
        return lines


class ReportSuaBajaReport(models.AbstractModel):
    _name = "hr.sua.mov.report"
    _inherit = "account.report"
    _description = "SUA report Movements"

    filter_date = {'mode': 'range', 'filter': 'this_month'}
    filter_hierarchy = None

    def _get_columns_name(self, options):
        return [
            {},
            {'name': _('Employer Register')},
            {'name': _('NSS'), 'class': 'number'},
            {'name': _('Movement Type')},
            {'name': _('Date'), 'class': 'date'},
            {'name': _('Inability Number')},
            {'name': _('Days of incidence')},
            {'name': _('SDI')},
        ]

    def _get_reports_buttons(self):
        """Create the buttons to be used to download the required files"""
        buttons = super(ReportSuaBajaReport, self)._get_reports_buttons()
        buttons += [{
            'name': _('Export IMSS (TXT)'), 'sequence': 3, 'action': 'print_txt', 'file_export_type': _('IMSS TXT')}]
        return buttons

    @api.model
    def _get_lines(self, options, line_id=None):
        lines = []
        employees = self.env['hr.employee'].search([('active', 'in', [False, True])])
        date_from = fields.datetime.strptime(options['date']['date_from'], DEFAULT_SERVER_DATE_FORMAT).date()
        date_to = fields.datetime.strptime(options['date']['date_to'], DEFAULT_SERVER_DATE_FORMAT).date()
        for employee in employees:
            if not employee.active and employee.departure_date >= date_from and employee.departure_date <= date_to:
                lines.append({
                    'id': employee.id,
                    'name': employee.name,
                    'columns': [{'name': ''} for x in range(7)],
                    'level': 1,
                    'unfoldable': True,
                    'unfolded': True,
                })
                p_columns = [
                    {'name': employee.l10n_mx_edi_employer_registration_id.name or
                     employee.company_id.company_registry},
                    {'name': employee.ssnid},
                    {'name': 'Baja', 'value': '02'},
                    {'name': fields.datetime.strftime(employee.departure_date, '%d-%m-%Y')},
                    {'name': employee.l10n_mx_edi_employer_registration_id.guide},
                    {'name': employee.barcode or employee.id},
                    {'name': self.format_value(employee.contract_id.l10n_mx_edi_sdi_total)},
                ]
                lines.append({
                    'id': '02-%s' % employee.id,
                    'parent_id': employee.id,
                    'name': '',
                    'columns': p_columns,
                    'level': 2,
                    'unfoldable': False,
                    'unfolded': False,
                })
                continue
            contract = employee.contract_id
            if not contract:
                continue
            lines.append({
                'id': employee.id,
                'name': employee.name,
                'columns': [{'name': ''} for x in range(7)],
                'level': 1,
                'unfoldable': True,
                'unfolded': True,
            })
            show = False
            messages = contract.message_ids.filtered(lambda m: m.date.date() >= date_from and
                                                     m.date.date() <= date_to and m.message_type == 'notification')
            if messages:
                tracking = messages.sudo().mapped('tracking_value_ids').filtered(
                    lambda t: t.field == 'l10n_mx_edi_sbc')
                if tracking:
                    p_columns = [
                        {'name': employee.l10n_mx_edi_employer_registration_id.name or
                         employee.company_id.company_registry},
                        {'name': employee.ssnid},
                        {'name': 'Wage Update', 'value': '07'},
                        {'name': fields.datetime.strftime(
                            tracking.sorted('create_date')[-1].create_date.date(), '%d-%m-%Y')},
                        {'name': ''},
                        {'name': ''},
                        {'name': self.format_value(employee.contract_id.l10n_mx_edi_sdi_total)},
                    ]
                    lines.append({
                        'id': '07-%s' % employee.id,
                        'parent_id': employee.id,
                        'name': '',
                        'columns': p_columns,
                        'level': 2,
                        'unfoldable': False,
                        'unfolded': False,
                    })
                    show = True
            # Ausencias
            leave = self.env.ref('hr_payroll.work_entry_type_unpaid_leave')
            domain = [('work_entry_type_id', '=', leave.id)]
            leaves = contract._get_worked_leaves(date_from, date_to, domain=domain)
            if leaves:
                leaves = self.env['hr.leave']
                work_entry = self.env['hr.work.entry'].search(
                    contract._get_work_hours_domain(date_from, date_to, domain=domain, inside=True))
                for entry in work_entry:
                    if entry.leave_id in leaves:
                        continue
                    p_columns = [
                        {'name': employee.l10n_mx_edi_employer_registration_id.name or
                         employee.company_id.company_registry},
                        {'name': employee.ssnid},
                        {'name': 'Leaves', 'value': '11'},
                        {'name': fields.datetime.strftime(entry.leave_id.date_from.date(), '%d-%m-%Y')},
                        {'name': False},
                        {'name': int(entry.leave_id.number_of_days)},
                        {'name': self.format_value(employee.contract_id.l10n_mx_edi_sdi_total)},
                    ]
                    lines.append({
                        'id': '11-%s' % employee.id,
                        'parent_id': employee.id,
                        'name': '',
                        'columns': p_columns,
                        'level': 2,
                        'unfoldable': False,
                        'unfolded': True,
                    })
                    leaves |= entry.leave_id
                show = True
            # Incapacidades
            leave = self.env.ref('hr_payroll.work_entry_type_sick_leave')
            domain = [('work_entry_type_id', '=', leave.id)]
            leaves = contract._get_worked_leaves(date_from, date_to, domain=domain)
            if leaves:
                leaves = self.env['hr.leave']
                work_entry = self.env['hr.work.entry'].search(
                    contract._get_work_hours_domain(date_from, date_to, domain=domain, inside=True))
                for entry in work_entry:
                    if entry.leave_id in leaves:
                        continue
                    p_columns = [
                        {'name': employee.l10n_mx_edi_employer_registration_id.name or
                         employee.company_id.company_registry},
                        {'name': employee.ssnid},
                        {'name': 'Inability', 'value': '12'},
                        {'name': fields.datetime.strftime(entry.leave_id.date_from.date(), '%d-%m-%Y')},
                        {'name': entry.leave_id.name},
                        {'name': int(entry.leave_id.number_of_days)},
                        {'name': self.format_value(employee.contract_id.l10n_mx_edi_sdi_total)},
                    ]
                    lines.append({
                        'id': '12-%s' % employee.id,
                        'parent_id': employee.id,
                        'name': '',
                        'columns': p_columns,
                        'level': 2,
                        'unfoldable': False,
                        'unfolded': True,
                    })
                    leaves |= entry.leave_id
                show = True
            if not show:
                lines.pop()
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
        return 'SUA_%s_%s' % (vat, date.strftime('%Y%m'))

    def get_txt(self, options):
        ctx = self._set_context(options)
        ctx.update({'no_format': True, 'print_mode': True, 'raise': True})
        return self.with_context(ctx)._l10n_mx_txt_export(options)

    def _l10n_mx_txt_export(self, options):
        lines = ''
        txt_data = self._get_lines(options)
        employee = self.env['hr.employee']
        for line in txt_data:
            if line.get('level', False) == 1:
                continue
            columns = line.get('columns', [])
            data = [''] * 7
            employee = employee.browse(line['id'])
            data[0] = (columns[0]['name'] or '').ljust(11)
            data[1] = (columns[1]['name'] or '').ljust(11)[:11]
            data[2] = columns[2]['value'] or '  '
            data[3] = (columns[3]['name'] or '').replace('-', '').ljust(8)
            data[4] = (columns[4]['name'] or '').ljust(8)[:8]
            data[5] = (str(columns[5]['name']) or '').zfill(2)
            data[6] = (str(columns[6]['name'] or '')).replace('.', '').zfill(7)
            lines += ''.join(data).upper() + '\n'
        return lines
