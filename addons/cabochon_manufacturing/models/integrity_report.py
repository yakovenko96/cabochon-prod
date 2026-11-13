from odoo import fields, models, tools


class CabochonIntegrityReport(models.Model):
    _name = "cabochon.integrity.report"
    _description = "Контроль целостности производства"
    _auto = False
    _order = "problem, id"

    problem = fields.Char(string="Что проверить", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    lot_id = fields.Many2one("cabochon.stone.lot", string="Мешок", readonly=True)
    request_id = fields.Many2one("cabochon.production.request", string="Заявка", readonly=True)
    transfer_id = fields.Many2one("cabochon.material.transfer", string="Документ", readonly=True)
    movement_id = fields.Many2one("cabochon.manufacturing.movement", string="Движение", readonly=True)

    def init(self):
        tables = ["cabochon_stone_lot", "cabochon_material_transfer", "cabochon_manufacturing_movement", "cabochon_production_request"]
        for table in tables:
            self.env.cr.execute("SELECT to_regclass(%s)", [table])
            if not self.env.cr.fetchone()[0]:
                return
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW cabochon_integrity_report AS
            SELECT lot.id * 16 + 1 AS id, lot.company_id, lot.id AS lot_id,
                   NULL::integer AS request_id, NULL::integer AS transfer_id, NULL::integer AS movement_id,
                   'Отрицательный остаток мешка'::text AS problem
              FROM cabochon_stone_lot lot WHERE lot.current_weight_g < -0.0001
            UNION ALL
            SELECT lot.id * 16 + 2, lot.company_id, lot.id, NULL, NULL, NULL, 'Выданный мешок без владельца'
              FROM cabochon_stone_lot lot WHERE lot.state = 'issued' AND lot.owner_employee_id IS NULL
            UNION ALL
            SELECT transfer.id * 16 + 3, transfer.company_id, NULL, transfer.request_id, transfer.id, NULL, 'Подтверждение без времени или автора'
              FROM cabochon_material_transfer transfer
             WHERE transfer.state = 'confirmed' AND (transfer.manager_confirmed_at IS NULL OR transfer.worker_confirmed_at IS NULL
                OR transfer.manager_confirmed_by_id IS NULL OR transfer.worker_confirmed_by_id IS NULL)
            UNION ALL
            SELECT transfer.id * 16 + 4, transfer.company_id, NULL, transfer.request_id, transfer.id, NULL, 'Подтвержденная выдача без движения'
              FROM cabochon_material_transfer transfer
             WHERE transfer.state = 'confirmed' AND transfer.transfer_type = 'issue'
               AND NOT EXISTS (SELECT 1 FROM cabochon_manufacturing_movement movement WHERE movement.transfer_id = transfer.id)
            UNION ALL
            SELECT movement.id * 16 + 5, movement.company_id, movement.lot_id, movement.request_id, movement.transfer_id, movement.id, 'Движение у неподтвержденного документа'
              FROM cabochon_manufacturing_movement movement
              JOIN cabochon_material_transfer transfer ON transfer.id = movement.transfer_id
             WHERE transfer.state != 'confirmed'
            UNION ALL
            SELECT movement.id * 16 + 6, movement.company_id, movement.lot_id, movement.request_id, movement.transfer_id, movement.id, 'Разные компании в движении и мешке'
              FROM cabochon_manufacturing_movement movement
              JOIN cabochon_stone_lot lot ON lot.id = movement.lot_id
             WHERE movement.company_id != lot.company_id
            UNION ALL
            SELECT lot.id * 16 + 7, lot.company_id, lot.id, request.id, NULL, NULL, 'Закрытая заявка с остатком у работника'
              FROM cabochon_production_request request
              JOIN cabochon_material_transfer_line line ON line.transfer_id = request.issue_id
              JOIN cabochon_stone_lot lot ON lot.id = COALESCE(line.new_lot_id, line.lot_id)
             WHERE request.state = 'done' AND lot.state = 'issued' AND lot.current_weight_g > 0.0001
            UNION ALL
            SELECT lot.id * 16 + 8, lot.company_id, lot.id, NULL, NULL, NULL, 'Дублирующая позиция готового склада'
              FROM cabochon_stone_lot lot
              JOIN cabochon_manufacturing_location location ON location.id = lot.location_id
             WHERE location.code = 'finished' AND lot.state = 'available' AND NOT COALESCE(lot.is_defect_lot, FALSE)
               AND EXISTS (SELECT 1 FROM cabochon_stone_lot other WHERE other.id != lot.id
                    AND other.location_id = lot.location_id AND other.company_id = lot.company_id
                    AND other.state = 'available' AND NOT COALESCE(other.is_defect_lot, FALSE)
                    AND other.color_id IS NOT DISTINCT FROM lot.color_id
                    AND other.shape_id IS NOT DISTINCT FROM lot.shape_id
                    AND other.stone_size_id IS NOT DISTINCT FROM lot.stone_size_id
                    AND other.form_type_id IS NOT DISTINCT FROM lot.form_type_id)
            UNION ALL
            SELECT movement.id * 16 + 9, movement.company_id, movement.lot_id, movement.request_id,
                   movement.transfer_id, movement.id, 'Движение по отмененной заявке'
              FROM cabochon_manufacturing_movement movement
              JOIN cabochon_production_request request ON request.id = movement.request_id
             WHERE request.state = 'cancelled'
            UNION ALL
            SELECT transfer.id * 16 + 10, transfer.company_id, NULL, transfer.request_id, transfer.id, NULL,
                   'Подтвержденная сдача без исходного мешка'
              FROM cabochon_material_transfer transfer
             WHERE transfer.state = 'confirmed' AND transfer.transfer_type = 'receipt'
               AND EXISTS (SELECT 1 FROM cabochon_material_transfer_line line
                            WHERE line.transfer_id = transfer.id AND line.lot_id IS NULL
                              AND (line.weight_g > 0.0001 OR line.defect_weight_g > 0.0001
                                   OR line.return_loss_weight_g > 0.0001 OR line.lost_weight_g > 0.0001))
        """)

    def action_open_source(self):
        self.ensure_one()
        self.check_access("read")
        record = self.transfer_id or self.request_id or self.lot_id or self.movement_id
        record.check_access("read")
        return {"type": "ir.actions.act_window", "res_model": record._name, "res_id": record.id, "view_mode": "form"}
