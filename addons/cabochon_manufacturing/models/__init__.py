# ruff: noqa: I001
from . import once_mixin  # Register the abstract parent before its inheriting models.

from . import (
    cabochon_reports,
    catalogs,
    defect_recovery,
    external_receipt,
    finished_issue,
    hr_employee,
    integrity_report,
    scan_lot,
    material_transfer,
    movement,
    production_request,
    stone_lot,
)
