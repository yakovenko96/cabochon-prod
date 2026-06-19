from odoo import fields, models, tools


class CabochonWorkerLoadReport(models.Model):
    _name = "cabochon.worker.load.report"
    _description = "Панель технолога по нагрузке сотрудников"
    _auto = False
    _order = "active_request_count desc, worker_id"

    worker_id = fields.Many2one("hr.employee", string="Работник", readonly=True)
    company_id = fields.Many2one("res.company", string="Компания", readonly=True)
    active_request_count = fields.Integer(string="Активные заявки", readonly=True)
    total_request_count = fields.Integer(string="Всего заявок", readonly=True)
    planned_weight_g = fields.Float(string="Плановый вес, г", readonly=True)
    issued_weight_g = fields.Float(string="Выдано, г", readonly=True)
    received_weight_g = fields.Float(string="Сдано, г", readonly=True)
    detected_defect_weight_g = fields.Float(string="Выявленный брак, г", readonly=True)
    made_defect_weight_g = fields.Float(string="Сделанный брак, г", readonly=True)
    lost_weight_g = fields.Float(string="Потери, г", readonly=True)
    avg_duration_hours = fields.Float(string="Среднее время, ч", readonly=True)
    last_activity_at = fields.Datetime(string="Последняя активность", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW cabochon_worker_load_report AS (
                SELECT
                    MIN(request.id) AS id,
                    request.worker_id AS worker_id,
                    request.company_id AS company_id,
                    SUM(
                        CASE
                            WHEN request.state IN ('confirmed', 'issued', 'in_progress', 'partially_done')
                            THEN 1 ELSE 0
                        END
                    )::integer AS active_request_count,
                    COUNT(request.id)::integer AS total_request_count,
                    COALESCE(SUM(request.planned_weight_g), 0.0) AS planned_weight_g,
                    COALESCE(SUM(request.issued_weight_g), 0.0) AS issued_weight_g,
                    COALESCE(SUM(request.received_weight_g), 0.0) AS received_weight_g,
                    COALESCE(SUM(request.detected_defect_weight_g), 0.0) AS detected_defect_weight_g,
                    COALESCE(SUM(request.made_defect_weight_g), 0.0) AS made_defect_weight_g,
                    COALESCE(SUM(request.lost_weight_g), 0.0) AS lost_weight_g,
                    COALESCE(AVG(NULLIF(request.actual_duration_hours, 0.0)), 0.0) AS avg_duration_hours,
                    MAX(request.write_date) AS last_activity_at
                FROM cabochon_production_request request
                WHERE request.worker_id IS NOT NULL
                GROUP BY request.worker_id, request.company_id
            )
            """
        )


class CabochonWorkerOperationQualityReport(models.Model):
    _name = "cabochon.worker.operation.quality.report"
    _description = "Качество по работникам и операциям"
    _auto = False
    _order = "total_loss_percent desc, defect_percent desc, worker_id, operation_id"

    worker_id = fields.Many2one("hr.employee", string="Работник", readonly=True)
    operation_id = fields.Many2one("cabochon.manufacturing.operation", string="Операция", readonly=True)
    company_id = fields.Many2one("res.company", string="Компания", readonly=True)
    movement_count = fields.Integer(string="Движений", readonly=True)
    issued_weight_g = fields.Float(string="Выдано, г", readonly=True)
    received_weight_g = fields.Float(string="Сдано, г", readonly=True)
    defect_weight_g = fields.Float(string="Брак, г", readonly=True)
    detected_defect_weight_g = fields.Float(string="Выявленный брак, г", readonly=True)
    made_defect_weight_g = fields.Float(string="Сделанный брак, г", readonly=True)
    lost_weight_g = fields.Float(string="Потери, г", readonly=True)
    processed_weight_g = fields.Float(string="Обработано, г", readonly=True)
    defect_percent = fields.Float(string="Брак, %", readonly=True)
    loss_percent = fields.Float(string="Потери, %", readonly=True)
    total_loss_percent = fields.Float(string="Брак + потери, %", readonly=True)
    expected_loss_percent = fields.Float(string="Норма потерь, %", readonly=True)
    loss_over_norm_percent = fields.Float(string="Потери сверх нормы, %", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW cabochon_worker_operation_quality_report AS (
                WITH quality AS (
                    SELECT
                        movement.worker_id AS worker_id,
                        movement.primary_operation_id AS operation_id,
                        movement.company_id AS company_id,
                        COUNT(movement.id)::integer AS movement_count,
                        COALESCE(SUM(CASE WHEN movement.kind = 'issue' THEN movement.weight_g ELSE 0 END), 0.0) AS issued_weight_g,
                        COALESCE(SUM(CASE WHEN movement.kind = 'receipt' THEN movement.weight_g ELSE 0 END), 0.0) AS received_weight_g,
                        COALESCE(SUM(CASE WHEN movement.kind = 'defect' THEN movement.weight_g ELSE 0 END), 0.0) AS defect_weight_g,
                        COALESCE(SUM(CASE WHEN movement.kind = 'defect' AND movement.defect_kind = 'detected' THEN movement.weight_g ELSE 0 END), 0.0) AS detected_defect_weight_g,
                        COALESCE(SUM(CASE WHEN movement.kind = 'defect' AND movement.defect_kind = 'made' THEN movement.weight_g ELSE 0 END), 0.0) AS made_defect_weight_g,
                        COALESCE(SUM(CASE WHEN movement.kind = 'loss' THEN movement.weight_g ELSE 0 END), 0.0) AS lost_weight_g,
                        COALESCE(SUM(CASE WHEN movement.kind IN ('receipt', 'defect', 'loss') THEN movement.weight_g ELSE 0 END), 0.0) AS processed_weight_g,
                        COALESCE(MAX(operation.expected_loss_percent), 0.0) AS expected_loss_percent
                    FROM cabochon_manufacturing_movement movement
                    LEFT JOIN cabochon_manufacturing_operation operation ON operation.id = movement.primary_operation_id
                    WHERE movement.worker_id IS NOT NULL
                      AND movement.primary_operation_id IS NOT NULL
                      AND movement.kind IN ('issue', 'receipt', 'defect', 'loss')
                    GROUP BY movement.worker_id, movement.primary_operation_id, movement.company_id
                )
                SELECT
                    row_number() OVER ()::integer AS id,
                    worker_id,
                    operation_id,
                    company_id,
                    movement_count,
                    issued_weight_g,
                    received_weight_g,
                    defect_weight_g,
                    detected_defect_weight_g,
                    made_defect_weight_g,
                    lost_weight_g,
                    processed_weight_g,
                    CASE WHEN issued_weight_g > 0 THEN defect_weight_g / issued_weight_g * 100.0 ELSE 0.0 END AS defect_percent,
                    CASE WHEN issued_weight_g > 0 THEN lost_weight_g / issued_weight_g * 100.0 ELSE 0.0 END AS loss_percent,
                    CASE WHEN issued_weight_g > 0 THEN (defect_weight_g + lost_weight_g) / issued_weight_g * 100.0 ELSE 0.0 END AS total_loss_percent,
                    expected_loss_percent,
                    GREATEST(
                        CASE WHEN issued_weight_g > 0 THEN lost_weight_g / issued_weight_g * 100.0 ELSE 0.0 END - expected_loss_percent,
                        0.0
                    ) AS loss_over_norm_percent
                FROM quality
            )
            """
        )
