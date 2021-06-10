# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta
import calendar
from math import floor
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.osv import expression
from odoo.tools import date_utils
from datetime import datetime
from collections import defaultdict


class HrContract(models.Model):
    _inherit = 'hr.contract'

    l10n_mx_edi_holidays = fields.Integer(
        string="Days of holidays", default=6, tracking=True,
        help="Initial number of days for holidays. The minimum is 6 days.")
    l10n_mx_edi_vacation_bonus = fields.Integer(
        string="Vacation bonus (%)", default=25, tracking=True,
        help="Percentage of vacation bonus. The minimum is 25 %.")
    l10n_mx_edi_christmas_bonus = fields.Integer(
        string="Christmas bonus (days)", default=15, help="Number of day for "
        "the Christmas bonus. The minimum is 15 days' pay",
        tracking=True)
    l10n_mx_edi_sdi_variable = fields.Float(
        'Variable SDI', default=0, tracking=True,
        help='Used when the salary type is mixed or variable. This value is '
        'integrated by the sum of perceptions in the previous two months and '
        'divided by the number of days worked. Also, it affects the '
        'integrated salary value.')
    l10n_mx_edi_sdi_total = fields.Float(
        compute='_compute_sdi_total', string='SDI', store=True, tracking=True,
        help='Get the sum of Variable SDI + Integrated Salary')
    l10n_mx_edi_sbc = fields.Float(
        'SBC', tracking=True, store=True, compute='_compute_integrated_salary',
        help='Used in the CFDI to express the salary that is integrated with the payments made in cash by daily '
        'quota, gratuities, perceptions, room, premiums, commissions, benefits in kind and any other quantity or '
        'benefit that is delivered to the worker by his work, Pursuant to Article 84 of the Federal Labor Law.')
    # Overwrite options & default
    l10n_mx_edi_schedule_pay = fields.Selection([
        ('01', 'Daily'),
        ('02', 'Weekly'),
        ('03', 'Biweekly'),
        ('04', 'Fortnightly'),
        ('05', 'Monthly'),
        ('06', 'Bimonthly'),
        ('07', 'Unit work'),
        ('08', 'Commission'),
        ('09', 'Raised price'),
        ('10', 'Decennial'),
        ('99', 'Other')], default='02', string=' Schedule Pay')

    l10n_mx_edi_contract_type = fields.Selection([
        ('01', 'Contrato de trabajo por tiempo indeterminado'),
        ('02', 'Contrato de trabajo para obra determinada'),
        ('03', 'Contrato de trabajo por tiempo determinado'),
        ('04', 'Contrato de trabajo por temporada'),
        ('05', 'Contrato de trabajo sujeto a prueba'),
        ('06', 'Contrato de trabajo con capacitación inicial'),
        ('07', 'Modalidad de contratación por pago de hora laborada'),
        ('08', 'Modalidad de trabajo por comisión laboral'),
        ('09', 'Modalidades de contratación donde no existe relación de '
         'trabajo'),
        ('10', 'Jubilación, pensión, retiro'),
        ('99', 'Otro contrato')], string='Contract Type')
    l10n_mx_edi_integrated_salary = fields.Float(
        'Integrated Salary', tracking=True, store=True,
        help='Used in the CFDI to express the salary '
        'that is integrated with the payments made in cash by daily quota, '
        'gratuities, perceptions, room, premiums, commissions, benefits in '
        'kind and any other quantity or benefit that is delivered to the '
        'worker by his work, Pursuant to Article 84 of the Federal Labor '
        'Law. (Used to calculate compensation).', compute='_compute_integrated_salary')
    l10n_mx_edi_food_voucher = fields.Float(
        'Food Voucher Amount',
        help='Amount to be paid in food voucher each payment period.', tracking=True)
    l10n_mx_edi_food_voucher_onerous = fields.Float(
        'Food Voucher Amount Onerous',
        help='Amount to be paid in food voucher onerous each payment period. If set, the food voucher amount '
        'not will be considered in the ISN. The common value is 1.00', tracking=True)
    l10n_mx_edi_punctuality_bonus = fields.Float(
        'Punctuality bonus', tracking=True,
        help='If the company offers punctuality bonus, indicate the bonus amount by payment period.')
    l10n_mx_edi_attendance_bonus = fields.Float(
        'Attendance bonus', tracking=True,
        help='If the company offers attendance bonus, indicate the bonus amount by payment period.')
    l10n_mx_edi_salary_type = fields.Selection([
        ('0', 'Fixed'),
        ('1', 'Variable'),
        ('2', 'Mixed'),
    ], 'Salary type', help='The action that updates automatically the SDI variable each bimester could discard '
        'contracts based on this field.', tracking=True, default='0')
    l10n_mx_edi_working_type = fields.Selection([
        ('0', 'Normal'),
        ('1', '1 day'),
        ('2', '2 days'),
        ('3', '3 days'),
        ('4', '4 days'),
        ('5', '5 days'),
        ('6', 'Reduced'),
    ], 'Working Type', help='Indicate the working type, based on the IDSE report.')
    l10n_mx_edi_day_off = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday')
    ], 'Day Off', help='Day off to Mexican payroll, the salary rule Septimo dia will use this '
        'day to be calculated, if is not set, the rule will consider Saturdays and Sundays as days off.')
    l10n_mx_edi_electric_ho = fields.Float(
        'Electric for Home Office', tracking=True,
        help='If the company offers electric bonus for home office employees, indicate the bonus amount.')
    l10n_mx_edi_internet_ho = fields.Float(
        'Internet for Home Office', tracking=True,
        help='If the company offers internet bonus for home office employees, indicate the bonus amount.')

    @api.depends('l10n_mx_edi_integrated_salary', 'l10n_mx_edi_sdi_variable')
    def _compute_sdi_total(self):
        for record in self:
            record.l10n_mx_edi_sdi_total = record.l10n_mx_edi_integrated_salary + record.l10n_mx_edi_sdi_variable

    @api.depends('l10n_mx_edi_vacation_bonus', 'l10n_mx_edi_christmas_bonus', 'l10n_mx_edi_holidays', 'wage',
                 'date_start', 'employee_id', 'l10n_mx_edi_sdi_variable')
    def _compute_integrated_salary(self):
        """Compute Daily Salary Integrated according to Mexican laws"""
        for record in self:
            sdi, sbc = record._get_integrated_salary()
            record.l10n_mx_edi_integrated_salary = sdi
            record.l10n_mx_edi_sbc = sbc

    def _get_integrated_salary(self, wage=None):
        self.ensure_one()
        sdi = self._get_static_sdi(wage)
        # the integrated salary cannot be less than 1 minimum wages
        minimum_wage = self.employee_id.l10n_mx_edi_employer_registration_id.minimum_wage or \
            self.company_id.l10n_mx_edi_minimum_wage
        sdi = minimum_wage if sdi < minimum_wage else sdi
        l10n_mx_edi_integrated_salary = round(sdi, 2)
        # the integrated salary cannot be more than 25 UMAs
        max_sdi = self.company_id.l10n_mx_edi_uma * 25
        sdi = sdi + self.l10n_mx_edi_sdi_variable
        sdi = sdi if sdi < max_sdi else max_sdi
        return l10n_mx_edi_integrated_salary, round(sdi, 2)

    def compute_integrated_salary_variable(self):
        """Compute Daily Salary Integrated Variable according to Mexican laws"""
        payslips = self.env['hr.payslip']
        categories = self.env.ref(
            'l10n_mx_edi_payslip.hr_salary_rule_category_perception_mx_taxed')
        categories |= self.env.ref(
            'l10n_mx_edi_payslip.hr_salary_rule_category_perception_mx_exempt')
        date_mx = fields.datetime.now()
        date_from = (date_mx - timedelta(days=30 * (2 if date_mx.month % 2 else 3))).replace(day=1)
        date_to = (date_mx - timedelta(days=30 * (1 if date_mx.month % 2 else 2)))
        date_to = date_to.replace(day=calendar.monthrange(date_to.year, date_to.month)[1])
        for record in self:
            payslips = payslips.search([
                ('contract_id', '=', record.id), ('state', '=', 'done'),
                ('date_from', '>=', date_from), ('date_to', '<=', date_to)])
            worked = sum(payslips.mapped('worked_days_line_ids').filtered(
                lambda work: work.code == 'WORK100').mapped('number_of_days'))
            inputs = sum(payslips.mapped('line_ids').filtered(
                lambda input: input.category_id in categories and not (input.code.endswith(
                    '001') or input.code.endswith('046'))).mapped('total'))
            record.l10n_mx_edi_sdi_variable = (inputs / worked) if worked else 0

    def _get_static_sdi(self, wage=None):
        """Get the integrated salary for the static perceptions like:
            - Salary
            - holidays
            - Christmas bonus
        """
        self.ensure_one()
        return (wage or self.wage) / 30 * self._get_integration_factor()

    def _get_integration_factor(self):
        """get the factor used to get the static integrated salary
        overwrite to add new static perceptions.
        factor = 1 + static perceptions/365
        new_factor = factor + new_perception / 365
        """
        self.ensure_one()
        vacation_bonus = (self.l10n_mx_edi_vacation_bonus or 25) / 100
        holidays = self.l10n_mx_edi_holidays * vacation_bonus
        bonus = self.l10n_mx_edi_christmas_bonus or 15
        return round(1 + (holidays + bonus) / 365, 4)

    def action_update_current_holidays(self):
        """Assign number of days according with the seniority and holidays"""
        # TODO - Moverlo a la metodología de listado de server action por contrato @nhomar
        for record in self:
            holidays = 6
            seniority = record.get_seniority()['years']
            if seniority < 4:
                record.l10n_mx_edi_holidays = holidays + 2 * (seniority)
                continue
            record.l10n_mx_edi_holidays = holidays + 6 + 2 * floor((seniority + 1) / 5)

    def get_seniority(self, date_from=False, date_to=False, method='r'):
        """Return seniority between contract's date_start and date_to or today

        :param date_from: start date (default contract.date_start)
        :type date_from: str
        :param date_to: end date (default today)
        :type date_to: str
        :param method: {'r', 'a'} kind of values returned
        :type method: str
        :return: a dict with the values years, months, days.
            These values can be relative or absolute.
        :rtype: dict
        """
        self.ensure_one()
        datetime_start = date_from or self.date_start
        date = date_to or fields.Date.today()
        relative_seniority = relativedelta(date, datetime_start)
        if method == 'r':
            return {'years': relative_seniority.years,
                    'months': relative_seniority.months,
                    'days': relative_seniority.days}
        return {'years': relative_seniority.years,
                'months': (relative_seniority.months + relative_seniority
                           .years * 12),
                'days': (date - datetime_start).days + 1}

    @staticmethod
    def _l10n_mx_edi_get_days(date_start, date_end):
        """Given two dates return the days elapsed between both dates"""
        date_start = fields.Date.from_string(date_start)
        date = fields.Date.from_string(date_end)
        days_work = ((date - date_start).days - 1)
        return 0 if days_work < 0 else days_work

    def _get_days_in_current_period(self, date_to=False, start_year=False):
        """Get days at current period to compute payments' proportional part

        :param date_to: date to get the days
        :type date_to: str
        :param start_year: period start at 1 Jan
        :type start_year: boolean
        :return: number of days of the contract in current period
        :rtype: int
        """
        date = date_to or fields.Date.today()
        contract_date = self.date_start
        if start_year:
            date_start = fields.date(date.year, 1, 1)
            if (contract_date - date_start).days > 0:
                date_start = contract_date
            return (date - date_start).days + 1
        date_start = fields.date(
            contract_date.year, contract_date.month, contract_date.day)
        if (date - date_start).days < 0:
            date_start = fields.date(
                date.year - 1, contract_date.month, contract_date.day)
        return (date - date_start).days + 1

    def _get_work_hours_domain(self, date_from, date_to, domain=None, inside=True):
        """This method was gotten from hr_payroll odoo/enterprise V14"""
        if domain is None:
            domain = []
        domain = expression.AND([domain, [
            ('state', 'in', ['validated', 'draft']),
            ('contract_id', 'in', self.ids),
        ]])
        if inside:
            domain = expression.AND([domain, [
                ('date_start', '>=', date_from),
                ('date_stop', '<=', date_to)]])
        else:
            domain = expression.AND([domain, [
                '|', '|',
                '&', '&',
                ('date_start', '>=', date_from),
                ('date_start', '<', date_to),
                ('date_stop', '>', date_to),
                '&', '&',
                ('date_start', '<', date_from),
                ('date_stop', '<=', date_to),
                ('date_stop', '>', date_from),
                '&',
                ('date_start', '<', date_from),
                ('date_stop', '>', date_to)]])
        return domain

    def _get_worked_leaves(self, date_from, date_to, domain=None):
        self.ensure_one()
        if not self.resource_calendar_id:
            return False
        work_hours = self._get_work_hours_new(date_from, date_to, domain=domain)
        work_hours_ordered = sorted(work_hours.items(), key=lambda x: x[1])
        return work_hours_ordered

    def _get_work_hours_new(self, date_from, date_to, domain=None):
        """This method was gotten from hr_payroll odoo/enterprise V14
        It is the update of a preexisting method _get_work_hours, was definied
        as a another method instand of intherit it to avoid undiscover problems
        in V13 structure

        Returns the amount (expressed in hours) of work
        for a contract between two dates.
        If called on multiple contracts, sum work amounts of each contract.
        :param domain: The domain for search of the hours
        :type domain: tuple, odoo domain form
        :param date_from: The start date
        :type date_from: datetime
        :param date_to: The end date
        :type date_to: datetime
        :returns: a dictionary {work_entry_id: hours_1, work_entry_2: hours_2}
        :rtype: dict
        """

        generated_date_max = min(fields.Date.to_date(date_to), date_utils.end_of(fields.Date.today(), 'month'))
        self._generate_work_entries(date_from, generated_date_max)
        date_from = datetime.combine(date_from, datetime.min.time())
        date_to = datetime.combine(date_to, datetime.max.time())
        work_data = defaultdict(int)

        # First, found work entry that didn't exceed interval.
        work_entries = self.env['hr.work.entry'].read_group(
            self._get_work_hours_domain(date_from, date_to, domain=domain, inside=True),
            ['hours:sum(duration)'],
            ['work_entry_type_id']
        )
        work_data.update({data['work_entry_type_id'][0] if data['work_entry_type_id'] else False:
                         data['hours'] for data in work_entries})

        # Second, find work entry that exceeds interval and compute right duration.
        work_entries = self.env['hr.work.entry'].search(
            self._get_work_hours_domain(date_from, date_to, domain=domain, inside=False))

        for work_entry in work_entries:
            date_start = max(date_from, work_entry.date_start)
            date_stop = min(date_to, work_entry.date_stop)
            if work_entry.work_entry_type_id.is_leave:
                contract = work_entry.contract_id
                calendar = contract.resource_calendar_id
                employee = contract.employee_id
                contract_data = employee._get_work_days_data_batch(
                    date_start, date_stop, compute_leaves=False, calendar=calendar
                )[employee.id]

                work_data[work_entry.work_entry_type_id.id] += contract_data.get('hours', 0)
            else:
                dt = date_stop - date_start
                work_data[work_entry.work_entry_type_id.id] += dt.days * 24 + dt.seconds / 3600  # Number of hours
        return work_data


class L10nMxEdiJobRank(models.Model):
    _name = "l10n_mx_edi.job.risk"
    _description = "Used to define the percent of each job risk."

    name = fields.Char(required=True, help='Job risk provided by the SAT.')
    code = fields.Char(required=True, help='Code assigned by the SAT for this job risk.')
    percentage = fields.Float(required=True, help='Percentage for this risk, is used in the '
                              'payroll rules.', digits=(2, 6),)
    branch_id = fields.Many2one(
        'res.partner', help='If the company have multi-branches, assign the job risk branch.')


class HrEmployeeLoan(models.Model):
    _name = 'hr.employee.loan'
    _inherit = ['mail.thread']
    _description = 'Allow register the loans in each employee.'

    name = fields.Char(
        'Number', help='Number for this record, if comes from Fonacot, use '
        '"No. Credito"', required=True, tracking=True)
    monthly_withhold = fields.Float(
        'Amount', tracking=True,
        help='Indicates the Amount to withhold base on\n\n'
        'Internal Discount: Amount monthly basis.\nCompany: Amount per pay period.\n'
        'Infonavit: Amount monthly basis.\nFonacot: Amount per pay period.\n'
        'Errors: Amount per pay period.\nBreakdowns: Amount per pay period.'
    )
    payment_term = fields.Integer(
        help='Indicates the payment term for this loan. If is undefined, please use "-1".', tracking=True)
    payslip_ids = fields.Many2many(
        'hr.payslip', help='Payslips where this loan is collected.', tracking=True)
    payslips_count = fields.Integer(
        'Number of Payslips', compute='_compute_payslips_count', tracking=True)
    loan_type = fields.Selection([
        ('internal', 'Internal Discount'),
        ('company', 'Company'),
        ('infonavit', 'Infonavit'),
        ('fonacot', 'Fonacot'),
        ('errors', 'Errors'),
        ('breakdowns', 'Breakdowns'),
    ], 'Type', help='Indicates the loan type.', tracking=True, required=True)
    employee_id = fields.Many2one(
        'hr.employee', help='Employee for this loan', tracking=True)
    number_fonacot = fields.Char(
        help='If comes from Fonacot, indicate the number.', tracking=True)
    active = fields.Boolean(
        help='If the loan was paid the record will be deactivated.',
        default=True, tracking=True)
    date_from = fields.Date(
        help='Start date of loan, is used to know if must be considered in the payslip.')
    date_to = fields.Date(
        help='End date of loan, is used to know if must be considered in the payslip.\nNote: If is empty will be '
        'considered always.')
    infonavit_type = fields.Selection(
        [('percentage', _('Percentage')),
         ('vsm', _('Number of minimum wages')),
         ('fixed_amount', _('Fixed amount')), ], tracking=True,
        string='Discount Type', help="INFONAVIT discount type that is calculated in the employee's payslip.")
    company_id = fields.Many2one(
        'res.company', related='employee_id.company_id', help='Employee Company')

    def _compute_payslips_count(self):
        for loan in self:
            loan.payslips_count = len(loan.payslip_ids.filtered(
                lambda rec: rec.state == 'done'))

    def action_get_payslips_view(self):
        return {
            'name': _('Loan Payslips'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'hr.payslip',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', self.payslip_ids.filtered(
                lambda rec: rec.state == 'done').ids)],
        }


class L10nMxEdiEmployerRegistration(models.Model):
    _name = 'l10n_mx_edi.employer.registration'
    _description = 'Allow define all the employer registration from the company'
    _inherit = ['mail.thread']

    name = fields.Char(
        help='Value to set in the "RegistroPatronal" attribute.')
    job_risk_id = fields.Many2one(
        'l10n_mx_edi.job.risk', 'Job Risk',
        help='Used in the XML to express the key according to the Class in '
        'which the employers must register, according to the activities '
        'carried out by their workers, as provided in article 196 of the '
        'Regulation on Affiliation Classification of Companies, Collection '
        'and Inspection, or in accordance with the regulations Of the Social '
        'Security Institute of the worker.', required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)
    partner_id = fields.Many2one('res.partner', related='company_id.partner_id')
    branch_id = fields.Many2one(
        'res.partner', help='If the company have multi-branches, assign the employer registration branch.')
    guide = fields.Char(
        'Guide Number', help='Number assigned for the delegation to this record. This will be used in the IDSE '
        'report.')
    minimum_wage = fields.Float(
        help='Indicates the current daily minimum wage amount in this employer registration.')
