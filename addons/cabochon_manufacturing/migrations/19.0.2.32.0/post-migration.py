def migrate(cr, version):
    cr.execute(
        """
        UPDATE cabochon_size
           SET active = FALSE
         WHERE id IN (
            SELECT res_id
              FROM ir_model_data
             WHERE module = 'cabochon_manufacturing'
               AND name IN ('size_tube_thin', 'size_tube_medium', 'size_tube_thick')
               AND model = 'cabochon.size'
         )
        """
    )
    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE module = 'cabochon_manufacturing'
           AND name IN ('size_tube_thin', 'size_tube_medium', 'size_tube_thick')
           AND model = 'cabochon.size'
        """
    )
