def migrate(cr, version):
    cr.execute(
        """
        UPDATE cabochon_material_transfer
           SET transfer_date = NULL
         WHERE state IN ('draft', 'manager_confirmed')
        """
    )
