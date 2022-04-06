# lunchmoney transactions to ledger file
from __future__ import annotations

import asyncio
import datetime
import re
from typing import List, Optional, Union

import httpx
from pydantic import BaseModel, Field

from acct.ledger import (
    LedgerTransaction,
    LedgerTransactionPost,
    LedgerTag,
    LedgerNote,
    LedgerStatus,
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
    updated_at: str
    created_at: str
    is_group: bool
    description: Optional[str] = ""
    group_id: Optional[int] = None


class LunchMoneyAsset(BaseModel):
    id: int
    type_name: str
    name: str
    balance: str
    balance_as_of: str
    currency: str
    created_at: str
    subtype_name: Optional[str] = ""
    institution_name: Optional[str] = ""


class LunchMoneyPlaidAccount(BaseModel):
    id: int
    date_linked: str
    name: str
    type: str
    subtype: str
    mask: str
    institution_name: str
    status: str
    balance: str
    currency: str
    balance_last_update: str
    limit: Optional[int] = None
    last_import: str = None


class LunchMoneyTransactionBase(BaseModel):
    date: datetime.date
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
            "date": t.date,
            "payee": t.payee,
            "posts": [],
            "tags": [LedgerTag(name=tag.name) for tag in t.tags],
            "status": LedgerStatus.PENDING if t.status == "uncleared" else LedgerStatus.CLEARED,
        }
        data["notes"] = [LedgerNote(t.notes)] if t.notes is not None else []
        data['tags'].append(LedgerTag('lm', str(t.id)))
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
        data["posts"] = [
            LedgerTransactionPost(account=debit_account, amount=t.amount, date=data['date']),
            LedgerTransactionPost(account=credit_account, amount=-t.amount, date=data['date']),
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
