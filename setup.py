from setuptools import setup

setup(
    name='lm2ledger',
    version='0.1',
    py_modules=['lm2ledger'],
    python_requires='>=3.8',
    install_requires=[
        'Click',
        'aiohttp',
        'pydantic',
    ],
    entry_points={
        'console_scripts': [
            'lm2ledger=lm2ledger:cli',
        ]
    },
)