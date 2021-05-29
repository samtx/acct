# Add splitwise transactions to lunchmoney
import datetime
from typing import List, Dict, Union
import asyncio
from pydantic import BaseModel, Field, validator

import httpx

from lunchmoney.utils import isodatestr_to_date, none_to_empty_string

class SplitwiseGroup(BaseModel):
    pass


class SplitwiseFriendship(BaseModel):
    pass


class SplitwiseExpenseBundle(BaseModel):
    pass


class SplitwiseCategory(BaseModel):
    id: int
    name: str
    parent_id: int = None


class SplitwiseUser(BaseModel):
    id: int
    first_name: str
    last_name: str

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'


class SplitwiseRepayment(BaseModel):
    to: int  # user id
    amount: float
    from_: int = Field(..., alias='from')


class SplitwiseUserShare(BaseModel):
    user: SplitwiseUser
    paid_share: float
    owed_share: float
    net_balance: float


class SplitwiseExpense(BaseModel):
    id: int
    cost: float
    category: SplitwiseCategory
    date: datetime.date
    payment: bool
    details: str = ''
    users: List[SplitwiseUserShare] = None
    # repayments: List[SplitwiseRepayment] = None
    deleted_at: datetime.datetime = None

    _validate_details = validator('details', allow_reuse=True)(none_to_empty_string)

    # @validator('details')
    # def none_to_empty_string(cls, value):
    #     value = '' if not value else value
    #     return str(value)




class Splitwise:
    def __init__(self, api_key: str):
        if not api_key:
            raise Exception('Splitwise API Key required')
        self.api_key = api_key
        self.base_url = "https://secure.splitwise.com/api/v3.0/"
        self.headers = {'Authorization': f'Bearer {self.api_key}'}
        self.current_user_id = None
        self.expenses = {}
        self.categories = {}
        self.users = {}
        self.repayments = {}

    def fetch_splitwise_data(self, params):
        tasks = [
            self.fetch_current_user_id(),
            self.fetch_resource('categories'),
            self.fetch_resource('expenses', params),
        ]
        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(asyncio.gather(*tasks))
        return results

    async def fetch_current_user_id(self):
        """
        async get request for current Splitwise user id
        """
        async with httpx.AsyncClient(http2=True, base_url=self.base_url, headers=self.headers) as client:
            data = await client.get(f'get_current_user')
            return data.json()['user']['id']

    async def fetch_resource(self, resource: str, params: dict = None):
        """
        async get request for transaction data
        """
        if params is None:
            params = {}
        async with httpx.AsyncClient(http2=True, base_url=self.base_url, headers=self.headers) as client:
            data = await client.get(f'get_{resource}', params=params)
            return data.json()[resource]

    # def json_to_model(self, model, data_list):
    #     data = [model(**x) for x in data_list]
    #     new_dict = {d.id: d for d in data}
    #     return new_dict

    def get_expenses(self, params):
        results = self.fetch_splitwise_data(params)
        self.current_user_id = int(results[0])
        self.categories = self.categories_serializer(results[1])
        self.expenses = self.expenses_serializer(results[2])

    def categories_serializer(self, category_data):
        """
        Take category data from splitwise api and convert it to local objects
        """
        categories = {}
        for parent_category in category_data:
            parent_id, name = int(parent_category['id']), parent_category['name']
            categories[parent_id] = SplitwiseCategory(id=parent_id, name=name)
            for subcategory in parent_category['subcategories']:
                sub_id, name = int(subcategory['id']), subcategory['name']
                categories[sub_id] = SplitwiseCategory(id=sub_id, name=name, parent_id=parent_id)
        return categories

    def expenses_serializer(self, expenses):
        return [self.expense_serializer(expense) for expense in expenses]

    def expense_serializer(self, expense):
        """
        Extract subset of data from splitwise api and convert it to local object
        """
        data_keys = ['id', 'cost', 'category', 'date', 'payment', 'details', 'users', 'deleted_at']
        expense['date'] = isodatestr_to_date(expense['date'])
        # replace some values with empty strings if not set
        for user in (u['user'] for u in expense['users']):
            for key in ['first_name', 'last_name']:
                user[key] = none_to_empty_string(user[key])
        expense['details'] = none_to_empty_string(expense['details'])
        expense_subset = {key: value for key, value in expense.items() if key in data_keys}
        serialized_expense = SplitwiseExpense(**expense_subset)
        return serialized_expense


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
    e = splitwise.expenses
    from pprint import pprint
    pprint(splitwise.expenses)

