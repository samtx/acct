import datetime
import re
from functools import partial

from pydantic import validator

currency_re = re.compile(r"\$?\s(([-+]?\d{1,3}(\,\d{3})*|(\d+))(\.\d{2})?)")


def isodatestr_to_date(isodatestr: str):
    if "Z" in isodatestr:
        isodatestr = isodatestr.replace("Z", "+00:00")
    dt = datetime.datetime.fromisoformat(isodatestr)
    date = datetime.date(dt.year, dt.month, dt.day)
    return date


def datestr_to_date(datestr, mdy=False):
    """
    Parse year/month/day string to datetime.date

    dmy = use the month/day/year order for parsing
        otherwise user year/month/day
    """
    datestr = datestr.replace("-", "/")
    n1, n2, n3 = datestr.split("/")
    if mdy:
        # swap
        mo, dy, yr = n1, n2, n3
    else:
        yr, mo, dy = n1, n2, n3
    date = datetime.date(int(yr), int(mo), int(dy))
    return date


def parse_currency_string(currency_str: str) -> float:
    """
    input: str, '$3,065.86'
    output: float, 3065.86
    """
    # extract number from string
    if (currency_match := currency_re.search(currency_str)):
        number_str = currency_match.get(1)
    else:
        currency_match = re.match(r"[-+]?\d+(\.\d{2})?", currency_str)
        number_str = currency_match.get(1)
    # remove commas
    number_str = number_str.replace(",", "")
    number_float = float(number_str)
    return number_float


def none_to_empty_string(value) -> str:
    """
    Convert value to string and None to ''
    """
    value = "" if not value else value
    return str(value)


# def simple_string_to_currency_float(currency_str: str) -> float:
#     """
#     input: str, '3065.86'
#     output: float, 3065.86
#     """
#     # extract number from string
#     # remove commas
#     number_str = number_str.replace(",", "")
#     amount = float(currency_str)
#     number_float = float(number_str)
#     return number_float
