from odoo import fields, models


class CabochonStoneType(models.Model):
    """Reference list for raw material types used before finished stones appear."""

    _name = "cabochon.stone.type"
    _description = "Тип сырья/материала"
    _order = "name"

    name = fields.Char(string="Название", required=True, index=True)
    description = fields.Text(string="Описание")
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint("UNIQUE(name)", "Название типа сырья должно быть уникальным.")


class CabochonFormType(models.Model):
    """Reference list for broad form categories across raw and processed lots."""

    _name = "cabochon.form.type"
    _description = "Тип формы"
    _order = "name"

    name = fields.Char(string="Название", required=True, index=True)
    description = fields.Text(string="Описание")
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint("UNIQUE(name)", "Название типа формы должно быть уникальным.")


class CabochonShape(models.Model):
    """Reference list for concrete raw blank or final stone shapes."""

    _name = "cabochon.shape"
    _description = "Форма"
    _order = "name"

    name = fields.Char(string="Название", required=True, index=True)
    description = fields.Text(string="Описание")
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint("UNIQUE(name)", "Название формы должно быть уникальным.")


class CabochonColor(models.Model):
    """Reference list for cabochon colors."""

    _name = "cabochon.color"
    _description = "Цвет"
    _order = "name"

    name = fields.Char(string="Название", required=True, index=True)
    hex_code = fields.Char(string="HEX-код")
    description = fields.Text(string="Описание")
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint("UNIQUE(name)", "Название цвета должно быть уникальным.")


class CabochonDrilledOption(models.Model):
    """Reference list for whether a cabochon is drilled."""

    _name = "cabochon.drilled.option"
    _description = "Просверлен"
    _order = "name"

    name = fields.Char(string="Название", required=True, index=True)
    description = fields.Text(string="Описание")
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint("UNIQUE(name)", "Название признака сверления должно быть уникальным.")


class CabochonExtraOption(models.Model):
    """Reference list for additional cabochon attributes."""

    _name = "cabochon.extra.option"
    _description = "Дополнительно"
    _order = "name"

    name = fields.Char(string="Название", required=True, index=True)
    description = fields.Text(string="Описание")
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint("UNIQUE(name)", "Название дополнительного признака должно быть уникальным.")


class CabochonSize(models.Model):
    """Reference list for raw fraction and finished stone sizes."""

    _name = "cabochon.size"
    _description = "Размер"
    _order = "name"

    name = fields.Char(string="Название", required=True, index=True)
    size = fields.Char(string="Размер")
    description = fields.Text(string="Описание")
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint("UNIQUE(name)", "Название размера должно быть уникальным.")


class CabochonDefectType(models.Model):
    """Classifies defects and their default operational treatment."""

    _name = "cabochon.defect.type"
    _description = "Тип брака кабошонов"
    _order = "name"

    name = fields.Char(string="Название", required=True, index=True)
    description = fields.Text(string="Описание")
    is_employee_caused = fields.Boolean(string="По вине сотрудника", default=False)
    is_returnable = fields.Boolean(string="Возвратный", default=True)
    default_action = fields.Selection(
        [
            ("keep_on_defect_stock", "Оставить на складе брака"),
            ("return_to_supplier", "Вернуть поставщику"),
            ("write_off_final", "Окончательно списать"),
            ("rework", "Переделка"),
        ],
        default="keep_on_defect_stock",
        required=True,
    )
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint("UNIQUE(name)", "Название типа брака должно быть уникальным.")
