import pytest
from acct.venmo import parse_venmo_currency_str


@pytest.mark.parametrize(
    "input_str, output_float",
    [
        ('"- $2,500.00"', -2500.0),
        ("+ $72.00", 72.0),
        ("- $637.86", -637.86),
        ('"+ $1,214.17"', 1214.17),
        ("- $10.00", -10.0),
        ("+ $10.00", 10.0),
    ],
)
def test_parse_venmo_currency_str(input_str, output_float):
    x = parse_venmo_currency_str(input_str)
    assert x == pytest.approx(output_float)
