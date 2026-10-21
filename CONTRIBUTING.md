# Development and testing

This is a **paper-trading research system**. Live order submission is disabled.

Run the tests from the repository root:

```bash
python -m unittest discover -s tests -v
PYTHONPATH=legacy/v5 python -m unittest discover -s legacy/v5/tests -v
```

Only commit source code, synthetic fixtures, and documentation. Keep credentials, actual exchange captures, broker account information, private IDs, local database files, and unsynchronized sportsbook data out of Git. Do not flip the live-order guard without independent review of execution, settlement, fees, legal eligibility, and risk controls.
