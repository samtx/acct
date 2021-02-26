from setuptools import setup

setup(
    name='lm2ledger',
    version='0.2',
    py_modules=['lm2ledger'],
    python_requires='>=3.8',
    install_requires=[
        'Click',
        'httpx[http2]',
    ],
    entry_points={
        'console_scripts': [
            'lm2ledger=lm2ledger.cli:cli',
        ]
    },
)