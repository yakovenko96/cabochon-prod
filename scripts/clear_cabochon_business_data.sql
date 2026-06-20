-- Destructive reset of Cabochon business data. Create a pg_dump backup first.
-- Preserves Odoo users, employees, five system locations and system operations.
BEGIN;

LOCK TABLE cabochon_production_request IN ACCESS EXCLUSIVE MODE;
LOCK TABLE cabochon_material_transfer IN ACCESS EXCLUSIVE MODE;
LOCK TABLE cabochon_stone_lot IN ACCESS EXCLUSIVE MODE;
LOCK TABLE cabochon_manufacturing_movement IN ACCESS EXCLUSIVE MODE;

DELETE FROM mail_activity
WHERE res_model_id IN (
    SELECT id FROM ir_model WHERE model LIKE 'cabochon.%'
);

DELETE FROM mail_followers WHERE res_model LIKE 'cabochon.%';
DELETE FROM mail_message WHERE model LIKE 'cabochon.%';
DELETE FROM ir_attachment WHERE res_model LIKE 'cabochon.%';

DELETE FROM ir_model_data
WHERE module = 'cabochon_manufacturing'
  AND model IN ('cabochon.extraction.year', 'cabochon.fraction');

TRUNCATE TABLE
    cabochon_audit_log,
    cabochon_employee_operation_rel,
    cabochon_external_receipt_wizard,
    cabochon_movement_correction_wizard,
    cabochon_movement_operation_rel,
    cabochon_production_request_operation_line,
    cabochon_request_operation_rel,
    cabochon_transfer_operation_rel,
    cabochon_manufacturing_movement,
    cabochon_material_transfer_line,
    cabochon_material_transfer,
    cabochon_production_request,
    cabochon_stone_lot,
    cabochon_color,
    cabochon_form_type,
    cabochon_shape,
    cabochon_size,
    cabochon_extraction_year,
    cabochon_fraction,
    cabochon_stone_type,
    cabochon_defect_type,
    cabochon_drilled_option,
    cabochon_extra_option
RESTART IDENTITY CASCADE;

DELETE FROM cabochon_manufacturing_location
WHERE id NOT IN (
    SELECT res_id
    FROM ir_model_data
    WHERE module = 'cabochon_manufacturing'
      AND model = 'cabochon.manufacturing.location'
      AND name LIKE 'location_%'
);

UPDATE cabochon_manufacturing_location
SET manager_id = NULL,
    employee_id = NULL,
    write_uid = 1,
    write_date = now();

DELETE FROM cabochon_manufacturing_operation
WHERE id NOT IN (
    SELECT res_id
    FROM ir_model_data
    WHERE module = 'cabochon_manufacturing'
      AND model = 'cabochon.manufacturing.operation'
      AND name LIKE 'operation_%'
);

UPDATE cabochon_manufacturing_operation
SET expected_loss_percent = 0.0,
    write_uid = 1,
    write_date = now();

UPDATE ir_sequence
SET number_next = 1,
    write_uid = 1,
    write_date = now()
WHERE code IN (
    'cabochon.stone.lot',
    'cabochon.production.request',
    'cabochon.material.transfer',
    'cabochon.manufacturing.movement'
);

COMMIT;
