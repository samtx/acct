from sqlalchemy import (
    MetaData,
    Table,
    Column,
    String,
    Integer,
    Date,
    Text,
    Boolean,
    ForeignKey,
)
from sqlalchemy.types import (
    DECIMAL,
)

metadata = MetaData()


Journal = Table(
    'journal',
    metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(256), nullable=False),
    Column('note', Text),
)


AccountType = Table(
    'account_type',
    metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(256), nullable=False),
    Column('debit_as_negative', Boolean, nullable=False),
)
# class AccountType(str, enum.Enum):
#     EQUITY = 'EQUITY'
#     ASSET = 'ASSET'
#     INCOME = 'INCOME'
#     EXPENSE = 'EXPENSE'
#     LIABILITY = 'LIABILITY'


Account = Table(
    'account',
    metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(256), nullable=False),
    Column('account_type_id', Integer, ForeignKey('account_type.id'), nullable=False),
    Column('note', Text),
    Column('code', Integer, nullable=False),
    Column('parent_id', ForeignKey('account.id'), ondelete='CASCADE'),
    Column('journal_id', ForeignKey('journal.id'), ondelete='CASCADE', nullable=False),
    Column('lunchmoney_category_id', Integer, index=True),
    Column('lunchmoney_asset_id', Integer, index=True),
    Column('lunchmoney_plaid_account_id', Integer, index=True),
)


Transaction = Table(
    'transaction',
    metadata,
    Column('id', Integer, primary_key=True),
    Column('post_date', Date, nullable=False),
    Column('payee', String(256), nullable=False),
    Column('note', Text),
    Column('reconciled', Boolean, default=False, nullable=False),
    Column('journal_id', Integer, ForeignKey('journal.id'), ondelete='CASCADE'),
    Column('lunchmoney_id', Integer, index=True),
)


Entry = Table(
    'entry',
    metadata,
    Column('id', Integer, primary_key=True),
    Column('account_id', Integer, ForeignKey('account.id'), ondelete='CASCADE'),
    Column('transaction_id', Integer, ForeignKey('transaction.id'), nullable=False, ondelete='CASCADE'),
    Column('amount', DECIMAL(precision=2), nullable=False),
    Column('note', Text),
)


Tag = Table(
    'tag',
    metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(256), nullable=False),
    Column('note', Text),
    Column('journal_id', Integer, ForeignKey('journal.id'), nullable=False, ondelete='CASCADE'),
    Column('lunchmoney_id', Integer, index=True),
)


# Many to Many join tables
TagTransaction = Table(
    'tag_transaction',
    metadata,
    Column('tag_id', Integer, ForeignKey('tag.id'), nullable=False, ondelete='CASCADE', primary_key=True),
    Column('transaction_id', Integer, ForeignKey('transaction.id'), nullable=False, ondelete='CASCADE', primary_key=True, index=True),
)


TagEntry = Table(
    'tag_entry',
    metadata,
    Column('tag_id', Integer, ForeignKey('tag.id'), nullable=False, ondelete='CASCADE', primary_key=True),
    Column('entry_id', Integer, ForeignKey('entry.id'), nullable=False, ondelete='CASCADE', primary_key=True, index=True),
)
