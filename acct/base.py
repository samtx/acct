from abc import ABCMeta, abstractmethod
from acct.lunchmoney import LunchMoneyTransaction
from acct.ledger import LedgerTransaction
from typing import Union
from pathlib import Path
from collections import defaultdict


class BankClient(metaclass=ABCMeta):
    """
    Base class for reading CSV files from banking and financial institutions
    e.g. Chase, Bank of America, Venmo, Cash App

    Classes derived from BankClient should not insert or update transactions for their client
    """

    def __init__(self):
        self.transactions = {}
        self.transaction_dates = defaultdict(set)

    @abstractmethod
    def read_csv(self, filename: Union[Path, str]):
        """
        Read CSV file of transactions and save transaction objects
        """
        pass

    def save_transaction(self, transaction):
        """
        Save transaction to object data store
        """
        self.transactions[transaction.id] = transaction
        self.transaction_dates[transaction.date].add(transaction.id)

    @staticmethod
    def to_lunchmoney(transaction, asset_id, *a, **kw) -> LunchMoneyTransaction:
        """
        Convert transaction to Lunchmoney transaction
        """
        raise NotImplementedError(
            'to_lunchmoney() staticmethod is not implemented for this client'
        )

    @staticmethod
    def to_ledger(transaction, asset_id, *a, **kw) -> LedgerTransaction:
        """
        Convert transaction to Ledger transaction
        """
        raise NotImplementedError(
            'to_ledger() staticmethod is not implemented for this client'
        )


class PersonalFinanceClient(metaclass=ABCMeta):
    """
    Base class for using API of personal finance apps
    e.g. Lunchmoney, Splitwise, Ledger CLI

    Classes derived from BankClient should be able to insert, update, or delete transactions for their client
    """

    def __init__(self):
        self.transactions = {}
        self.transaction_dates = defaultdict(set)

    def save_transaction(self, transaction):
        """
        Save transaction to object data store
        """
        self.transactions[transaction.id] = transaction
        self.transaction_dates[transaction.date].add(transaction.id)

    @staticmethod
    def to_lunchmoney(transaction, asset_id, *a, **kw) -> LunchMoneyTransaction:
        """
        Convert transaction to Lunchmoney transaction
        """
        raise NotImplementedError(
            'to_lunchmoney() staticmethod is not implemented for this client'
        )

    @staticmethod
    def to_ledger(transaction, asset_id, *a, **kw) -> LedgerTransaction:
        """
        Convert transaction to Ledger transaction
        """
        raise NotImplementedError(
            'to_ledger() staticmethod is not implemented for this client'
        )





