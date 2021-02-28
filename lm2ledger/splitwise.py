# Add splitwise transactions to lunchmoney
from dataclasses import dataclass
import datetime
from typing import List

import httpx


@dataclass
class SplitwiseGroup:
    pass


@dataclass
class SplitwiseFriendship:
    pass


@dataclass
class SplitwiseExpenseBundle:
    pass


@dataclass
class SplitwiseCategory:
    pass


@dataclass
class SplitwiseUser:
    id: int
    first_name: str
    last_name: str

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'


@dataclass
class SplitwiseRepayment:
    from: SplitwiseUser
    to: SplitwiseUser
    amount: float


@dataclass
class SplitwiseUserShare:
    user: SplitwiseUser
    paid_share: float
    owed_share: float
    net_balance: float


@dataclass
class SplitwiseExpense:
    id: int
    cost: float
    group: SplitwiseGroup
    friendship: SplitwiseFriendship
    category: SplitwiseCategory
    details: str
    date: datetime.date
    payment: bool
    comments: str
    users: List[SplitwiseUserShare]
    repayments: List[SplitwiseRepayment]
    deleted_at: datetime.datetime = None


class Splitwise:

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://secure.splitwise.com/api/v3.0/"
        self.headers = {'Authorization': f'Bearer {self.api_key}'}
        self.groups = {}
        self.expenses = {}
        self.categories = {}
        # self.friendships = {}
        self.expense_bundles = {}
        self.users = {}
        self.repayments = {}
        self.user_shares = {}

    def fetch_data(self, params):
        # get user from id
        # /get_user/{id}
        tasks = [
            self.fetch_resource('categories'),
            self.fetch_resource('groups'),
            self.fetch_resource('expenses', params),
        ]
        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(asyncio.gather(*tasks))
        return results

    async def fetch_resource(self, resource: str, params: dict = None):
        """
        async get request for transaction data
        """
        if params is None:
            params = {}
        async with httpx.AsyncClient(http2=True, base_url=self.base_url, headers=self.headers) as client:
            data = await client.get(f'get_{resource}', params=params)
            return data.json()[resource]


