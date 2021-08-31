from setuptools import setup

setup(
    name="acct",
    version="0.1",
    packages=["acct"],
    python_requires=">=3.8",
    install_requires=[
        "Click",
        "httpx[http2]",
        "pydantic",
    ],
    entry_points={
        "console_scripts": [
            "acct=acct.cli:cli",
            "boa2ledger=acct.cli:boa2ledger",
        ]
    },
)
