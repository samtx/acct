# lunchmoney transactions to ledger file
from __future__ import annotations

import datetime
import pathlib
import uuid
from decimal import Decimal
import re
from collections import defaultdict
from enum import Enum
from dataclasses import dataclass, field, fields
from typing import List, NamedTuple, Optional, Iterable

from pytest import Instance


def datestr_to_date(datestr):
    """
    Parse year/month/day string to datetime.date
    """
    datestr = datestr.replace("-", "/")
    yr, mo, dy = datestr.split("/")
    date = datetime.date(int(yr), int(mo), int(dy))
    return date


"""
Ledger Objects

Journal
    Account
    Commodity
    Payees
    Metadata
    Metadatawithvalue

Item

Transaction(Item)
Post(Item)

A transaction has at least two posts
A transaction has a date, payee, status

An item can have a note, or metadata, or metadatavalue

"""

@dataclass
class NewLine:
    def to_string(self):
        return '\n'


@dataclass
class LedgerTagDirective:
    name: str

    def to_string(self):
        return f"tag {self.name}\n"


@dataclass
class LedgerCommodityOption:
    name: str
    value: str = ''


@dataclass
class LedgerCommodity:
    name: str
    options: Optional[List[LedgerCommodityOption]] = field(default_factory=list)

    def to_string(self, indent=4):
        indent_str = ' ' * indent
        strlist = [f'commodity {self.name}\n']
        for option in self.options:
            strlist.append(f'{indent_str}{option.name} {option.value}\n')
        return "".join(strlist)


class LedgerStatus(str, Enum):
    CLEARED = "*"
    PENDING = "!"
    UNKNOWN = ""


@dataclass
class LedgerComment:
    value: str
    date: datetime.date = None


@dataclass
class LedgerNote:
    value: str
    newline: bool = True   # this note is printed on a new line
    comment: str = ';'  # comment character

    def to_string(self, indent=4):
        indent = ' ' * indent
        if self.newline:
            prefix = f"\n{indent}{self.comment} "
        else:
            prefix = f"  {self.comment} "
        return prefix + self.value


@dataclass
class LedgerTag:
    name: str
    value: str = ''
    newline: bool = True  # this tag is printed on a new line
    comment: str = ';'  # comment character

    def to_string(self, indent=4):
        indent = ' ' * indent
        if self.newline:
            prefix = f"\n{indent}{self.comment} "
        else:
            prefix = f"  {self.comment} "
        if self.value:
            return prefix + f"{self.name}: {self.value}"
        return prefix + f":{self.name}:"


@dataclass
class LedgerItem:
    date: datetime.date
    notes: List[LedgerNote] = field(default_factory=list)
    tags: List[LedgerTag] = field(default_factory=list)


@dataclass
class LedgerTransactionPost(LedgerItem):
    account: str = ''
    amount: Optional[Decimal] = None
    commodity: str = 'USD'

    def to_string(self, indent=4, max_account_len=40):
        indent_str = ' ' * indent
        strlist = [f"\n{indent_str}{self.account:{max_account_len}s}    "]
        if self.amount is not None:
            strlist.append(f"{self.amount:>16f} {self.commodity}")
        for note in self.notes:
            strlist.append(note.to_string(indent*2))
        for tag in self.tags:
            strlist.append(tag.to_string(indent*2))
        return "".join(strlist)


@dataclass
class LedgerTransaction(LedgerItem):
    payee: str = ''
    posts: List[LedgerTransactionPost] = field(default_factory=list)
    raw: str = ''  # raw strings from ledger file
    status: LedgerStatus = LedgerStatus.UNKNOWN
    id: str = ''

    def __hash__(self):
        return hash(self.to_string())

    def validate_amounts(self):
        """
        """
        pass

    def to_string(self, indent=4):
        """Create string for writing to ledger file"""
        strlist = [f'{self.date.strftime(r"%Y-%m-%d")} {self.status.value} {self.payee}']
        for note in self.notes:
            strlist.append(note.to_string(indent))
        for tag in self.tags:
            strlist.append(tag.to_string(indent))
        # Get maximum account name length
        max_account_len = 0
        for post in self.posts:
            max_account_len = max(max_account_len, len(post.account))
        # print posts in descending order of amount
        for post in sorted(self.posts, key=lambda x: -x.amount if x.amount is not None else 1e20):
            strlist.append(post.to_string(indent, max_account_len=max_account_len))
        strlist.append('\n')
        return "".join(strlist)


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
        self.tokens = []
        self.transactions = dict()
        self.commodities = []
        self.tag_directives = []
        self.accounts = defaultdict(set)
        self.payees = defaultdict(set)
        self.dates = defaultdict(set)
        self.tags = defaultdict(set)
        self.tagsv = defaultdict(lambda: defaultdict(set))

        self.line_groups = []
        self.raw = ""
        self.raw_header = ""
        self.counter = 0

    def incr(self):
        self.counter += 1
        return self.counter

    def parse(self):
        """
        Read ledger file and parse contents
        """
        if not pathlib.Path(self.fname).exists():
            print(f"Ledger file '{self.fname}' does not exist.")
            raise FileNotFoundError

        lexer = LedgerLexer(self.fname)
        tokens = lexer.tokenize()
        self.tokens = tokens
        # Save transactions
        for token in self.tokens:
            if isinstance(token, LedgerCommodity):
                self.commodities.append(token)
            elif isinstance(token, LedgerTagDirective):
                self.tag_directives.append(token)
            elif isinstance(token, LedgerTransaction):
                self.save_transaction(token)

    def save_transaction(self, t: LedgerTransaction):
        """
        Save transaction by lunch money id
        """
        _id = t.id
        self.transactions[_id] = t
        self.payees[t.payee].add(_id)
        self.dates[t.date].add(_id)
        for tag in t.tags:
            if tag.value:
                self.tagsv[tag.name][tag.value].add(_id)
            else:
                self.tags[tag.name].add(_id)
        for post in t.posts:
            self.accounts[post.account].add(_id)
            for tag in post.tags:
                if tag.value:
                    self.tagsv[tag.name][tag.value].add(_id)
                else:
                    self.tags[tag.name].add(_id)

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

    def to_string(self, sorted=False):
        if not sorted:
            return "".join([t.to_string() for t in self.tokens])
        # Sort Ledger file in order: commodities, tag directives, transactions
        out = []
        for commodity in self.commodities:
            out.extend([commodity, NewLine()])
        for tag_directive in self.tag_directives:
            out.extend([tag_directive, NewLine()])
        for t in sorted(self.transactions.values(), key=lambda x: x.date):
            out.extend([t, NewLine()])
        return "".join([token.to_string() for token in out])


class LedgerLexer:
    comments = ";#%|"
    comments_regex = re.compile(r"\s*[;#%|\*]")
    item_comment_regex = re.compile(r"^\s+[" + comments + r"]+(.*)$")
    commodity_regex = re.compile(r"^(commodity\s)|(c\s)", flags=re.I)
    tag_directive_regex = re.compile(r"^tag\s", flags=re.I)
    tag_without_value_regex = re.compile(r":[\w:]+:")
    tag_with_value_regex = re.compile(r"^\s+\w+:[^:]*$")
    transaction_first_line_regex = re.compile(r"^(\d{4}[-\/]\d{2}[-\/]\d{2})\s+([*! ])?(.*)$")
    payee_and_note_regex = re.compile(r"^(.*)(( {2,}|\t|\n|\r\n)([" + comments + r"])(.*))?$")
    post_acount_regex = re.compile(r"^\s*([a-zA-Z0-9:& .]+)( {2,}|\t|\n|\r\n)\s*")
    post_amount_regex = re.compile(r"^\$?\s*([-+]?[\d+\.,]*)")

    def __init__(self, fname):
        self.fname = fname
        self.pos = 0
        self.line = 0
        self.file_handler = None

    def next(self):
        line = next(self.file_handler)
        self.pos += 1
        return line

    def tokenize(self):
        tokens = []
        with open(self.fname) as f:
            while f:
                try:
                    line = next(f)
                except StopIteration:
                    break
                # Match the type of token

                # Commodity
                if self.commodity_regex.match(line):
                    group = [line]
                    while line := next(f).rstrip():
                        group.append(line)
                    token = self.parse_commodity(group)
                    tokens.append(token)
                    tokens.append(NewLine())

                # Tag directive
                elif self.tag_directive_regex.match(line):
                    name = line[3:].strip()
                    token = LedgerTagDirective(name)
                    tokens.append(token)

                # Transaction
                elif self.transaction_first_line_regex.match(line):
                    group = [line]
                    while line := next(f, ""):
                        if not line.strip():
                            break
                        group.append(line)
                    token = self.parse_transaction(group)
                    tokens.append(token)
                    tokens.append(NewLine())

                # New line
                elif not line.rstrip():
                    token = NewLine()
                    tokens.append(token)

                else:
                    raise Exception(f'Parsing error: {line}')
        return tokens


    def parse_commodity(self, group):
        """
        Parse commodity directive
        """
        name = group[0].split()[1].strip()
        commodity = LedgerCommodity(name)
        for line in group[1:]:
            key, *values = (x.strip() for x in line.split())
            value = " ".join(values)
            option = LedgerCommodityOption(name=key, value=value)
            commodity.options.append(option)
        return commodity

    def parse_transaction(self, group):
        """
        Parse transaction from group of lines
        """
        # process first line
        res = self.parse_first_line_of_transaction(group[0])
        tx_data = {
            "date": res.date,
            "payee": res.payee,
            "status": res.status,
            "notes": [res.note] if res.note else [],
            "tags": [],
            "raw": "".join(group),
            "posts": [],
            "id": str(uuid.uuid4()),
        }
        # get transaction items
        remaining_lines = iter(group[1:])
        # parse transaction notes and tags
        while line := next(remaining_lines, ""):
            if result := self.item_comment_regex.match(line):
                comment = result[1]
                notes, tags = self.parse_item_comment(comment)
                tx_data["notes"].extend(notes)
                tx_data["tags"].extend(tags)
            else:
                break

        # get transaction posts
        post = self.parse_transaction_post(line, tx_data['date'])
        while line := next(remaining_lines, ""):
            if result := self.item_comment_regex.match(line):
                # get post notes and tags
                comment = result[1]
                notes, tags = self.parse_item_comment(comment)
                post.notes.extend(notes)
                post.tags.extend(tags)
            else:
                tx_data["posts"].append(post)
                post = self.parse_transaction_post(line, tx_data['date'])
        tx_data["posts"].append(post)
        tx = LedgerTransaction(**tx_data)
        if len(tx.posts) <= 1:
            raise Exception(f"Less than two post entries for ledger transaction: {tx}")
        return tx

    def parse_item_comment(self, comment):
        """
        Parses comment line for note or tags
        """
        notes, tags = [], []
        if matches := self.tag_with_value_regex.findall(comment):
            tag = self.parse_tag_with_values(matches)
            tags.extend([tag])
        elif matches := self.tag_without_value_regex.findall(comment):
            tags = self.parse_tag_without_values(matches)
        else:
            notes.append(LedgerNote(comment.strip()))
        return notes, tags

    def parse_transaction_post(self, line, date):
        """
        (indented)  Expenses:Food:Alcohol & Bars        $  388.19
        (indented)  Liabilities:Chase Sapphire Visa     $ -388.19
        """
        # split accounts and amounts on double space and tabs
        m = self.post_acount_regex.match(line)
        account = m[1].rstrip()
        # add some currency string validation later.
        # m_amount = re.search(r"")
        # amount_string = re
        # # For now, just remove commas and convert to Decimal
        # amount_string = line_item[m.].replace(m[1],'')
        amount_string = line.replace(m[0],'').strip()
        m_amount = self.post_amount_regex.match(amount_string)
        if len(amount_string) > 0 and m_amount:
            amount_string = m_amount[1].replace(',','')
            amount = Decimal(amount_string)
        else:
            amount = None
        # find line item note
        m_note = re.search(r"^.*[" + self.comments + r"]\s*(.*)$", line)
        if m_note:
            note = [LedgerNote(m_note[1], newline=False)]
        else:
            note = []
        post = LedgerTransactionPost(account=account, amount=amount, notes=note, date=date)
        return post

    def parse_first_line_of_transaction(self, line: str) -> FirstLineTransactionGroup:
        """
        Parse first line of transaction
        """
        m = self.transaction_first_line_regex.search(line)
        datestr, status_char, payee_and_note = m[1], m[2], m[3].strip()
        # get transaction note if one exists
        # check for 'hard separator' between payee and note comment character
        if m2 := re.search(r"([\t\r\n]| {2,})", payee_and_note):
            payee, note_with_comment_char = payee_and_note.split(m2[0])
            # remove leading comment character
            if m3 := re.search(r"["+ self.comments + r"]\s*(.*)", note_with_comment_char):
                note = LedgerNote(m3[1], newline=False)
            else:
                note = None
        else:
            payee, note = payee_and_note, None
        date = datestr_to_date(datestr)
        if status_char == "*":
            status = LedgerStatus.CLEARED
        elif status_char == "!":
            status = LedgerStatus.PENDING
        else:
            status = LedgerStatus.UNKNOWN
        payee = payee.strip()
        res = FirstLineTransactionGroup(date=date, status=status, payee=payee, note=note)
        return res

    def parse_tag_without_values(self, matches: re.Match) -> List[LedgerTag]:
        """
        check to see if tag comment matches
        ; :tag1:tag2:tag3:
        """
        tags = []
        for match in matches:
            match_tags = match.strip(':').split(':')
            tags.extend([LedgerTag(name=tag) for tag in match_tags])
        return tags

    def parse_tag_with_values(self, matches: re.Match) -> LedgerTag:
        """
        check to see if tag comment matches
        ;  tagname: tagvalue
        """
        tag_items = matches[0].split(':')
        if len(tag_items) != 2:
            raise Exception('Tag parsing for tag \'{tag_string}\' failed')
        tag_name, tag_value = (item.strip() for item in tag_items)
        return LedgerTag(name=tag_name, value=tag_value)

