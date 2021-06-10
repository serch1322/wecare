def migrate(cr, version):
    create_loans_infonavit_data(cr)


def create_loans_infonavit_data(cr):
    """Create a loan for infonavit by each contract with infonavit"""
    cr.execute(
        """
        SELECT
            id, name
        FROM
            hr_employee_loan
        WHERE
            loan_type = 'infonavit'
            and name like '%::%';
        """)
    for loan in cr.fetchall():
        cr.execute(
            """
            UPDATE
                hr_employee_loan
            SET
                name = 'Infonavit',
                infonavit_type = %s
            WHERE
                id = %s;
            """, (loan[1].split('::')[-1], loan[0]))
