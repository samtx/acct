from datetime import date

import pytest

from acct.ledger import (
    Ledger,
    LedgerStatus,
    FirstLineTransactionGroup as fltg,
    LedgerLexer,
    LedgerNote,
)

@pytest.mark.parametrize(
    ('line', 'expected_result'),
    (
        (
            '2019/05/01 * Opening Balances\n',
            fltg(date(2019,5,1), LedgerStatus.CLEARED,'Opening Balances', None)
        ),
        (
            '2019/07/10 * Initial Transfer           ; an extra comment\n',
            fltg(date(2019,7,10), LedgerStatus.CLEARED,'Initial Transfer', LedgerNote('an extra comment', newline=False))
        ),
        (
            '2019/07/10 Initial Transfer 	#an extra comment\n',
            fltg(date(2019,7,10), LedgerStatus.UNKNOWN,'Initial Transfer', LedgerNote('an extra comment', newline=False))
        ),
        (
            '2019/07/09 ! Initial Transfer 	#an extra comment\n',
            fltg(date(2019,7,9), LedgerStatus.PENDING,'Initial Transfer', LedgerNote('an extra comment', newline=False))
        ),
    )
)
def test_first_line_transaction_group_regex(line, expected_result):
    """
    Test regular expression for first line of transaction group
    """
    lexer = LedgerLexer('dummy.ledger')
    res = lexer.parse_first_line_of_transaction(line)
    assert res.date == expected_result.date
    assert res.status == expected_result.status
    assert res.payee == expected_result.payee
    if expected_result.note is None:
        assert res.note is None
    else:
        assert res.note.value == expected_result.note.value
        assert res.note.newline == expected_result.note.newline