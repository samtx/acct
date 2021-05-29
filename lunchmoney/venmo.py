import datetime
from dataclasses import dataclass
from typing import List, Union
from pathlib import Path
import asyncio
import csv
from enum import Enum

import httpx
from pydantic import BaseModel

from lunchmoney.core import LunchMoneyTransaction, LunchMoneyCategory, LunchMoneyTransactionInsert
from .utils import isodatestr_to_date

# https://venmo.com/transaction-history/statement?startDate=11-30-2020&endDate=02-28-2021&profileId=1499956183564288593&accountType=personal

def parse_venmo_currency_str(currency_str) -> float:
    """
    from venmo statement csv file:
    input: [str] "- $2,500.00"
    output: [float] -2500.0
    """
    parsed_str = currency_str.replace('$','').replace(',','').replace(' ','').replace('\"','')
    currency_float = float(parsed_str)
    return currency_float


class TransactionType(Enum):
    transfer = 'Standard Transfer'
    payment = 'Payment'


def venmo_type_to_enum(transaction_type):
    if transaction_type == 'Standard Transfer':
        return TransactionType.transfer
    elif transaction_type == 'Payment':
        return TransactionType.payment


class VenmoTransaction(BaseModel):
    id: int
    date: datetime.date
    amount: float
    type: TransactionType
    note: str = ''
    from_: str = ''
    to: str = ''
    source: str = ''
    destination: str = ''
    fee: float = 0.0


class Venmo:

    def __init__(self):
        self.transactions = {}

    def read_csv(self, csv_file: Union[str, Path]):
        """ Read Venmo statement csv file into object data """
        data = {}
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            # get header row
            # fieldnames = list(next(reader).keys())
            # get beginning balance row
            bal = next(reader)
            beginning_balance = parse_venmo_currency_str(bal['Beginning Balance'])
            reader_list = list(reader)
            running_total = 0.0
            for row in reader_list:
                if row['Ending Balance'] != '':
                    ending_balance = parse_venmo_currency_str(row['Ending Balance'])
                    break
                data = {
                    'id': row['ID'],
                    'date': isodatestr_to_date(row['Datetime']),
                    'from_': row['From'],
                    'to': row['To'],
                    'note': row['Note'],
                    'amount': parse_venmo_currency_str(row['Amount (total)']) if row['Amount (total)'] else 0.0,
                    'fee': parse_venmo_currency_str(row['Amount (fee)']) if row['Amount (fee)'] else 0.0,
                    'type': venmo_type_to_enum(row['Type']),
                    'source': row['Funding Source'],
                    'destination': row['Destination'],
                }
                transaction = VenmoTransaction(**data)
                running_total += transaction.amount
                self.transactions[transaction.id] = transaction
            if (beginning_balance + running_total - ending_balance > 1e-6):
                raise Exception('venmo statement amounts don\'t reconcile')


    def to_lunchmoney(self,
        transaction: VenmoTransaction,
        asset_id: int,
        venmo_user: str,
        transfer_category_id: int,
    ) -> LunchMoneyTransactionInsert:
        """
        Convert Venmo transaction to Lunch money transaction

        date: datetime.date
        payee: str
        amount: float
        category: LunchMoneyCategory
        status: str
        is_group: bool
        currency: str = 'usd'
        asset: Optional[LunchMoneyAsset] = None
        notes: Optional[str] = ''
        external_id: Optional[str] = None

        Samuel Friedman

        """
        if transaction.type == TransactionType.payment:
            payee = transaction.from_ if transaction.to == venmo_user else transaction.to
            payee = payee + ': ' + transaction.note if transaction.note else payee
            if len(payee) > 140:  # lunch money payee is maximum 140 characters
                payee = payee[:140]
            category_id = None
        elif transaction.type == TransactionType.transfer:
            category_id = transfer_category_id
            payee = "Venmo Transfer"
        data = {
            'asset_id': asset_id,
            'date': transaction.date,
            'amount': transaction.amount,
            'category_id': category_id,
            'payee': payee,
            'external_id': transaction.id,  # venmo transaction id
        }
        note = transaction.note + ', ' if transaction.note else ''
        note += f'imported: {datetime.date.today().isoformat()}, '
        note += f'venmo_id: {transaction.id} '
        data['notes'] = note
        lm_transaction = LunchMoneyTransactionInsert(**data)
        return lm_transaction
