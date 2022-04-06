from prompt_toolkit import PromptSession
from prompt_toolkit.shortcuts import prompt
from prompt_toolkit import print_formatted_text

from acct.boa import BOATransaction
from acct.ledger import (
    LedgerTransaction,
    LedgerTransactionPost,
    LedgerTag,
)
from acct.utils import datestr_to_date


def prompt_to_create_new_ledger_transaction(
    history,
    completer,
    payee_suggestor,
    default_account=None,
) -> LedgerTransaction:
    """
    Interactive prompt to create new Ledger transaction
    """
    n_accounts = 0
    while True:
        date = prompt('Date > ')
        if date:
            date = datestr_to_date(date)
            break
        return
    while True:
        payee = prompt('Payee > ', history=history, auto_suggest=payee_suggestor)
        if payee:
            break
    note = prompt('Note > ', history=history)
    ledger_tags = []
    while True:
        tagstr = prompt('Tag > ', history=history)
        if tagstr:
            try:
                tag_items = tagstr.split(':')
                tag_name = tag_items[0].strip()
                tag_value = tag_items[1].strip() if len(tag_items) > 1 else None
                ledger_tags.append(LedgerTag(name=tag_name, value=tag_value))
            except:
                print_formatted_text("Invalid tag")
        if not tagstr:
            break
    ledger_items = []
    while True:
        if default_account and len(ledger_items) == 0:
            account = default_account
            print_formatted_text(f'Account 1 > {account}')
        else:
            account = prompt(f'Account {len(ledger_items)+1} > ', history=history, completer=completer, complete_while_typing=True)
        if not account and len(ledger_items) >= 2:
            break
        if account.lower() == 'q':
            break
        if not account:
            print_formatted_text('Must have at least two accounts')
            continue
        amount = prompt(f'Account {len(ledger_items)+1} > $', history=history)
        amount = float(amount.replace(',','')) if amount else None
        ledger_item = LedgerTransactionPost(account=account, amount=amount)
        ledger_items.append(ledger_item)
        if amount is None:
            break
    ledger_transaction = LedgerTransaction(
        date=date,
        payee=payee,
        items=ledger_items,
        note=note,
        tags=ledger_tags,
    )
    return ledger_transaction


def prompt_to_create_ledger_transaction(
    t: BOATransaction,
    boa_account: str,
    history,
    completer,
    payee_suggestor,
    ) -> LedgerTransaction:
    # check to see if transaction already exists in Ledger file

    # create Ledger transaction from BOA transaction
    # display BOA transaction details for reference
    print_formatted_text(f'\nBoA tx. {t.date}  ${t.amount:9.2f},  {t.description}')
    # create default journal entry for Bank of America account
    ledger_item = LedgerTransactionItem(account=boa_account, amount=t.amount)
    ledger_items = [ledger_item]
    n_accounts = 1
    print_formatted_text(f'{ledger_item.account}  $ {ledger_item.amount:.2f}')
    payee = prompt('Payee > ', history=history, auto_suggest=payee_suggestor)
    if not payee:
        payee = t.description
    note = prompt('Note > ', history=history)
    while True:
        account = prompt(f'Account {n_accounts+1} > ', history=history, completer=completer, complete_while_typing=True)
        if not account and n_accounts >= 2:
            break
        if not account:
            print_formatted_text('Must have at least two accounts')
            continue
        amount = prompt(f'Account {n_accounts+1} > $', history=history)
        amount = float(amount.replace(',','')) if amount else None
        ledger_item = LedgerTransactionItem(account=account, amount=amount)
        ledger_items.append(ledger_item)
        n_accounts += 1
        if amount is None:
            break
    ledger_transaction = LedgerTransaction(
        date=t.date,
        payee=payee,
        items=ledger_items,
        note=note,
        tags=[LedgerTransactionTag(name='boa',value=t.description)]
    )
    return ledger_transaction