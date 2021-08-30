from datetime import date

import pytest
from lunchmoney.utils import isodatestr_to_date


@pytest.mark.parametrize("input_str, output_date", [
    ('2020-12-09T03:03:49', date(2020, 12, 9)),
    ('2020-12-10T16:00:26', date(2020, 12, 10)),
    ('2020-12-28T22:43:05', date(2020, 12, 28)),
    ('2020-12-28T22:59:33', date(2020, 12, 28)),
    ('2021-01-24T21:30:15', date(2021, 1, 24)),
    ('2021-02-01T17:18:15', date(2021, 2, 1)),
])
def test_isodatestr_to_date(input_str, output_date):
    x = isodatestr_to_date(input_str)
    assert x == output_date