import re
import datetime
from functools import partial

from pydantic import validator


currency_re = re.compile(r"\$?\s(([-+]?\d{1,3}(\,\d{3})*|(\d+))(\.\d{2})?)")

def isodatestr_to_date(isodatestr: str):
    if 'Z' in isodatestr:
        isodatestr = isodatestr.replace('Z','+00:00')
    dt = datetime.datetime.fromisoformat(isodatestr)
    date = datetime.date(dt.year, dt.month, dt.day)
    return date


def parse_currency_string(currency_str: str) -> float:
    """
    input: str, '$3,065.86'
    output: float, 3065.86
    """
    # extract number from string
    currency_match = currency_re.search(currency_str)
    number_str = currency_match.get(1)
    # remove commas
    number_str = number_str.replace(',','')
    number_float = float(number_str)
    return number_float


def none_to_empty_string(value) -> str:
    """
    Convert value to string and None to ''
    """
    value = '' if not value else value
    return str(value)


