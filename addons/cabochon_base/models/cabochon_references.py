from odoo import fields, models


class CabochonFormType(models.Model):
    _name = "cabochon.form.type"
    _description = "Тип формы"
    _order = "name"

    name = fields.Char(string="Название", required=True, index=True)
    use_for_machine = fields.Boolean(string="ЧПУ, кабошонерка, шарокрутка")
    description = fields.Text(string="Описание")
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint("UNIQUE(name)", "Название типа формы должно быть уникальным.")


class CabochonShape(models.Model):
    _name = "cabochon.shape"
    _description = "Форма"
    _order = "name"

    name = fields.Char(string="Название", required=True, index=True)
    use_for_press = fields.Boolean(string="Пресс")
    use_for_machine = fields.Boolean(string="ЧПУ, кабошонерка, шарокрутка")
    description = fields.Text(string="Описание")
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint("UNIQUE(name)", "Название формы должно быть уникальным.")


class CabochonColor(models.Model):
    _name = "cabochon.color"
    _description = "Цвет"
    _order = "name"

    name = fields.Char(string="Название", required=True, index=True)
    hex_code = fields.Char(string="HEX-код")
    description = fields.Text(string="Описание")
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint("UNIQUE(name)", "Название цвета должно быть уникальным.")


class CabochonSize(models.Model):
    _name = "cabochon.size"
    _description = "Размер"
    _order = "name"

    name = fields.Char(string="Название", required=True, index=True)
    size = fields.Char(string="Размер")
    use_for_sorting = fields.Boolean(string="Сортировка")
    use_for_press = fields.Boolean(string="Пресс")
    use_for_machine = fields.Boolean(string="ЧПУ, кабошонерка, шарокрутка")
    description = fields.Text(string="Описание")
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint("UNIQUE(name)", "Название размера должно быть уникальным.")
