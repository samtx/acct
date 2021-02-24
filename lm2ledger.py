# lunchmoney transactions to ledger file
from __future__ import annotations
import datetime
import os

import click

from lunchmoney import LunchMoney
from ledger import Ledger
from utils import datestr_to_date


class Lm2LedgerError(Exception):
    """ Base class for exceptions for this program """
    pass


class LunchMoneyTokenError(Lm2LedgerError):
    pass


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
            return datetime.datetime.strptime(value, format).date()
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
@click.option('--lmtoken', type=str, default='')
# @click.option('--start', 'date_start', type=Date('%Y-%m-%d'))
# @click.option('--end', 'date_end', type=Date('%Y-%m-%d'))
def cli(ledger_file, days, lmtoken):#, date_start, date_end):
    """ Update last number of days of transactions from lunch money """
    if not lmtoken:
        try:
            lmtoken = os.environ["LUNCHMONEY_ACCESS_TOKEN"]
        except KeyError:
            msg = "'LUNCHMONEY_ACCESS_TOKEN' environment variable not set"
            raise LunchMoneyTokenError(msg)

    lm = LunchMoney(lmtoken)
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=days)
    params = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
    click.echo('Getting Lunch Money data...')
    lm_txns = lm.get_transactions(params)
    click.echo(f'Found {len(lm_txns)} transactions between {start_date} and {end_date}')

    # create LedgerTransaction objects from lunchmoney transactions
    new_transactions = [lm.to_ledger(t) for t in lm_txns]

    click.echo('Parsing ledger file...')
    ledger = Ledger(ledger_file)
    ledger.parse()

    # update ledger file with lunchmoney transactions
    ledger.update(new_transactions)

    click.echo('Done')


if __name__ == "__main__":
#     ledger_file = 'personal.ledger'
#     days = 120
#     lmtoken = os.getenv('LUNCHMONEY_ACCESS_TOKEN')
    cli()
