# lunchmoney transactions to ledger file
from __future__ import annotations

import datetime
import os
import pathlib
import shutil
import tempfile

import click
from prompt_toolkit.shortcuts import prompt, confirm
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit import print_formatted_text


from acct.boa import BankOfAmerica
from acct.ledger import (
    Ledger,
    LedgerAccountCompleter,
    LedgerPayeeAutoSuggest
)
from acct.prompts import prompt_to_create_ledger_transaction, prompt_to_create_new_ledger_transaction
from acct.lunchmoney import LunchMoney


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


@click.group()
@click.pass_context
def cli(ctx):
    pass


@cli.command()
@click.option("-f", "--file", "ledger_file", type=click.Path(), required=True)
@click.option("-o", "--output", "output_file", type=click.Path())
@click.option('--account', 'default_account', type=str, help='Default ledger account')
def ledgeradd(ledger_file, output_file, default_account):
    """
    Interatively add transactions to ledger file
    """
    ledger = Ledger(ledger_file)
    ledger.parse()
    completer = LedgerAccountCompleter(ledger)
    payee_suggestor = LedgerPayeeAutoSuggest(ledger)
    history = InMemoryHistory()
    n = 0

    # check default account
    if default_account and (default_account not in ledger.accounts):
        print_formatted_text(f"Default account {default_account} is not in ledger file {ledger_file}")
        default_account = prompt('Enter default account > ', history=history, completer=completer)
        if not bool(default_account):
            default_account = None
    try:
        while True:
            print_formatted_text(f'Add transaction for file {ledger_file}')
            t = prompt_to_create_new_ledger_transaction(
                history=history,
                completer=completer,
                payee_suggestor=payee_suggestor,
                default_account=default_account,
            )
            if not t:
                print_formatted_text("Quitting...")
                return
            # Assume transaction is cleared
            t.status = 'cleared'
            # find similar transactions already entered
            similar_t = ledger.find_similar_transactions(t)
            if len(similar_t) > 0:
                print_formatted_text('Similar transactions found:')
                for tx in similar_t:
                    print_formatted_text(f"{tx.write()}\n")
                print_formatted_text(f"You entered\n{t.write()}")
            else:
                print_formatted_text(f"\n{t.write()}")
            # double check transaction
            yes = confirm(message='Add transaction? ')
            if yes:
                ledger.save_transaction(t)
                n += 1
                print_formatted_text("Saved transaction\n")
    finally:
        # write to file
        print_formatted_text(f"Added {n} new transactions to ledger file")
        if output_file is None:
            output_file = ledger_file
        write_output_to_file(output_file, ledger.write())



@cli.command()
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


@cli.command()
@click.argument("input_file", type=click.Path())
@click.option("-f", "--file", "ledger_file", type=click.Path())
@click.option("-v", "--verbose", count=True)
def boa2ledger(input_file, ledger_file, verbose):
    """Update your ledger file with transactions from Bank of America CSV file"""

    boa = BankOfAmerica()
    boa.read_csv(input_file, verbose=verbose, printfn=click.echo)

    # Create Ledger transactions from BOA transactions
    ledger = Ledger(ledger_file)
    ledger.parse()

    completer = LedgerAccountCompleter(ledger)
    payee_suggestor = LedgerPayeeAutoSuggest(ledger)
    history = InMemoryHistory()

    # Get ledger account for BOA account
    boa_account = prompt('BoA Ledger Account > ', history=history, completer=completer, complete_while_typing=True)

    ledger_transactions = []
    print_formatted_text('Create new ledger transactions')
    n_duplicate = 0
    n_saved = 0
    try:
        for t in boa.transactions:
            # check to see if transaction matches any existing ledger transaction
            if res := BankOfAmerica.search_ledger_transactions(ledger, t, boa_account):
                print_formatted_text("Transaction already exists in ledger.")
                if verbose > 0:
                    print_formatted_text(res)
                print_formatted_text('Skipping...')
                n_duplicate += 1
                continue
            ledger_t = prompt_to_create_ledger_transaction(
                t, boa_account, history, completer, payee_suggestor
            )
            ledger.save_transaction(ledger_t)
            n_saved += 1
    finally:
        f_path = pathlib.Path(ledger_file) if not isinstance(ledger_file, pathlib.Path) else ledger_file
        fname = f_path.stem + '_tmp' + f_path.suffix
        print_formatted_text(f'Saving temporary ledger file {fname}')
        with open(fname, 'w', encoding='utf-8') as f:
            f.write(ledger.write())

    print_formatted_text(f'Saved {n_saved} new transactions. Skipped {n_duplicate} duplicates.')
    import pprint
    pprint.pprint(ledger_transactions)


    # click.echo(data)
    # value = click.prompt('Enter Payee information', type=str)
    # journalentry = True
    # while journalentry:
    #     account = click.prompt('Enter journal entry account string')
    #     amount = click.prompt('Enter journal entry amount in USD', type=float)
    #     comment = click.prompt('Enter journal entry comment')


if __name__ == "__main__":
    ledgeradd()
