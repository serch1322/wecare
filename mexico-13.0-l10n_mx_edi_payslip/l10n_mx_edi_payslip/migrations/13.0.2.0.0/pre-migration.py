def migrate(cr, version):
    create_loans_infonavit_data(cr)


def create_loans_infonavit_data(cr):
    """Create a loan for infonavit by each contract with infonavit"""
    cr.execute(
        """
        SELECT
            l10n_mx_edi_infonavit_type, l10n_mx_edi_infonavit_rate, employee_id
        FROM
            hr_contract
        WHERE
            state = 'open'
            AND l10n_mx_edi_infonavit_type != '';
        """)
    for data in cr.fetchall():
        cr.execute(
            """
            INSERT INTO
                hr_employee_loan
                (active, name, monthly_withhold, payment_term, loan_type, employee_id)
            VALUES
                (true, %s, %s, -1, 'infonavit', %s);
            """, ('Infonavit ::%s' % data[0], data[1], data[2]))
