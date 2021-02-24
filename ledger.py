# lunchmoney transactions to ledger file
from __future__ import annotations
import datetime
import re
from typing import List, Optional
import asyncio

from pydantic import BaseModel

from utils import datestr_to_date


class LedgerTransactionItem(BaseModel):
    account: str
    amount: float


class LedgerTransactionTag(BaseModel):
    name: str


class LedgerTransaction(BaseModel):
    date: datetime.date
    payee: str
    items: List[LedgerTransactionItem]
    raw: str = ''  # raw strings from ledger file
    status: str = ''
    note: str = ''
    tags: Optional[List[LedgerTransactionTag]]
    lm_id: Optional[int]


class Ledger:
    """
    Ledger file operations
    """
    comments = ';#%|*'
    commnets_regex = re.compile(r"\s*[;#%|\*]")

    def __init__(self, ledger_file):
        self.fname = ledger_file
        self.transactions = dict()
        self.accounts = dict()
        self.transaction_regex = re.compile(r"^\d")
        self.transaction_first_line_regex = re.compile(r"^(\d{4}[-\/]\d{2}[-\/]\d{2})\s+([*!])?\s*([\w\d. &:]*)\s*([;#%|*][ \w\d]*)?$")
        self.lm_txn_regex = re.compile(r"(?<=[lm|LM|Lm]:)\s*\d+")
        # self.currency_regex = re.compile(r"\$(\d{1,3}(\,\d{3})*|(\d+))(\.\d{2})?")
        self.line_groups = []
        self.raw = ''
        self.raw_header = ''
        self.transactions = {}  # store by lunch money id
        self.counter = 0

    def incr(self):
        self.counter += 1
        return self.counter

    def parse(self):
        """
        Read ledger file and parse contents
        """
        self.gather_transactions()
        self.process_transactions()

    def gather_transactions(self):
        """
        Read ledger file and gather transactions as line groups
        """
        first_transaction = False
        with open(self.fname, 'r') as f:
            while True:
                line = f.readline()
                self.raw += line
                txn_group = []
                if self.transaction_regex.match(line):
                    first_transaction = True
                    txn_group.append(line)
                    # iterate over the next group of lines until a blank line is encountered
                    line = f.readline()
                    self.raw += line
                    while line.rstrip():
                        txn_group.append(line)
                        line = f.readline()
                        self.raw += line
                    self.line_groups.append(txn_group)

                elif not first_transaction:
                    header_lines = self.raw_header.splitlines()
                    if (len(header_lines) > 0) and (not header_lines[-1].strip()) and (not line.strip()):
                        continue
                    else:
                        self.raw_header += line

                elif not line:
                    break

    def save_transaction(self, t: Transaction):
        """
        Save transaction by lunch money id
        """
        _id = t.lm_id if t.lm_id else f'ledger-only-{self.incr()}'
        self.transactions[_id] = t

    def process_transactions(self):
        """
        Process transaction text groups
        """
        for txn in self.line_groups:
            t = self.process_transaction(txn)
            self.save_transaction(t)
            # print(t.json(indent=2))

    def process_transaction(self, txn_lines):
        """
        Process transaction from group of lines
        """
        # process first line
        s = self.transaction_first_line_regex.search(txn_lines[0])
        datestr, status_char, payee, note = s[1], s[2], s[3], s[4]
        note = "" if not note else note
        date = datestr_to_date(datestr)
        if status_char == '*':
            status = 'cleared'
        elif status_char == '!':
            status = 'pending'
        else:
            status = ''

        txn_data = {
            'date': date,
            'payee': payee,
            'status': status,
            'note': note,
            'raw': ''.join(txn_lines)
        }
        # get transaction items
        txn_items = []
        for line in txn_lines[1:]:

            s = re.search(r"^\s+[" + self.comments + r"]\s*(.*)$", line)
            if (s) and (s[1] is not None):
                # process comments
                comment_data = self.process_transaction_comment(s[1])
                if 'tags' in comment_data:
                    txn_data['tags'].extend(comment_data['tags'])
                if 'note' in comment_data:
                    txn_data['note'] += "\n" + comment_data['note']
                if 'lm_id' in comment_data:
                    txn_data['lm_id'] = comment_data['lm_id']
            else:
                # process line item
                txn_item = self.process_transaction_item(line)
                txn_items.append(txn_item)
        txn_data.update({'items': txn_items})
        txn = LedgerTransaction(**txn_data)
        return txn

    def process_transaction_comment(self, comment_line):
        """
        extract note, tags, and lunch money id number
        """
        if tags := re.findall(r":([-\w\d&]+ *[-\w\d&]+):", comment_line):
            return {'tags': tags}
        if lm_id := re.search(r"(?<=[lm|LM|Lm]:)\s*\d+", comment_line):
            return {'lm_id': int(lm_id[0])}
        else:
            return {'note': comment_line}

    def process_transaction_item(self, line_item):
        """
        (indented)  Expenses:Food:Alcohol & Bars        $  388.19
        (indented)  Liabilities:Chase Sapphire Visa     $ -388.19
        """
        # split accounts and amounts on double space and tabs
        m = re.search(r"^\s*([a-zA-Z0-9:& ]+)( {2,}|\t)\s*", line_item)
        account = m[1].rstrip()
        m = re.search(r"\$?(([-+]?\d{1,3}(\,\d{3})*|(\d+))(\.\d{2})?)", line_item)
        amount = float(m[1].replace(',', ''))
        txn_item = LedgerTransactionItem(account=account, amount=amount)
        return txn_item

