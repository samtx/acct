# Add splitwise transactions to lunchmoney
from dataclasses import dataclass
import datetime
from typing import List
import asyncio

import httpx

def isodatestr_to_date(isodatestr):
    dt = datetime.datetime.fromisoformat(isodatestr)
    date = datetime.date(dt.year, dt.month, dt.day)
    return date

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
    id: int
    name: str
    parent_id: int = None


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
    from_: SplitwiseUser
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
            # self.fetch_resource('groups'),
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

    def get_expenses(self, params):
        results = self.fetch_data(params)
        self.parse_categories(results[0])
        # self.groups = self.json_to_dataclass(SplitwiseGroup, results[0])
        self.parse_expenses(results[1])
        for expense in self.expenses:
            expense_id = expense.id
            print(f'id={expense_id}, amount={expense.amount}')
            a = 1

    def parse_categories(self, category_data):
        """
        Take category data from splitwise api and convert it to local objects
        """
        for parent_category in category_data:
            parent_id, name = int(parent_category['id']), parent_category['name']
            self.categories[parent_id] = SplitwiseCategory(id=parent_id, name=name)
            for subcategory in parent_category['subcategories']:
                sub_id, name = int(subcategory['id']), subcategory['name']
                self.categories[sub_id] = SplitwiseCategory(id=sub_id, name=name, parent_id=parent_id)

    def parse_expenses(self, expenses):
        """
        Take expense data from splitwise api and convert it to local object
        """
        data_to_store = ['id', 'cost', 'details', 'payment']
        for expense in expenses:
            data = {
                'id' : int(expense['id']),
                'cost': float(expense['cost']),
                'details': expense['details'],
                'payment': bool(expense[]),
                'date': isodatestr_to_date(expense['date']),
                'description': expense['description'] if expense['description'] else '',

            }






if __name__ == "__main__":
    import os
    api_key = os.getenv('SPLITWISE_API_KEY')
    if not api_key:
        raise Exception('splitwise api key not set')
    splitwise = Splitwise(api_key)
    start_date = datetime.date.today() - datetime.timedelta(days=60)
    end_date = datetime.date.today()
    params = {
        'dated_after': start_date.isoformat(),
        # 'dated_before'
        'limit': 30,
    }
    splitwise.get_expenses(params)

