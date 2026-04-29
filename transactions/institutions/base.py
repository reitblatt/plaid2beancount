from enum import Enum


class InvestmentKind(Enum):
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    SWEEP_IN = "sweep_in"       # cash -> money market fund
    SWEEP_OUT = "sweep_out"     # money market fund -> cash
    TRANSFER_IN = "transfer_in"   # external cash arriving (includes contributions)
    TRANSFER_OUT = "transfer_out"  # cash leaving to external
    FEE = "fee"                 # miscellaneous fee treated as buy


class Institution:
    """Default institution: classifies investment transactions by Plaid type/subtype only."""

    def classify(self, tx) -> InvestmentKind:
        type_val = tx.type.type.value
        subtype_val = tx.type.subtype.value if tx.type.subtype else ''

        if type_val == 'buy':
            return InvestmentKind.BUY
        elif type_val == 'sell':
            return InvestmentKind.SELL
        elif type_val == 'fee':
            if subtype_val == 'dividend':
                return InvestmentKind.DIVIDEND
            elif subtype_val == 'miscellaneous fee':
                return InvestmentKind.FEE
        elif type_val == 'cash':
            if subtype_val == 'dividend':
                return InvestmentKind.DIVIDEND
            elif subtype_val in ('deposit', 'contribution'):
                return InvestmentKind.TRANSFER_IN
            elif subtype_val == 'withdrawal':
                return InvestmentKind.TRANSFER_OUT
        elif type_val == 'transfer':
            if subtype_val == 'transfer':
                if tx.amount > 0:
                    return InvestmentKind.TRANSFER_OUT
                else:
                    return InvestmentKind.TRANSFER_IN

        raise ValueError(f"Unknown transaction type: {tx.type.type} - {tx.type.subtype}")
