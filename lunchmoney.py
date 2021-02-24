# lunchmoney transactions to ledger file
from __future__ import annotations
import datetime
import re
import os
from typing import List, Optional
import asyncio

from pydantic import BaseModel
import aiohttp

from utils import datestr_to_date
from ledger import LedgerTransaction, LedgerTransactionItem, LedgerTransactionTag


def split_dict_by_id(data: List):
    new_dict = dict([(x.pop('id'), x) for x in data])
    return new_dict




class LunchMoneyTag(BaseModel):
    id: int
    name: str
    description: Optional[str] = None


class LunchMoneyCategory(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_income: bool
    exclude_from_budget: bool
    exclude_from_totals: bool
    updated_at: str
    created_at: str
    is_group: bool
    group_id: Optional[int]


class LunchMoneyAsset(BaseModel):
    id: int
    type_name: str
    subtype_name: Optional[str]
    name: str
    balance: str
    balance_as_of: str
    currency: str
    institution_name: Optional[str]
    created_at: str


class LunchMoneyPlaidAccount(BaseModel):
    id: int
    date_linked: str
    name: str
    type: str
    subtype: str
    mask: str
    institution_name: str
    status: str
    last_import: str
    balance: str
    currency: str
    balance_last_update: str
    limit: Optional[int]


class LunchMoneyTransaction(BaseModel):
    id: int
    date: datetime.date
    payee: str
    amount: float
    currency: str = 'usd'
    category_id: int
    category: LunchMoneyCategory
    status: str
    is_group: bool
    tags: Optional[List[LunchMoneyTag]] = []
    asset: Optional[LunchMoneyAsset]
    plaid_account: Optional[LunchMoneyPlaidAccount]
    notes: Optional[str]
    recurring_id: Optional[int]
    group_id: Optional[int]
    parent_id: Optional[int]
    external_id: Optional[str]




class LunchMoney:
    def __init__(self, lm_access_token):
        self.token = lm_access_token
        self.base_url = "https://dev.lunchmoney.app/v1/"
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.categories = {}
        self.assets = {}
        self.plaid_accounts = {}

    def get_transactions(self, params):
        loop = asyncio.get_event_loop()
        tasks = [
            self.fetch('categories'),
            self.fetch('assets'),
            self.fetch('plaid_accounts'),
            self.fetch('transactions', params),
        ]
        results = loop.run_until_complete(asyncio.gather(*tasks))
        self.categories = self.json_to_pydantic(LunchMoneyCategory, results[0])
        self.assets = self.json_to_pydantic(LunchMoneyAsset, results[1])
        self.plaid_accounts = self.json_to_pydantic(LunchMoneyPlaidAccount, results[2])
        transactions = results[3]
        uncategorized = LunchMoneyCategory.construct(id=-1, name='Uncategorized', is_income=False)
        # ignore group transactions
        transactions[:] = [t for t in transactions if not t['is_group']]
        for t in transactions:
            if category_id := t['category_id']:
                t['category'] = self.categories[t['category_id']]
            else:
                t['category_id'] = -1
                t['category'] = uncategorized
            if not t['tags']:
                t['tags'] = []
            if asset_id := t['asset_id']:
                t['asset'] = self.assets[asset_id]
            elif plaid_id := t['plaid_account_id']:
                t['plaid_account'] = self.plaid_accounts[plaid_id]
            else:
                msg = f"No account listed for transaction #{t['id']} - {t['payee']} on {t['date']} for {t['amount']} {t['currency']}"
                raise Exception(msg)
        lm_transactions = [LunchMoneyTransaction(**t) for t in transactions]
        return lm_transactions

    def json_to_pydantic(self, model, data_list):
        data = [model(**x) for x in data_list]
        new_dict = {d.id: d for d in data}
        return new_dict

    async def fetch(self, resource: str, params: dict = None):
        """
        async get request for transaction data
        """
        if params is None:
            params = {}
        async with aiohttp.ClientSession() as session:
            async with session.get(self.base_url + resource, headers=self.headers, params=params) as resp:
                data = await resp.json()
                return data[resource]

    def to_ledger(self, t: LunchMoneyTransaction) -> LedgerTransaction:
        """
        Convert LunchMoneyTransaction to LedgerTransaction object

        categories that aren't expenses:
            "Payment, Transfer"
            "Adjustment"
            "Income"
            "Withdrawal"
            "Splitwise"
        """
        data = {
            'lm_id': t.id,
            'date': t.date,
            'payee': t.payee,
            'note': t.notes if t.notes is not None else '',
            'items': [],
            'tags': [LedgerTransactionTag(name=tag.name) for tag in t.tags],
            'status': 'pending' if t.status == 'uncleared' else 'cleared'
        }

        if t.category.is_income:
            # treat transaction as income
            debit_account, credit_account = self.ledger_accounts_for_income(t)

        elif t.category in ['Withdrawal', 'Payment, Transfer', 'Splitwise', 'Adjustment']:
            # treat transaction as transfer
            # debit_account, credit_account = self.ledger_accounts_for_transfer(t)
            pass

        else:
            # treat transaction as expense
            debit_account, credit_account = self.ledger_accounts_for_expense(t)

        data['items'] = [
            LedgerTransactionItem(account=debit_account, amount=t.amount),
            LedgerTransactionItem(account=credit_account, amount=-t.amount)
        ]
        ledger_transaction = LedgerTransaction(**data)
        return ledger_transaction

    def asset_to_ledger_account(self, asset: LunchMoneyAsset):
        if asset.type_name == 'credit':
            return f'Liabilities:{asset.name}'
        elif asset.type_name == 'cash':
            return f'Assets:{asset.name}'
        else:
            msg = f'Lunch Money asset type {asset.type_name} not implemented'
            raise NotImplementedError(msg)

    def plaid_to_ledger_account(self, plaid_account: LunchMoneyPlaidAccount):
        if plaid_account.type == 'credit':
            return f'Liabilities:{plaid_account.institution_name} {plaid_account.name}'
        elif plaid_account.type in ['depository', 'cash']:
            return f'Assets:{plaid_account.institution_name} {plaid_account.name}'
        else:
            msg = f'Lunch Money plaid account type {plaid_account.type} not implemented'
            raise NotImplementedError(msg)

    def ledger_accounts_for_transfer(self, t: LunchMoneyTransaction):
        return (None, None)

    def ledger_accounts_for_income(self, t: LunchMoneyTransaction):
        """
        get ledger accounts for income transaction
        """
        negative_account = f'Income:{t.payee}'
        if asset := t.asset:
            positive_account = self.asset_to_ledger_account(asset)
        elif plaid_account := t.plaid_account:
            positive_account = self.plaid_to_ledger_account(plaid_account)
        if 'Liabilities' in positive_account:
            msg = f'Income transaction cannot post to account {positive_account}'
            raise Exception(msg)
        return (positive_account, negative_account)

    def ledger_accounts_for_expense(self, t: LunchMoneyTransaction):
        """
        t: transaction json from Lunch Money
        get ledger account string from expense category
        """
        # get expense account chain
        category = t.category
        expense_account_list = [category.name]
        while group_id := category.group_id:
            category = self.categories[group_id]
            expense_account_list.insert(0, category.name)
        expense_account_list.insert(0, 'Expenses')
        positive_account = ':'.join(expense_account_list)

        # get credit account
        if asset := t.asset:
            negative_account = self.asset_to_ledger_account(asset)
        elif plaid_account := t.plaid_account:
            negative_account = self.plaid_to_ledger_account(plaid_account)


        return (positive_account, negative_account)
