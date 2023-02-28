# lunchmoney transactions to ledger file
from __future__ import annotations

import re
from typing import List, Optional, Union

from attr import has


from acct.ledger import (
    Ledger,
    LedgerTransaction,
    LedgerTransactionPost,
    LedgerTag,
    LedgerNote,
    LedgerStatus,
)
from acct.lunchmoney import (
    LunchMoney,
    LunchMoneyAsset,
    LunchMoneyCategory,
    LunchMoneyPlaidAccount,
    LunchMoneyTag,
    LunchMoneyTransaction
)


class LunchMoneyLedgerConverter:

    def __init__(self, lunchmoney: LunchMoney, ledger: Ledger):
        self.lunchmoney = lunchmoney
        self.ledger = ledger


    def to_ledger(
        self,
        transactions: Union[LunchMoneyTransaction, List[LunchMoneyTransaction]]
    ):
        if not hasattr(transactions, '__iter__'):
            transactions = (transactions, )
        for t in transactions:
            ledger_t = self.single_transaction_to_ledger(t)
        return

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