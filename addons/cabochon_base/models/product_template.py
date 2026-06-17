from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    """Extends Odoo products with cabochon-specific catalog fields.

    Product records are reused by standard Odoo modules and Cabochon catalogs.
    The cabochon flags below separate stones and finished products from
    ordinary products.
    """

    _inherit = "product.template"

    default_code = fields.Char(string="Артикул")
    is_cabochon_stone = fields.Boolean(string="Камень-кабошон", default=False)
    is_cabochon_finished_product = fields.Boolean(
        string="Готовое изделие с кабошонами",
        default=False,
    )
    cabochon_stone_type_id = fields.Many2one(
        "cabochon.stone.type",
        string="Тип огранки",
    )
    cabochon_shape_id = fields.Many2one(
        "cabochon.shape",
        string="Форма",
    )
    cabochon_color_id = fields.Many2one(
        "cabochon.color",
        string="Цвет",
    )
    cabochon_drilled_id = fields.Many2one(
        "cabochon.drilled.option",
        string="Просверлен",
        default=lambda self: self.env.ref("cabochon_base.drilled_option_no", raise_if_not_found=False),
    )
    cabochon_extra_option_ids = fields.Many2many(
        "cabochon.extra.option",
        "product_template_cabochon_extra_option_rel",
        "product_tmpl_id",
        "extra_option_id",
        string="Дополнительно",
    )
    cabochon_size_id = fields.Many2one(
        "cabochon.size",
        string="Размер кабошона",
    )
    cabochon_standard_weight_g = fields.Float(
        string="Эталонный вес, г",
        digits=(16, 4),
    )
    cabochon_weight_tolerance_percent = fields.Float(
        string="\u041f\u043e\u0433\u0440\u0435\u0448\u043d\u043e\u0441\u0442\u044c \u0432\u0435\u0441\u0430, %",
        digits=(16, 2),
    )
    cabochon_weight_tolerance_g = fields.Float(
        string="\u041f\u043e\u0433\u0440\u0435\u0448\u043d\u043e\u0441\u0442\u044c \u0432\u0435\u0441\u0430, \u0433",
        compute="_compute_cabochon_weight_tolerance_g",
        digits=(16, 4),
        store=True,
    )
    cabochon_internal_code = fields.Char(string="Внутренний код кабошона")

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        """Show Odoo's internal reference as an article number in Cabochon flows."""
        fields_info = super().fields_get(allfields=allfields, attributes=attributes)
        if "default_code" in fields_info:
            fields_info["default_code"]["string"] = self.env._("Артикул")
        return fields_info

    @api.model
    def default_get(self, fields_list):
        """Default cabochon products to storable when opened from Cabochon menus."""
        values = super().default_get(fields_list)
        if values.get("is_cabochon_stone") or values.get("is_cabochon_finished_product"):
            values["type"] = "consu"
            values["is_storable"] = True
        return values

    @api.model_create_multi
    def create(self, vals_list):
        """Create cabochon products as storable Odoo products."""
        for vals in vals_list:
            if vals.get("is_cabochon_stone") or vals.get("is_cabochon_finished_product"):
                vals.setdefault("type", "consu")
                vals["is_storable"] = True
        return super().create(vals_list)

    def write(self, vals):
        """Keep cabochon products storable when cabochon flags are enabled."""
        if vals.get("is_cabochon_stone") or vals.get("is_cabochon_finished_product"):
            vals = dict(vals)
            vals.setdefault("type", "consu")
            vals["is_storable"] = True
        return super().write(vals)

    @api.constrains("is_cabochon_stone", "cabochon_weight_tolerance_percent")
    def _check_cabochon_weight_tolerance_percent(self):
        """Require a positive weight tolerance percent for stone products."""
        for record in self:
            if record.is_cabochon_stone and record.cabochon_weight_tolerance_percent <= 0:
                raise ValidationError(
                    "\u0414\u043b\u044f \u043a\u0430\u043c\u043d\u044f \u043d\u0443\u0436\u043d\u043e "
                    "\u0443\u043a\u0430\u0437\u0430\u0442\u044c \u043f\u043e\u043b\u043e\u0436\u0438\u0442\u0435\u043b"
                    "\u044c\u043d\u044b\u0439 % \u043f\u043e\u0433\u0440\u0435\u0448\u043d\u043e\u0441\u0442\u0438 "
                    "\u0432\u0435\u0441\u0430."
                )

    @api.depends("cabochon_standard_weight_g", "cabochon_weight_tolerance_percent")
    def _compute_cabochon_weight_tolerance_g(self):
        """Convert the tolerance percent into grams from the standard weight."""
        for record in self:
            record.cabochon_weight_tolerance_g = (
                record.cabochon_standard_weight_g * record.cabochon_weight_tolerance_percent / 100.0
            )

    @api.onchange("is_cabochon_stone", "is_cabochon_finished_product")
    def _onchange_cabochon_product_flags(self):
        """Enable stock tracking immediately when a product becomes cabochon-related."""
        for record in self:
            if record.is_cabochon_stone or record.is_cabochon_finished_product:
                record.type = "consu"
                record.is_storable = True


class ProductProduct(models.Model):
    """Align variant article label with Cabochon product terminology."""

    _inherit = "product.product"

    default_code = fields.Char(string="Артикул")

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        """Show Odoo's internal reference as an article number in Cabochon flows."""
        fields_info = super().fields_get(allfields=allfields, attributes=attributes)
        if "default_code" in fields_info:
            fields_info["default_code"]["string"] = self.env._("Артикул")
        return fields_info
