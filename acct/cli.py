# lunchmoney transactions to ledger file
from __future__ import annotations

import csv
import datetime
import os
import re
import shutil
import tempfile
from collections import defaultdict

import click

from acct.ledger import Ledger
from acct.lunchmoney import LunchMoney
from acct.utils import datestr_to_date, isodatestr_to_date, parse_currency_string
from acct.boa import BOATransaction


class Lm2LedgerError(Exception):
    """Base class for exceptions for this program"""
    pass


class LunchMoneyTokenError(Lm2LedgerError):
    pass


class Date(click.ParamType):
    """
    Ref: https://markhneedham.com/blog/2019/07/29/python-click-date-parameter-type/
    """

    name = "date"

    def __init__(self, formats=None):
        self.formats = formats or [
            r"%Y-%m-%d",
            r"%Y/%m/%d",
            r"%m-%d",
            r"%m/%d",
        ]

    def get_metavar(self, param):
        # return '[{}]'.format('|'.join(self.formats))
        return "DATE"

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
            "invalid date format: {}. (choose from {})".format(
                value, ", ".join(self.formats)
            )
        )

    def __repr__(self):
        return "Date"


def select_date_range(**query):
    """
    Select date range for Lunch Money query.
    Order of precedence:
        year
        range
        begin/end
        days

    """
    if year := query.get("year"):
        start_date = datetime.date(int(year), 1, 1)
        end_date = datetime.date(int(year), 12, 31)

    elif begin := query.get("begin"):
        start_date = parse_date_string(begin)
        if end := query.get("end"):
            end_date = parse_date_string(end)
        else:
            end_date = datetime.date.today()

    elif end := query.get("end"):
        end_date = parse_date_string(end)
        if start := query.get("start"):
            start_date = parse_date_string(begin)
        else:
            start_date = datetime.date(1900, 1, 1)

    elif days := query.get("days"):
        start_date = datetime.date.today() - datetime.timedelta(days=days)
        end_date = datetime.date.today()

    return (start_date, end_date)


def write_output_to_file(file_name, output_string):
    # write to new temporary ledger file
    with tempfile.NamedTemporaryFile(mode="r+") as f:
        f.write(output_string)
        f.seek(0)
        shutil.copy2(f.name, file_name)


@click.command()
@click.option("-f", "--file", "ledger_file", type=click.Path())
@click.option("-o", "--output", "output_file", type=click.Path())
@click.option("--token", type=str, help="Lunch Money Access Token")
@click.option(
    "--token-stdin",
    "token_stdin",
    is_flag=True,
    default=False,
    help="Take Lunch Money token from stdin",
)
@click.option(
    "--cleared", is_flag=True, default=False, help="Only import cleared transactions"
)
@click.option("-v", "--verbose", count=True)
@click.option(
    "-d",
    "--days",
    type=int,
    default=90,
    show_default=True,
    help="select most recent number of days",
)
@click.option("-y", "--year", type=int, help="select transactions by year")
@click.option("-b", "--begin", type=Date(), help="transactions beginning with date")
@click.option("-e", "--end", type=Date(), help="transactions ending with date")
@click.option("--range", "range_", type=str, help="range of transaction dates")
def lm2ledger(
    ledger_file, output_file, token, token_stdin, cleared, verbose, **query_kw
):  # , date_start, date_end):
    """Update your ledger file with transactions from Lunch Money"""
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
        click.echo("Getting Lunch Money data...")
    lm.get_transactions(params)
    num_txns = len(lm.transactions)
    if verbose:
        click.echo(f"Found {num_txns} transactions between {start_date} and {end_date}")

    # create LedgerTransaction objects from lunchmoney transactions
    new_transactions = lm.to_ledger()

    if ledger_file:
        if verbose:
            click.echo("Parsing ledger file...")
        ledger = Ledger(ledger_file)
        ledger.parse()
        ledger.update(
            new_transactions
        )  # update ledger file with lunchmoney transactions
        output_string = ledger.write()
    else:
        output_string = "\n".join([t.write() for t in new_transactions])

    if output_file:
        write_output_to_file(output_file, output_string)
    else:
        stdout = click.get_text_stream("stdout")
        stdout.write(output_string)

    if verbose:
        out = output_file if output_file else "stdout"
        click.echo(f"Updated transactions written to {out}")


@click.command()
@click.argument("input_file", type=click.Path())
@click.option("-f", "--file", "ledger_file", type=click.Path())
@click.option("-v", "--verbose", count=True)
def boa2ledger(input_file, ledger_file, verbose):
    """Update your ledger file with transactions from Bank of America CSV"""

    # loop through csv
    data = defaultdict(list)
    with open(input_file, "r", encoding="utf-8") as f:
        line = f.readline()  # skip first line header for summary information

        # Beginning balance
        line = f.readline().strip()
        line_items = line.split(',')
        if begin_date_str := re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", line_items[0]):
            begin_date_str = begin_date_str[0]
            data['begin date'] = datestr_to_date(begin_date_str, mdy=True)
        else:
            raise Exception('Invalid begin balance date string')
        data['begin bal'] = float(line_items[2].strip('"'))

        # Total credits
        line = f.readline().strip()
        line_items = line.split(',')
        data['total credits'] = float(line_items[2].strip('"'))

        # Total debits
        line = f.readline().strip()
        line_items = line.split(',')
        data['total debits'] = float(line_items[2].strip('"'))

        # Ending balance
        line = f.readline().strip()
        line_items = line.split(',')
        if date_str := re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", line_items[0]):
            date_str = date_str[0]
            data['end date'] = datestr_to_date(date_str, mdy=True)
        else:
            raise Exception('Invalid end balance date string')
        data['end bal'] = float(line_items[2].strip('"'))

        # skip next line
        f.readline()

        # begin csv data section
        reader = csv.DictReader(f)
        running_total = 0.0
        for row in reader:
            # skip lines that have no amounts
            # e.g. the beginning balance line
            if row['Amount'] == '':
                continue

            boa_txn = BOATransaction(
                date=datestr_to_date(row['Date'], mdy=True),
                description=row['Description'],
                amount=float(row['Amount'].strip('"')),
            )

            # check if transaction is a duplicate, otherwise add to data set
            date_ = boa_txn.date
            if date_ in data:
                if not (boa_txn in data[date_]):
                    data[date_].append(boa_txn)
                else:
                    raise Exception(f"Duplicate transaction: {boa_txn}")

            if verbose > 0:
                click.echo(f"Added BoA trans. {boa_txn.date.strftime('%m/%d/%Y')}, ${boa_txn.amount:10.2f}, {boa_txn.description}")

            running_total += boa_txn.amount

        # check data integrity
        if data['total credits'] + data['total debits'] - running_total > 1e-6:
            raise Exception("Bank of America csv file amounts don't reconcile")

    # value = click.prompt('Enter Payee information', type=str)
    # journalentry = True
    # while journalentry:
    #     account = click.prompt('Enter journal entry account string')
    #     amount = click.prompt('Enter journal entry amount in USD', type=float)
    #     comment = click.prompt('Enter journal entry comment')



def cli():
    pass

if __name__ == "__main__":
    boa2ledger()
