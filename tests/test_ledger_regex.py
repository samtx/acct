from datetime import date

import pytest

from acct.ledger import Ledger, FirstLineTransactionGroup as fltg

@pytest.mark.parametrize(
    ('line', 'expected_result'),
    (
        (
            '2019/05/01 * Opening Balances\n',
            fltg(date(2019,5,1),'cleared','Opening Balances','')
        ),
        (
            '2019/07/10 * Initial Transfer           ; an extra comment\n',
            fltg(date(2019,7,10),'cleared','Initial Transfer','an extra comment')
        ),
        (
            '2019/07/10 Initial Transfer 	#an extra comment\n',
            fltg(date(2019,7,10),'','Initial Transfer','an extra comment')
        ),
        (
            '2019/07/09 ! Initial Transfer 	#an extra comment\n',
            fltg(date(2019,7,9),'pending','Initial Transfer','an extra comment')
        ),
    )
)
def test_first_line_transaction_group_regex(line, expected_result):
    """
    Test regular expression for first line of transaction group
    """
    ledger = Ledger('dummy.ledger')
    res = ledger._parse_first_line_of_transaction_group(line)
    assert res.date == expected_result.date
    assert res.status == expected_result.status
    assert res.payee == expected_result.payee
    assert res.note == expected_result.note