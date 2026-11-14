"""Every task's scripted oracle, keyed by task id."""

from shopgym.agents.oracle import Oracle
from shopgym.agents.oracles_account import ACCOUNT_ORACLES
from shopgym.agents.oracles_shop import SHOP_ORACLES

ALL_ORACLES: dict[str, Oracle] = {**SHOP_ORACLES, **ACCOUNT_ORACLES}
