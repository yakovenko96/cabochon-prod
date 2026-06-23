{
    "name": "Кабошоны: база",
    "summary": "Группы, справочники и аудит учета кабошонов",
    "version": "19.0.2.2.0",
    "category": "Inventory/Inventory",
    "author": "Cabochon Ware",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
    ],
    "data": [
        "security/cabochon_groups.xml",
        "security/ir.model.access.csv",
        "security/cabochon_activity_rules.xml",
        "views/cabochon_menus.xml",
        "views/audit_log_views.xml",
        "views/cabochon_reference_views.xml",
    ],
    "application": True,
    "installable": True,
}
