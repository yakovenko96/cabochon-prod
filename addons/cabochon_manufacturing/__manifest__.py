{
    "name": "Кабошоны: изготовление",
    "summary": "Учет партий, операций, заявок, брака и движений при изготовлении кабошонов",
    "version": "19.0.2.5.1",
    "category": "Manufacturing/Manufacturing",
    "author": "Cabochon Ware",
    "license": "LGPL-3",
    "depends": [
        "cabochon_base",
        "hr",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/cabochon_manufacturing_rules.xml",
        "data/cabochon_manufacturing_data.xml",
        "views/hr_employee_views.xml",
        "views/cabochon_manufacturing_views.xml",
        "views/cabochon_manufacturing_menus.xml",
    ],
    "application": True,
    "installable": True,
    "post_init_hook": "post_init_hook",
}
