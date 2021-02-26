# lunchmoney transactions to ledger file
from __future__ import annotations
import datetime
import os
import shutil
import tempfile

import click

from .lunchmoney import LunchMoney
from .ledger import Ledger


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
            r'%Y-%m-%d',
            r'%Y/%m/%d',
            r'%m-%d',
            r'%m/%d',
        ]

    def get_metavar(self, param):
        # return '[{}]'.format('|'.join(self.formats))
        return 'DATE'

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



def select_date_range(**query):
    """
    Select date range for Lunch Money query.
    Order of precedence:
        year
        range
        begin/end
        days

    """
    if year := query.get('year'):
        start_date = datetime.date(int(year), 1, 1)
        end_date = datetime.date(int(year), 12, 31)

    elif begin := query.get('begin'):
        start_date = parse_date_string(begin)
        if end := query.get('end'):
            end_date = parse_date_string(end)
        else:
            end_date = datetime.date.today()

    elif end := query.get('end'):
        end_date = parse_date_string(end)
        if start := query.get('start'):
            start_date = parse_date_string(begin)
        else:
            start_date = datetime.date(1900, 1, 1)

    elif days := query.get('days'):
        start_date = datetime.date.today() - datetime.timedelta(days=days)
        end_date = datetime.date.today()

    return (start_date, end_date)


def write_output_to_file(file_name, output_string):
    # write to new temporary ledger file
    with tempfile.NamedTemporaryFile(mode='r+') as f:
        n = f.write(output_string)
        f.seek(0)
        shutil.copy2(f.name, file_name)


@click.command()
@click.option('-f', '--file', 'ledger_file', type=click.Path())
@click.option('-o', '--output', 'output_file', type=click.Path())
@click.option('--token', type=str, help='Lunch Money Access Token')
@click.option('--token-stdin', 'token_stdin', is_flag=True, default=False, help='Take Lunch Money token from stdin')
@click.option('--cleared', is_flag=True, default=False, help='Only import cleared transactions')
@click.option('-v', '--verbose', count=True)
@click.option('-d', '--days', type=int, default=90, show_default=True, help='select most recent number of days')
@click.option('-y', '--year', type=int, help='select transactions by year')
@click.option('-b', '--begin', type=Date(), help='transactions beginning with date')
@click.option('-e', '--end', type=Date(), help='transactions ending with date')
@click.option('--range', 'range_', type=str, help='range of transaction dates')
def cli(ledger_file, output_file, token, token_stdin, cleared, verbose, **query_kw):#, date_start, date_end):
    """Update your ledger file with transactions from Lunch Money

    """
    if token_stdin:
        # Read token from stdin
        token = click.get_text_stream()
    if (not token) and not (token := os.getenv("LUNCHMONEY_ACCESS_TOKEN")):
        msg = "'LUNCHMONEY_ACCESS_TOKEN' environment variable not set"
        raise LunchMoneyTokenError(msg)

    lm = LunchMoney(token)

    if query_kw is None:
        query_kw = {}

    start_date, end_date = select_date_range(**query_kw)
    params = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "cleared": cleared,
    }
    if verbose:
        click.echo('Getting Lunch Money data...')
    lm_txns = lm.get_transactions(params)
    if verbose:
        click.echo(f'Found {len(lm_txns)} transactions between {start_date} and {end_date}')

    # create LedgerTransaction objects from lunchmoney transactions
    new_transactions = [lm.to_ledger(t) for t in lm_txns]

    if ledger_file:
        if verbose:
            click.echo('Parsing ledger file...')
        ledger = Ledger(ledger_file)
        ledger.parse()
        ledger.update(new_transactions)  # update ledger file with lunchmoney transactions
        output_string = ledger.write()
    else:
        output_string = '\n'.join([t.write() for t in new_transactions])

    if output_file:
        write_output_to_file(output_file, output_string)
    else:
        stdout = click.get_text_stream('stdout')
        stdout.write(output_string)

    if verbose:
        out = output_file if output_file else 'stdout'
        click.echo(f'Updated transactions written to {out}')


if __name__ == "__main__":
    cli()
