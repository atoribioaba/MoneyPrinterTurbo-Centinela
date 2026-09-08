import math

import pytest

from app.services.centinela.openngc_catalog import (
    OPENNGC_LICENSE,
    parse_dms_deg,
    parse_hms_hours,
    parse_openngc_row,
)


def test_coordinate_parsers_use_j2000_catalog_units():
    assert math.isclose(parse_hms_hours("00:42:44.30"), 0.7123056, rel_tol=1e-6)
    assert math.isclose(parse_dms_deg("+41:16:09.0"), 41.2691667, rel_tol=1e-6)
    assert math.isclose(parse_dms_deg("-12:30:00"), -12.5, rel_tol=1e-12)


def test_parse_openngc_row_preserves_source_fields():
    row = {
        "Name": "NGC0224",
        "Type": "G",
        "RA": "00:42:44.30",
        "Dec": "+41:16:09.0",
        "Const": "And",
        "MajAx": "177.83",
        "MinAx": "69.66",
        "PosAng": "35",
        "B-Mag": "4.36",
        "V-Mag": "3.44",
        "SurfBr": "13.6",
        "M": "31",
        "Identifiers": "UGC00454,PGC002557",
        "Common names": "Andromeda Galaxy",
        "Sources": "1,2,3",
    }
    obj = parse_openngc_row(row)
    assert obj.catalog_name == "NGC0224"
    assert obj.messier_number == 31
    assert obj.major_axis_arcmin == 177.83
    assert obj.common_names == ["Andromeda Galaxy"]
    assert obj.source_license == OPENNGC_LICENSE
    assert obj.scientific_status.value == "HECHO_VERIFICADO"


def test_nonexistent_and_duplicate_rows_are_not_physical_targets():
    base = {"Name": "NGC0000", "RA": "00:00:00", "Dec": "+00:00:00", "Const": "And"}
    with pytest.raises(ValueError):
        parse_openngc_row({**base, "Type": "NonEx"})
    with pytest.raises(ValueError):
        parse_openngc_row({**base, "Type": "Dup"})
