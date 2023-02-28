""" Lunchmoney transactions to sqlite database """

import asyncio
import re
from typing import List, Optional, Union
from datetime import date

from databases import Database
from sqlalchemy import select, insert, update

from acct.database.models import (
    Journal,
    Account,
    Transaction,
    Entry,
    Tag,
    TagTransaction,
    TagEntry,
)

from acct.lunchmoney import (
    LunchMoney,
    LunchMoneyAsset,
    LunchMoneyCategory,
    LunchMoneyPlaidAccount,
    LunchMoneyTag,
    LunchMoneyTransaction
)


class LunchMoneyDbConverter:

    _queue: asyncio.Queue

    def __init__(self, lunchmoney: LunchMoney, db_url: str):
        self.lunchmoney = lunchmoney
        self.db_url = db_url
        # self.db = Database(db_url)
        self._journal = None
        self._accounts = []
        self._tags = []
        self._transactions = []
        self._entries = []


    async def import_transactions(
        self,
        journal_id: int,
        start_date: date,
        end_date: date,
    ):
        """ Query Lunchmoney API and import transactions to database """
        # Query Lunchmoney for accounts, categories, tags, and assets
        await self.lunchmoney.load_foreign_key_objects()

        self._queue = asyncio.Queue()

        # Load journal from db
        async with Database(self.db_url) as db:
            stmt = select(Journal).where(Journal.c.id == journal_id)
            journal = await db.fetch_one(query=stmt)
            self._journal = journal

        # Start db_worker
        task = asyncio.create_task(self.db_worker(self._queue), name='db_worker')

        # Query Lunchmoney for transactions
        async for lm_txn in self.lunchmoney.iter_transactions(start_date, end_date):
            await self._queue.put(lm_txn)

        await self._queue.join()
        return

    async def db_worker(self, queue: asyncio.Queue):
        """ Worker task to upsert transactions from Lunchmoney """
        try:
            async with Database(self.db_url) as db:
                while not queue.empty():
                    lm_txn: LunchMoneyTransaction = await queue.get()
                    await self.upsert_lunchmoney_transaction_to_db(db=db, lm_txn=lm_txn)
                    queue.task_done()

        except asyncio.CancelledError:
            ...
        except Exception:
            ...


    async def upsert_lunchmoney_transaction_to_db(self, db: Database, lm_txn: LunchMoneyTransaction):
        """ Use database connection to update or insert Lunchmoney Transaction """
        journal_id = self._journal['id']
        async with db.transaction():
            # Find account foreign key
            stmt = select(Account.c.id).where(Account.c.lunchmoney_category_id == lm_txn.category.id)
            account_id = await db.fetch_one(query=stmt)
            if not account_id:
                account_id = await self.insert_account(db, lm_txn.category)
            # Find tag foreign key
            stmt = select(Tag.c.id).where(Tag.c.lunchmoney_id.in_([tag.id for tag in lm_txn.tags]))
            tag_ids = await db.fetch_all(query=stmt)
            if not tag_ids:
                tag_ids = await self.insert_tags(db, lm_txn.tags)



            stmt = select(Transaction)
            values = {}
            res = await db.execute(query=stmt, values=values)


    async def insert_account(self, db: Database, data) -> int:
        """ Insert a new account into database
        Return new account id

        Recursive function to create this account and all parent accounts
        """


        data['']
        return 0

    async def insert_tags(self, db: Database, data) -> List[int]:
        """ Insert a new account into database
        Return new account id
        """
        data['']
        return []


    def convert_single_transaction(self, t: LunchMoneyTransaction):
        """
        Convert LunchMoneyTransaction to Transaction DB object

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