EXTRACTION_MONTHS = [
    ("1", "Январь"),
    ("2", "Февраль"),
    ("3", "Март"),
    ("4", "Апрель"),
    ("5", "Май"),
    ("6", "Июнь"),
    ("7", "Июль"),
    ("8", "Август"),
    ("9", "Сентябрь"),
    ("10", "Октябрь"),
    ("11", "Ноябрь"),
    ("12", "Декабрь"),
]

DEFECT_LOT_SUFFIX_BY_LOCATION_CODE = {
    "raw": "С",
    "prepared": "ПС",
    "semi_finished": "ПФ",
    "finished": "ГК",
}

EXCLUSIVE_OPERATION_GROUPS = (
    {"tumble_wash", "toluene_wash"},
    {"press", "stone_preparation"},
    {"ball_machine", "cabochon_machine", "cnc"},
)

SINGLE_REQUEST_OPERATION_GROUPS = ()

SORT_OPERATION_TYPES = {
    "manual_sorting": "Ручная",
    "auto_separator": "Авто",
}

OPERATION_CODE_SUFFIXES = {
    "tubes": "TUBE",
    "tumble_wash": "WASH",
    "toluene_wash": "TLN",
    "manual_sorting": "SORT-M",
    "auto_separator": "SORT-P",
    "stone_preparation": "PREP",
    "cutting": "CUT",
    "press": "PRS",
    "normalization": "NORM",
    "cabochon_machine": "CAB",
    "ball_machine": "BALL",
    "cnc": "CNC",
    "grinding_polishing": "POL",
    "husking": "HUSK",
    "sorting": "SORT",
    "drilling": "DRILL",
    "tinting": "TINT",
}
