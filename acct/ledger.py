# lunchmoney transactions to ledger file
from __future__ import annotations

import datetime
import pathlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, NamedTuple, Optional, Iterable

from prompt_toolkit.history import History, InMemoryHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory, AutoSuggest, Suggestion
from prompt_toolkit.completion import Completer, Completion


def datestr_to_date(datestr):
    """
    Parse year/month/day string to datetime.date
    """
    datestr = datestr.replace("-", "/")
    yr, mo, dy = datestr.split("/")
    date = datetime.date(int(yr), int(mo), int(dy))
    return date


@dataclass
class LedgerTransactionItem:
    account: str
    amount: Optional[float]
    note: str = ''


@dataclass
class LedgerTransactionTag:
    name: str
    value: str = ''

    def write(self):
        return f":{self.name}:"

    def write_item(self):
        return f"{self.name}: {self.value}"


@dataclass
class LedgerTransaction:
    date: datetime.date
    payee: str
    items: List[LedgerTransactionItem] = field(default_factory=list)
    raw: str = ""  # raw strings from ledger file
    status: str = ""
    note: str = ""
    tags: Optional[List[LedgerTransactionTag]] = field(default_factory=list)
    lm_id: Optional[int] = None
    id: str = ''

    def __hash__(self):
        return hash(self.write())

    def validate_amounts(self):
        """
        """
        pass

    def status_char(self):
        if self.status == "cleared":
            ch = "*"
        elif self.status == "pending":
            ch = "!"
        else:
            ch = ""
        return ch

    def write(self):
        """Create string for writing to ledger file"""
        indent = " " * 4
        lines = f'{self.date.strftime(r"%Y/%m/%d")} {self.status_char()} {self.payee}\n'
        # write note
        if self.note:
            if hasattr(self.note, "__len__"):
                for note_line in self.note.splitlines():
                    lines += f"{indent}; {note_line}\n"
            else:
                lines += f"{indent}; {self.note}\n"
        # write tags
        if len(self.tags) > 0:
            tags_no_value = []
            tags_with_value = []
            for tag in self.tags:
                if tag.value:
                    tags_with_value.append(f"{tag.name}: {tag.value}")
                else:
                    tags_no_value.append(f":{tag.name}:")
            if len(tags_no_value) > 0:
                lines += f"{indent}; " + ", ".join(tags_no_value) + "\n"
            for tag in tags_with_value:
                lines += f"{indent}; " + tag + "\n"

        # write lunchmoney id
        if self.lm_id:
            lines += f"{indent}; lm_id: {self.lm_id}\n"

        # write items
        for item in sorted(self.items, key=lambda x: -x.amount if x.amount is not None else 1e20):
            if item.amount:
                account_string = f"{indent}{item.account:40}  $ {item.amount:>8.2f}\n"
            else:
                account_string = f"{indent}{item.account:40}  {' ':>10s}\n"
            if item.note:
                account_string += f" ; {item.note}"
            lines += account_string
        lines = lines.rstrip()
        return lines


class LedgerAccountCompleter(Completer):
    """
    autocompleter for prompt_toolkit
    """
    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    def get_completions(self, document, complete_event) -> Iterable[Completion]:
        current_str = document.get_word_before_cursor().lower()
        for account in self.ledger.accounts.keys():
            if account.lower().startswith(current_str):
                yield Completion(account, start_position=-len(current_str))


class LedgerPayeeAutoSuggest(AutoSuggest):
    """
    autosuggester for payees
    """
    def __init__(self, ledger):
        self.ledger = ledger

    def get_suggestion(self, buffer, document):
        # Consider only the last line for the suggestion.
        text = document.text.rsplit("\n", 1)[-1]
        payees = list(self.ledger.payees.keys())
        # Find first matching line in history.
        for payee_str in reversed(payees):
            if payee_str.startswith(text):
                return Suggestion(payee_str[len(text) :])
        return None


class FirstLineTransactionGroup(NamedTuple):
    date: datetime.date
    status: str
    payee: str
    note: str


class Ledger:
    """
    Ledger file operations
    """
    comments = ";#%|"
    commnets_regex = re.compile(r"\s*[;#%|\*]")
    tag_without_value_regex = re.compile(r":[\w:]+:")
    tag_with_value_regex = re.compile(r"^[\w]+:\s?\w?[\w\s?!;'\"^$%&]*$")
    transaction_first_line_regex = re.compile(r"^(\d{4}[-\/]\d{2}[-\/]\d{2})\s+([*! ])?(.*)$")
    payee_and_note_regex = re.compile(r"^(.*)(( {2,}|\t|\n|\r\n)([" + comments + r"])(.*))?$")

    lm_txn_regex = re.compile(r"(?<=[lm|LM|Lm]:)\s*\d+")
    transaction_regex = re.compile(r"^\d")

    def __init__(self, ledger_file):
        self.fname = ledger_file
        self.transactions = dict()
        self.accounts = defaultdict(set)
        self.payees = defaultdict(set)
        self.dates = defaultdict(set)
        self.line_groups = []
        self.raw = ""
        self.raw_header = ""
        self.transactions = {}  # store by lunch money id
        self.counter = 0
        self.account_completer = None
        self.payee_suggestor = None
        self.prompt_history = None

    def set_prompt_helpers(self):
        """
        Create Completer, Suggestor, and History objects for prompt_toolkit
        """
        self.account_completer = LedgerAccountCompleter(self)
        self.payee_suggestor = LedgerPayeeAutoSuggest(self)
        self.prompt_history = InMemoryHistory()

    def incr(self):
        self.counter += 1
        return self.counter

    def parse(self):
        """
        Read ledger file and parse contents
        """
        if not pathlib.Path(self.fname).exists():
            print(f"Ledger file '{self.fname}' does not exist.")
            return None
        self._gather_transactions()
        for t_group in self.line_groups:
            t = self._process_transaction(t_group)
            self.save_transaction(t)

    def _gather_transactions(self):
        """
        Read ledger file and gather transactions as line groups
        """
        first_transaction = False
        with open(self.fname, "r") as f:
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
                    if (
                        (len(header_lines) > 0)
                        and (not header_lines[-1].strip())
                        and (not line.strip())
                    ):
                        continue
                    else:
                        self.raw_header += line
                elif not line:
                    break

    def save_transaction(self, t: LedgerTransaction):
        """
        Save transaction by lunch money id
        """
        _id = t.lm_id if t.lm_id else f"ledger-{self.incr()}"
        t.id = _id
        self.transactions[_id] = t
        self.payees[t.payee].add(_id)
        self.dates[t.date].add(_id)
        for item in t.items:
            self.accounts[item.account].add(_id)

    def get_transactions_by_date(self, date_: datetime.date) -> List[LedgerTransaction]:
        t_ids = self.dates[date_]
        if len(t_ids) == 0:
            return []
        transactions = [self.transactions[id_] for id_ in t_ids]
        return transactions

    def find_similar_transactions(self, t: LedgerTransaction):
        """
        Search saved transaction data for similar transactions
        """
        # check similar dates
        t_subset = self.get_transactions_by_date(t.date)
        if not t_subset:
            return set()
        # check similar amounts
        similar_transactions = set()
        amounts = {item.amount for item in t.items}
        for tx in t_subset:
            for item in tx.items:
                if item.amount in amounts:
                    similar_transactions.add(tx)
                    break
        # check similar account types
        account_types = {item.account.split(':', maxsplit=1)[0].lower() for item in t.items}
        for tx in similar_transactions:
            for item in tx.items:
                sim_account_type = item.account.split(':', maxsplit=1)[0].lower()
                if sim_account_type in account_types:
                    similar_transactions.add(tx)
                break
        return similar_transactions

    def update(self, ledger_transactions: List[LedgerTransaction]):
        """
        Update Ledger object with new transactions based on lunch money ID
        """
        for t in ledger_transactions:
            self.transactions[t.lm_id] = t

    def write(self):
        output_str = self.raw_header
        for t in sorted(self.transactions.values(), key=lambda x: x.date):
            # only use transaction attributes if it is tied to a Lunch Money ID
            # otherwise just write the raw strings
            if t.raw:
                transaction_string = t.raw
            else:
                transaction_string = t.write()
            output_str += transaction_string + "\n"
        return output_str

    def _process_transaction(self, txn_lines):
        """
        Process transaction from group of lines
        """
        # process first line
        res = self._parse_first_line_of_transaction_group(txn_lines[0])
        txn_data = {
            "date": res.date,
            "payee": res.payee,
            "status": res.status,
            "note": res.note,
            "tags": [],
            "raw": "".join(txn_lines),
        }
        # get transaction items
        txn_items = []
        for line in txn_lines[1:]:
            result = re.search(r"^\s+[" + self.comments + r"]\s*(.*)$", line)
            if (result) and (len(result.regs) >= 2):
                # process comments
                comment = result[1]
                if matches := self.tag_with_value_regex.findall(comment):
                    tag = self._parse_tag_with_values(matches)
                    txn_data['tags'].extend([tag])
                elif matches := self.tag_without_value_regex.findall(comment):
                    tags = self._parse_tag_without_values(matches)
                    txn_data['tags'].extend(tags)
                elif lm_id := re.search(r"(?<=[lm|LM|Lm]:)\s*\d+", comment):
                    tag = LedgerTransactionTag(name='lm_id', value=int(lm_id[0]))
                    txn_data['tags'].extend([tag])
                else:
                    txn_data['note'] += '\n' + comment.strip()
            else:
                # process line item
                txn_item = self._process_transaction_item(line)
                txn_items.append(txn_item)
        txn_data.update({"items": txn_items})
        txn = LedgerTransaction(**txn_data)
        if len(txn_items) <= 1:
            raise Exception(f"Less than two item entries for ledger transaction: {txn}")
        return txn

    def _parse_first_line_of_transaction_group(self, line: str) -> FirstLineTransactionGroup:
        """
        process first line
        """
        m = self.transaction_first_line_regex.search(line)
        datestr, status_char, payee_and_note = m[1], m[2], m[3].strip()
        # get transaction note if one exists
        # check for 'hard separator' between payee and note comment character
        if m2 := re.search(r"([\t\r\n]| {2,})", payee_and_note):
            payee, note_with_comment_char = payee_and_note.split(m2[0])
            # remove leading comment character
            if m3 := re.search(r"["+ self.comments + r"]\s*(.*)", note_with_comment_char):
                note = m3[1]
            else:
                note = ""
        else:
            payee, note = payee_and_note, ""

        date = datestr_to_date(datestr)
        if status_char == "*":
            status = "cleared"
        elif status_char == "!":
            status = "pending"
        else:
            status = ""
        payee, note = payee.strip(), note.strip()
        res = FirstLineTransactionGroup(date=date, status=status, payee=payee, note=note)
        return res

    def _parse_tag_without_values(self, matches: re.Match) -> List[LedgerTransactionTag]:
        """
        check to see if tag comment matches
        ; :tag1:tag2:tag3:
        """
        tags = []
        for match in matches:
            match_tags = match.strip(':').split(':')
            tags.extend([LedgerTransactionTag(name=tag) for tag in match_tags])
        return tags

    def _parse_tag_with_values(self, matches: re.Match) -> LedgerTransactionTag:
        """
        check to see if tag comment matches
        ;  tagname: tagvalue
        """
        tag_items = matches[0].split(':')
        if len(tag_items) != 2:
            raise Exception('Tag parsing for tag \'{tag_string}\' failed')
        tag_name, tag_value = (item.strip() for item in tag_items)
        return LedgerTransactionTag(name=tag_name, value=tag_value)

    def _process_transaction_item(self, line_item):
        """
        (indented)  Expenses:Food:Alcohol & Bars        $  388.19
        (indented)  Liabilities:Chase Sapphire Visa     $ -388.19
        """
        # split accounts and amounts on double space and tabs
        m = re.search(r"^\s*([a-zA-Z0-9:& .]+)( {2,}|\t|\n|\r\n)\s*", line_item)
        account = m[1].rstrip()
        # add some currency string validation later.
        # m_amount = re.search(r"")
        # amount_string = re
        # # For now, just remove commas and convert to float
        # amount_string = line_item[m.].replace(m[1],'')
        amount_string = line_item.replace(m[0],'').strip()
        m_amount = re.search(r"^\$?\s*([-+]?[\d+\.,]*)", amount_string)
        if len(amount_string) > 0 and m_amount:
            amount_string = m_amount[1].replace(',','')
            amount = float(amount_string)
        else:
            amount = None
        # find line item note
        m_note = re.search(r"^.*[" + self.comments + r"]\s*(.*)$", line_item)
        if m_note:
            note = m_note[1]
        else:
            note = None
        txn_item = LedgerTransactionItem(account=account, amount=amount, note=note)
        return txn_item
