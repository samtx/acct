from setuptools import setup

setup(
    name='lunchmoney',
    version='0.3',
    packages=['lunchmoney'],
    python_requires='>=3.8',
    install_requires=[
        'Click',
        'httpx[http2]',
    ],
    entry_points={
        'console_scripts': [
            'lm2ledger=lunchmoney.cli:lm2ledger',
            'lm=lunchmoney.cli:cli',
        ]
    },
)