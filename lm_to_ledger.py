# lunchmoney transactions to ledger file
from __future__ import annotations
import datetime
import re
import os
from typing import List, Optional
import asyncio

from dotenv import load_dotenv
import click
# from tqdm import tqdm
from pydantic import BaseModel
import aiohttp

from lunchmoney import LunchMoney
from ledger import Ledger
from utils import datestr_to_date

load_dotenv()


class Date(click.ParamType):
    """
    Ref: https://markhneedham.com/blog/2019/07/29/python-click-date-parameter-type/
    """
    name = 'date'

    def __init__(self, formats=None):
        self.formats = formats or [
            '%Y-%m-%d',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S'
        ]

    def get_metavar(self, param):
        return '[{}]'.format('|'.join(self.formats))

    def _try_to_convert_date(self, value, format):
        try:
            return datetime.strptime(value, format).date()
        except ValueError:
            return None

    def convert(self, value, param, ctx):
        for format in self.formats:
            date = self._try_to_convert_date(value, format)
            if date:
                return date

        self.fail(
            'invalid date format: {}. (choose from {})'.format(
                value, ', '.join(self.formats)))

    def __repr__(self):
        return 'Date'


@click.command()
@click.option('-f', '--file', 'ledger_file', type=click.Path(), default='personal.ledger', show_default=True)
@click.option('-d', '--days', type=click.IntRange(min=0), default=90, show_default=True)
# @click.option('--start', 'date_start', type=Date('%Y-%m-%d'))
# @click.option('--end', 'date_end', type=Date('%Y-%m-%d'))
def main(ledger_file, days):#, date_start, date_end):
    """ Update last number of days of transactions from lunch money """
    lm_access_token = os.getenv("LUNCHMONEY_ACCESS_TOKEN")
    lm = LunchMoney(lm_access_token)
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=days)
    params = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        # "limit": 10,
    }
    print('Getting Lunch Money data...')
    lm_txns = lm.get_transactions(params)
    print(f'Found {len(lm_txns)} transactions between {start_date} and {end_date}')

    print('Parsing ledger file...')
    ledger = Ledger(ledger_file)
    ledger.parse()

    # update ledger file with lunchmoney transactions
    # create Transaction object from lunchmoney transactions
    for t in lm_txns:
        ledger_tx = lm.to_ledger(t)
        ledger.transactions[t.id] = ledger_tx

    print('Done')


if __name__ == "__main__":
    main()
