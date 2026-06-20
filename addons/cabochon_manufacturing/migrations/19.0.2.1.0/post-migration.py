def migrate(cr, version):
    cr.execute("DROP TABLE IF EXISTS cabochon_admission_wizard_operation_rel")
    cr.execute("DROP TABLE IF EXISTS cabochon_employee_admission_wizard")
