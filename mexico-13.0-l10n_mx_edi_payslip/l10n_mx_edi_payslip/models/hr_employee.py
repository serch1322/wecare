from odoo import api, fields, models


class HrEmployee(models.Model):

    _inherit = "hr.employee"

    l10n_mx_edi_syndicated = fields.Boolean(
        'Syndicated', help='Used in the XML to indicate if the worker is '
        'associated with a union. If it is omitted, it is assumed that it is '
        'not associated with any union.')
    l10n_mx_edi_risk_rank = fields.Many2one(
        'l10n_mx_edi.job.risk', 'Job Risk',
        help='Used in the XML to express the key according to the Class in '
        'which the employers must register, according to the activities '
        'carried out by their workers, as provided in article 196 of the '
        'Regulation on Affiliation Classification of Companies, Collection '
        'and Inspection, or in accordance with the regulations Of the Social '
        'Security Institute of the worker.')
    l10n_mx_edi_contract_regime_type = fields.Selection([
        ('02', 'Sueldos'),
        ('03', 'Jubilados'),
        ('04', 'Pensionados'),
        ('05', 'Asimilados Miembros Sociedades Cooperativas Produccion'),
        ('06', 'Asimilados Integrantes Sociedades Asociaciones Civiles'),
        ('07', 'Asimilados Miembros consejos'),
        ('08', 'Asimilados comisionistas'),
        ('09', 'Asimilados Honorarios'),
        ('10', 'Asimilados acciones'),
        ('11', 'Asimilados otros'),
        ('99', 'Otro Regimen')
    ], 'Regimen Type', help='Indicates the regimen type for the employee.')
    l10n_mx_edi_is_assimilated = fields.Boolean(
        'Is assimilated?', help='If this employee is assimilated, must be '
        'used this option, to get the correct rules on their payslips')
    loan_ids = fields.One2many(
        'hr.employee.loan', 'employee_id', 'Loans',
        help='Indicate the loans for the employee. Will be considered on the '
        'payslips.')
    l10n_mx_edi_loan_count = fields.Integer(
        compute='_compute_loan_count', string='Loan Count', groups="hr_payroll.group_hr_payroll_user")
    l10n_mx_edi_employer_registration_id = fields.Many2one(
        'l10n_mx_edi.employer.registration', 'Employer Registration',
        help='If the company has multiple employer registration, define the '
        'correct for this employee.')
    departure_reason = fields.Selection(selection_add=[
        ('1', 'Contract End'),
        ('2', 'Voluntary separation'),
        ('3', 'Job Abandonment'),
        ('4', 'Death'),
        ('5', 'Closure'),
        ('6', 'Other')
    ], default="1")
    l10n_mx_edi_alimony_ids = fields.One2many(
        'hr.employee.alimony', 'employee_id', 'Alimony',
        help='Indicate the alimony for the employee. Will be considered on the payslip.')
    l10n_mx_edi_alimony_count = fields.Integer(
        compute='_compute_loan_count', string='Alimony Count', groups="hr_payroll.group_hr_payroll_user")
    l10n_mx_edi_payment_method_id = fields.Many2one('l10n_mx_edi.payment.method', 'Payment Way')
    l10n_mx_edi_medical_unit = fields.Char(
        'Medical Unit', help='Indicate the medical unit for the employee, will be used in the IDSE report.')
    l10n_mx_edi_type = fields.Selection([
        ('1', 'Permanent worker'),
        ('2', 'Casual City Worker'),
        ('3', 'Casual Construction Worker')], 'Employee Type',
        help='Indicate the employee type, based on the IDSE options.')
    l10n_mx_birth_state_id = fields.Many2one(
        'res.country.state', 'State of birth', help='Value to set in the SUA report')

    departure_date = fields.Date(copy=False, tracking=True, groups="hr.group_hr_user",
                                 help="When the employee got deactivate")

    def _compute_loan_count(self):
        for employee in self:
            employee.l10n_mx_edi_loan_count = len(employee.loan_ids)
            employee.l10n_mx_edi_alimony_count = len(employee.l10n_mx_edi_alimony_ids)

    @api.onchange('l10n_mx_birth_state_id')
    def onchange_birth_state(self):
        for record in self:
            record.country_of_birth = record.l10n_mx_birth_state_id.country_id

    def get_cfdi_employee_data(self, contract):
        self.ensure_one()
        return {
            'contract_type': contract.l10n_mx_edi_contract_type,
            'emp_syndicated': 'Sí' if self.l10n_mx_edi_syndicated else 'No',
            'working_day': self.sudo().get_working_date(),
            'emp_diary_salary': '%.2f' % contract.
            l10n_mx_edi_integrated_salary,
        }

    def get_working_date(self):
        """Based on employee category, verify if a category set in this
        employee come from this module and get code."""
        category = self.category_ids.filtered(lambda r: r.color == 3)
        if not category or not category[0].get_external_id()[
                category[0].id].startswith('l10n_mx_edi_payslip'):
            return ''
        return category[0].name[:2]

    @api.onchange('address_id')
    def onchange_address(self):
        emp_reg = self.env['l10n_mx_edi.employer.registration']
        for record in self.filtered('address_id'):
            record.l10n_mx_edi_employer_registration_id = emp_reg.search(
                [('branch_id', '=', record.address_id.id)], limit=1) or record.l10n_mx_edi_employer_registration_id

    def get_current_loans(self, loan_type, date_from, date_to):
        """ Get valid loans of a employee between dates.
            A loan is valid if received dates are between loan's dates
            If loans dates are not define the loan is considered as always valid """
        return self.loan_ids.filtered(
            lambda l: l.loan_type == loan_type
            and (l.payment_term == -1 or l.payslips_count < l.payment_term)
            and (not l.date_from or l.date_from <= date_to)
            and (not l.date_to or l.date_to >= date_to or (l.date_to >= date_from and l.date_to <= date_to)))

    def toggle_active(self):
        res = super(HrEmployee, self).toggle_active()
        unarchived_employees = self.filtered(lambda employee: employee.active)
        unarchived_employees.write({'departure_date': False})
        return res


class HrEmployeeAlimony(models.Model):
    _name = 'hr.employee.alimony'
    _description = 'Allow define the alimony records for the employee'
    _inherit = ['mail.thread']

    name = fields.Char('Order', required=True, tracking=True)
    court = fields.Char(tracking=True)
    number = fields.Char(tracking=True, required=True)
    discount_type = fields.Selection([
        ('percentage_wage', 'Percentage over salary'),
        ('percentage_perceptions_ISR', 'Percentage over perceptions less ISR and SS'),
        ('amount_fixed', 'Amount fixed'),
        ('percentage_over_net', 'Percentage over net'),
        ('percentage_perceptions', 'Percentage over perceptions'),
        ('percentage_perceptions_ISR_mortgages', 'Percentage over perceptions less ISR and Mortgages'),
        ('percentage_christmas', 'Percentage over Christmas bonus'),
        ('percentage_christmas_holidays', 'Percentage over Christmas bonus and holidays'),
        ('amount_fixed_christmas', 'Fixed over Christmas bonus'),
    ], required=True)
    discount_amount = fields.Float(
        'Discount/Percent Amount', tracking=True, required=True,
        help='If this alimony is based on un amount, indicate the amount by each payment period.')
    date_from = fields.Date(tracking=True, required=True)
    date_to = fields.Date(tracking=True)
    partner_id = fields.Many2one('res.partner', 'Beneficiary', tracking=True)
    employee_id = fields.Many2one('hr.employee', tracking=True)
    payment_method_id = fields.Many2one('l10n_mx_edi.payment.method', 'Payment Way', tracking=True)
    notes = fields.Text(tracking=True)
    increase_based_on = fields.Selection([
        ('uma', 'UMA'),
        ('vsm', 'VSM'),
        ('annual', 'Annual'),
    ], 'Base for Increase', help='If the alimony must increase, indicate base in with will be increased.')
    amount_annual_increase = fields.Float(
        'Amount for annual increase')

    @api.model
    def update_alimony(self):
        today = fields.datetime.now()
        for record in self.search([('increase_based_on', '=', 'annual')]):
            if record.date_from.month == today.month and record.date_from.day == today.day and record.date_from.year != today.year:  # noqa
                record.discount_amount += record.amount_annual_increase
