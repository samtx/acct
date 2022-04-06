from pathlib import Path
import datetime
import shutil
from _pytest.monkeypatch import V

import pytest
from acct.ledger import (
    Ledger,
    LedgerTransaction,
    LedgerTag,
    LedgerTransactionPost
)


@pytest.fixture
def ledger_file(tmp_path):
    """
    Copy sample ledger file to pytest temporary directory
    """
    filename = 'sample.ledger'
    src_path = Path(__file__).parent / filename
    dest_path = tmp_path / filename
    shutil.copy(src_path, dest_path)
    return dest_path


@pytest.fixture
def ledger(ledger_file):
    """
    Get parsed ledger object from sample file
    """
    ledger = Ledger(ledger_file)
    ledger.parse()
    return ledger


def test_parse_ledger_file(ledger_file):
    ledger = Ledger(ledger_file)
    ledger.parse()
    assert len(ledger.transactions) == 5


def test_ledger_transaction_dates(ledger):
    assert datetime.date(2019, 8, 2) in ledger.dates
    assert datetime.date(2019, 5, 1) in ledger.dates
    assert datetime.date(2019, 7, 10) in ledger.dates
    assert datetime.date(2019, 10, 1) in ledger.dates
    assert datetime.date(2019, 10, 15) in ledger.dates


