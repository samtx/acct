from setuptools import setup

setup(
    name='lm2ledger',
    version='0.1',
    py_modules=['lm2ledger'],
    install_requires=[
        'Click',
        'aiohttp',
        'pydantic',
    ],
    entry_points="""
        [console_scripts]
        lm2ledger=lm2ledger:cli
    """,
)