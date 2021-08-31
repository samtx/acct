import datetime
from os import name
import re
from dataclasses import dataclass
from collections import defaultdict
from pathlib import Path
from typing import Union, Callable
import csv
from io import TextIOWrapper

from acct.utils import datestr_to_date

@dataclass
class BOATransaction:
    date: datetime.date
    description: str
    amount: float


class BankOfAmerica:
    """
    Class to hold data from Bank of America csv files
    """
    def __init__(self):
        self.transactions = []

    def read_csv(
            self,
            csv_file: Union[str, Path],
            verbose: int = 0,
            printfn: Callable = print,
            **kw
        ):
        """Update your ledger file with transactions from Bank of America CSV"""

        # loop through csv
        data = defaultdict(list)
        if verbose > 0:
            printfn(f"Parsing csv file {str(csv_file)}")
        with open(csv_file, "r", encoding="utf-8") as f:
            data = self._parse_csv_file(f, verbose=verbose, printfn=printfn, **kw)


        # update object transaction list
        if verbose > 0:
            printfn(f"Update object with new transactions")
        n = 0
        for date_ in data.keys():
            for t in data[date_]:
                if t in self.transactions:
                    if verbose > 0:
                        printfn(f'Skipping duplicate transaction: {t}')
                    continue
                else:
                    self.transactions.append(t)
                    n += 1
        if verbose > 0:
            printfn(f'Added {n} new transactions')
        # print('')

    def _parse_csv_file(self, f: TextIOWrapper, **kw):
        verbose = kw.get('verbose')
        printfn = kw.get('printfn')
        data = defaultdict(list)
        line = f.readline()  # skip first line header for summary information
        # Beginning balance
        line = f.readline().strip()
        # line_items = line.split(',')
        # if begin_date_str := re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", line_items[0]):
        #     begin_date_str = begin_date_str[0]
        #     data['begin date'] = datestr_to_date(begin_date_str, mdy=True)
        # else:
        #     raise Exception('Invalid begin balance date string')
        # data['begin bal'] = float(line_items[2].strip('"'))

        # Total credits
        line = f.readline().strip()
        line_items = line.split(',')
        total_credits = float(line_items[2].strip('"'))

        # Total debits
        line = f.readline().strip()
        line_items = line.split(',')
        total_debits = float(line_items[2].strip('"'))

        # Ending balance
        line = f.readline().strip()
        # line_items = line.split(',')
        # if date_str := re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", line_items[0]):
        #     date_str = date_str[0]
        #     data['end date'] = datestr_to_date(date_str, mdy=True)
        # else:
        #     raise Exception('Invalid end balance date string')
        # data['end bal'] = float(line_items[2].strip('"'))

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
            if not(boa_txn in data[date_]):
                data[date_].append(boa_txn)
            else:
                if verbose > 0:
                    printfn(f"Skipping duplicate transaction: {boa_txn}")
                continue

            if verbose > 0:
                printfn(f"Found BoA trans. {boa_txn.date.strftime('%m/%d/%Y')}, ${boa_txn.amount:10.2f}, {boa_txn.description}")

            running_total += boa_txn.amount

        # check data integrity
        if verbose > 0:
            printfn(f"Check csv file integrity")
        if total_credits + total_debits - running_total > 1e-6:
            raise Exception("Bank of America csv file amounts don't reconcile")

        return data



