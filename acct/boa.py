import csv
import datetime
from collections import defaultdict
from dataclasses import dataclass
from io import TextIOWrapper
from pathlib import Path
from typing import Callable, Union

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
        **kw,
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
        for t_list in data.values():
            for t in t_list:
                if t in self.transactions:
                    if verbose > 0:
                        printfn(f"Skipping duplicate transaction: {t}")
                    continue
                else:
                    self.transactions.append(t)
                    n += 1
        if verbose > 0:
            printfn(f"Added {n} new transactions")

    def _parse_csv_file(self, f: TextIOWrapper, **kw):
        verbose = kw.get("verbose")
        printfn = kw.get("printfn")
        data = defaultdict(list)
        line = f.readline()  # skip first line header for summary information
        # Beginning balance
        line = f.readline()

        # Total credits
        line = f.readline().strip()
        line_items = line.split(",")
        total_credits = float(line_items[2].strip('"'))

        # Total debits
        line = f.readline().strip()
        line_items = line.split(",")
        total_debits = float(line_items[2].strip('"'))

        # Ending balance
        line = f.readline()

        # skip next line
        f.readline()

        # begin csv data section
        reader = csv.DictReader(f)
        running_total = 0.0
        for row in reader:
            # skip lines that have no amounts
            # e.g. the beginning balance line
            if row["Amount"] == "":
                continue

            boa_txn = BOATransaction(
                date=datestr_to_date(row["Date"], mdy=True),
                description=row["Description"],
                amount=float(row["Amount"].strip('"')),
            )

            # check if transaction is a duplicate, otherwise add to data set
            date_ = boa_txn.date
            if not (boa_txn in data[date_]):
                data[date_].append(boa_txn)
            else:
                if verbose > 0:
                    printfn(f"Skipping duplicate transaction: {boa_txn}")
                continue

            if verbose > 0:
                printfn(
                    f"Found BoA trans. {boa_txn.date.strftime('%m/%d/%Y')}, ${boa_txn.amount:10.2f}, {boa_txn.description}"
                )

            running_total += boa_txn.amount

        # check data integrity
        if verbose > 0:
            printfn(f"Check csv file integrity")
        if total_credits + total_debits - running_total > 1e-6:
            raise Exception("Bank of America csv file amounts don't reconcile")
        return data

    @staticmethod
    def search_ledger_transactions(ledger, boa_transaction, boa_account):
        """
        Search ledger transactions to see if Bank of America transaction has already been entered
        Can only check: date, amount, payee (listed as boa: payee in transaction metadata tag)
        """
        # get transactions for that post date
        transactions_on_date = ledger.dates.get(boa_transaction.date)
        if not transactions_on_date:
            return None
        # search those transactions for similar payees
        matched_transaction = None
        while (len(transactions_on_date) > 0) and (not matched_transaction):
            ledger_t_id = transactions_on_date.pop()
            ledger_t = ledger.transactions[ledger_t_id]
            found_matching_boa_tag = False
            for tag in ledger_t.tags:
                if (tag.name == 'boa') and (tag.value == boa_transaction.description):
                    found_matching_boa_tag = True
                    break
            if not found_matching_boa_tag:
                continue
            found_matching_amount = False
            for item in ledger_t.items:
                if (item.account == boa_account) and (item.amount == boa_transaction):
                    found_matching_amount = True
                    break
            if found_matching_amount:
                # found transaction matching date, payee, and amount
                matched_transaction = ledger_t
                break
        return matched_transaction










