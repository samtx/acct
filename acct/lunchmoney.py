# lunchmoney transactions to ledger file
from __future__ import annotations

import asyncio
import datetime
import re
from typing import List, Optional, Union, Dict, Any, AsyncGenerator
from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx
from pydantic import BaseModel, Field

from acct.ledger import (
    LedgerTransaction,
    LedgerTransactionItem,
    LedgerTransactionTag,
)


class LunchMoneyTag(BaseModel):
    id: int
    name: str
    description: Optional[str] = ""


class LunchMoneyCategory(BaseModel):
    id: int
    name: str
    is_income: bool
    exclude_from_budget: bool
    exclude_from_totals: bool
    updated_at: datetime
    created_at: datetime
    is_group: bool
    description: Optional[str] = ""
    group_id: Optional[int] = None


class LunchMoneyAsset(BaseModel):
    id: int
    type_name: str
    name: str
    balance: str
    balance_as_of: datetime
    currency: str
    created_at: datetime
    subtype_name: Optional[str] = ""
    institution_name: Optional[str] = ""


class LunchMoneyPlaidAccount(BaseModel):
    id: int
    date_linked: datetime
    name: str
    type: str
    subtype: str
    mask: str
    institution_name: str
    status: str
    last_import: datetime
    balance: str
    currency: str
    balance_last_update: datetime
    limit: Optional[int] = None


class LunchMoneyTransactionBase(BaseModel):
    date: date
    payee: str
    amount: float
    status: str = "uncleared"
    is_group: bool = False
    currency: str = "usd"
    tags: Optional[List[LunchMoneyTag]] = Field(default_factory=list)
    notes: Optional[str] = ""
    recurring_id: Optional[int] = None
    group_id: Optional[int] = None
    parent_id: Optional[int] = None
    external_id: Optional[str] = None


class LunchMoneyTransaction(LunchMoneyTransactionBase):
    id: int
    category: LunchMoneyCategory = None
    asset: Optional[LunchMoneyAsset] = None
    plaid_account: Optional[LunchMoneyPlaidAccount] = None

    class Config:
        extra = 'allow'


class LunchMoneyTransactionInsert(LunchMoneyTransactionBase):
    category_id: int = None
    asset_id: int = None
    plaid_account_id: int = None


class LunchMoneyTransactionInsertParams(BaseModel):
    transactions: List[LunchMoneyTransactionInsert]
    apply_rules: bool = False
    check_for_recurring: bool = False
    debit_as_negative: bool = False


class LunchMoney:
    def __init__(self, lm_access_token):
        if not lm_access_token:
            raise Exception("Lunch Money access token required")
        self.token = lm_access_token
        self.base_url = "https://dev.lunchmoney.app/v1/"
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.categories = {}
        self.assets = {}
        self.plaid_accounts = {}
        self.transactions = []


    @property
    def uncategorized_category(self) -> LunchMoneyCategory:
        """ Get category for an uncategorized Lunchmoney transaction """
        uncategorized = LunchMoneyCategory(
            id=-1,
            name="Uncategorized",
            is_income=False,
            exclude_from_budget=False,
            exclude_from_totals=False,
            updated_at=datetime.date.today().isoformat(),
            created_at=datetime.date.today().isoformat(),
            is_group=False,
        )
        return uncategorized


    async def load_foreign_key_objects(self):
        """ Query LunchMoneyAPI to get categories, assets, and plaid_accounts """
        async def fetch_resource(client: httpx.AsyncClient, endpoint: str) -> List[Dict, Any]:
            response = await client.get(endpoint)
            data = response.json()[endpoint]
            return data

        async with httpx.AsyncClient(base_url=self.base_url, headers=self.headers, http2=True) as client:
            results = await asyncio.gather(
                fetch_resource(client, 'categories'),
                fetch_resource(client, 'assets'),
                fetch_resource(client, 'plaid_accounts'),
            )

        self.categories = self.json_to_model(LunchMoneyCategory, results[0])
        self.assets = self.json_to_model(LunchMoneyAsset, results[1])
        self.plaid_accounts = self.json_to_model(LunchMoneyPlaidAccount, results[2])


    def get_transactions(self, params):
        results = self.fetch_lunch_money_data(params)
        self.categories = self.json_to_model(LunchMoneyCategory, results[0])
        self.assets = self.json_to_model(LunchMoneyAsset, results[1])
        self.plaid_accounts = self.json_to_model(LunchMoneyPlaidAccount, results[2])
        transactions = results[3]
        uncategorized = LunchMoneyCategory(
            id=-1,
            name="Uncategorized",
            is_income=False,
            exclude_from_budget=False,
            exclude_from_totals=False,
            updated_at=datetime.date.today().isoformat(),
            created_at=datetime.date.today().isoformat(),
            is_group=False,
        )
        # ignore group transactions
        transactions[:] = [t for t in transactions if not t["is_group"]]
        for t in transactions:
            t["date"] = datetime.date.fromisoformat(t["date"])
            t["amount"] = float(t["amount"])
            if category_id := t.get("category_id"):
                t["category"] = self.categories[category_id]
            else:
                t["category"] = uncategorized
            if not t["tags"]:
                t["tags"] = []
            else:
                t["tags"] = [LunchMoneyTag(**tag) for tag in t["tags"]]
            if asset_id := t["asset_id"]:
                t["asset"] = self.assets[asset_id]
            elif plaid_id := t["plaid_account_id"]:
                t["plaid_account"] = self.plaid_accounts[plaid_id]
            else:
                msg = f"No account listed for transaction #{t['id']} - {t['payee']} on {t['date']} for {t['amount']} {t['currency']}"
                raise Exception(msg)
            del t["category_id"]
            del t["asset_id"]
            del t["plaid_account_id"]

        lm_transactions = [LunchMoneyTransaction(**t) for t in transactions]
        self.transactions = lm_transactions


    def parse_lunchmoney_response(self, data: Dict[str, Any]) -> LunchMoneyTransaction:
        """ Parse json response to LunchMoneyTransaction object """
        data["date"] = datetime.date.fromisoformat(data["date"])
        data["amount"] = Decimal(data["amount"])
        data["category"] = self.categories[data['category_id']] if 'category_id' in data else self.uncategorized_category
        data["tags"] = [LunchMoneyTag(**tag) for tag in data["tags"]] if 'tags' in data else []
        data["asset"] = self.assets[data['asset_id']] if 'asset_id' in data else None
        data["plaid_account"] = self.plaid_accounts[data['plaid_account_id']] if 'plaid_account_id' in data else None
        lm_transaction = LunchMoneyTransaction(**data)
        return lm_transaction


    async def iter_transactions(self, start: date, end: date, *, limit: int = 100) -> AsyncGenerator[LunchMoneyTransaction, None, None]:
        """ Query LunchMoney API and yield an AsyncGenerator of LunchMoneyTransaction objects """
        params = {
            'start_date': start.isoformat(),
            'end_date': end.isoformat(),
            'is_group': False,   # Ignore transaction groups
        }
        offset = 0
        while True:
            params.update(limit=limit, offset=offset)
            async with httpx.AsyncClient(base_url=self.base_url, headers=self.headers) as client:
                response = await client.get('transactions', params=params)
            data = response.json()['transactions']
            for t_data in data:
                lm_txn = self.parse_lunchmoney_response(t_data)
                yield lm_txn
            if len(data) < limit:
                break
            offset += limit


    def json_to_model(self, model, data_list):
        data = [model(**x) for x in data_list]
        new_dict = {d.id: d for d in data}
        return new_dict

    def fetch_lunch_money_data(self, params):
        tasks = [
            self.fetch_resource("categories"),
            self.fetch_resource("assets"),
            self.fetch_resource("plaid_accounts"),
            self.fetch_resource("transactions", params),
        ]
        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(asyncio.gather(*tasks))
        return results

    async def fetch_resource(self, resource: str, params: dict = None):
        """
        async get request for transaction data
        """
        if params is None:
            params = {}
        async with httpx.AsyncClient(
            http2=True, base_url=self.base_url, headers=self.headers
        ) as client:
            data = await client.get(resource, params=params)
            return data.json()[resource]

    def to_ledger(
        self,
    ) -> List[LedgerTransaction]:
        ledger_txns = [self._single_transaction_to_ledger(t) for t in self.transactions]
        return ledger_txns

    def _single_transaction_to_ledger(self, t: LedgerTransaction):
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
            "lm_id": t.id,
            "date": t.date,
            "payee": t.payee,
            "note": t.notes if t.notes is not None else "",
            "items": [],
            "tags": [LedgerTransactionTag(name=tag.name) for tag in t.tags],
            "status": "pending" if t.status == "uncleared" else "cleared",
        }
        if t.category.is_income:
            # treat transaction as income
            debit_account, credit_account = self.ledger_accounts_for_income(t)
        elif t.category in [
            "Withdrawal",
            "Payment, Transfer",
            "Splitwise",
            "Adjustment",
        ]:
            # treat transaction as transfer
            debit_account, credit_account = self.ledger_accounts_for_transfer(t)
        else:
            # treat transaction as expense
            debit_account, credit_account = self.ledger_accounts_for_expense(t)
        data["items"] = [
            LedgerTransactionItem(account=debit_account, amount=t.amount),
            LedgerTransactionItem(account=credit_account, amount=-t.amount),
        ]
        ledger_transaction = LedgerTransaction(**data)
        return ledger_transaction

    def asset_to_ledger_account(self, asset: LunchMoneyAsset):
        if asset.type_name == "credit":
            return f"Liabilities:{asset.name}"
        elif asset.type_name == "cash":
            return f"Assets:{asset.name}"
        else:
            msg = f"Lunch Money asset type {asset.type_name} not implemented"
            raise NotImplementedError(msg)

    def plaid_to_ledger_account(self, plaid_account: LunchMoneyPlaidAccount):
        if plaid_account.type == "credit":
            return f"Liabilities:{plaid_account.institution_name} {plaid_account.name}"
        elif plaid_account.type in ["depository", "cash"]:
            return f"Assets:{plaid_account.institution_name} {plaid_account.name}"
        else:
            msg = f"Lunch Money plaid account type {plaid_account.type} not implemented"
            raise NotImplementedError(msg)

    def lunchmoney_to_ledger_account(self, t: LunchMoneyTransaction):
        """
        Get ledger account from lunchmoney transaction
        """
        if asset := t.asset:
            account = self.asset_to_ledger_account(asset)
        elif plaid_account := t.plaid_account:
            account = self.plaid_to_ledger_account(plaid_account)
        else:
            msg = f"No account listed for transaction {t}"
            raise Exception(msg)
        return account

    def ledger_accounts_for_transfer(self, t: LunchMoneyTransaction):
        """
        Get ledger accounts for transfer or adjustment
        """
        acct_from_note_regex = re.compile(r"(?<=ledger: \").+(?=\")")
        # credits are negative amounts, debits are positive
        positive_account = self.lunchmoney_to_ledger_account(t)
        s = acct_from_note_regex.search(t.note)
        negative_account = s[0] if not s else ""
        if t.amount > 0:
            positive_account, negative_account = negative_account, positive_account
        return (positive_account, negative_account)

    def ledger_accounts_for_income(self, t: LunchMoneyTransaction):
        """
        get ledger accounts for income transaction
        """
        negative_account = f"Income:{t.payee}"
        positive_account = self.lunchmoney_to_ledger_account(t)
        if "Liabilities" in positive_account:
            msg = f"Income transaction cannot post to account {positive_account}"
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
        expense_account_list.insert(0, "Expenses")
        positive_account = ":".join(expense_account_list)
        # get credit account
        negative_account = self.lunchmoney_to_ledger_account(t)
        return (positive_account, negative_account)

    def insert_transactions(
        self,
        transactions: Union[LunchMoneyTransaction, List[LunchMoneyTransaction]],
        params: dict = None,
    ):
        if isinstance(transactions, LunchMoneyTransactionInsert):
            transactions = [transactions]
        if params is None:
            params = {}
        params["transactions"] = transactions
        data = LunchMoneyTransactionInsertParams(**params).json()
        headers = self.headers
        headers["Content-Type"] = "application/json"
        res = httpx.post(self.base_url + "transactions", headers=headers, data=data)
        return res
