from .base import Institution, InvestmentKind


class VanguardInstitution(Institution):
    """
    Vanguard-specific transaction classification.

    Vanguard uses several non-standard patterns that the default classifier
    cannot handle:
      - 'cash/deposit' or 'cash/withdrawal' with names "Sweep out"/"Sweep in"
        represent money market fund sweeps, not external transfers.
      - 'fee/interest' is really a sweep out (money market -> cash), not a fee.
      - 'transfer/transfer' with "Sweep in"/"Sweep out" names are also sweeps
        (Vanguard started using this type at some point).
    """

    def classify(self, tx) -> InvestmentKind:
        type_val = tx.type.type.value
        subtype_val = tx.type.subtype.value if tx.type.subtype else ''

        if type_val == 'cash':
            if subtype_val == 'deposit' and tx.name == 'Sweep out':
                return InvestmentKind.SWEEP_OUT
            if subtype_val == 'withdrawal' and tx.name == 'Sweep in':
                return InvestmentKind.SWEEP_IN

        elif type_val == 'fee':
            if subtype_val == 'interest':
                # Vanguard records sweep-out (money market -> cash) as fee/interest
                return InvestmentKind.SWEEP_OUT

        elif type_val == 'transfer' and subtype_val == 'transfer':
            if tx.name == 'Sweep in':
                return InvestmentKind.SWEEP_IN
            elif tx.name == 'Sweep out':
                return InvestmentKind.SWEEP_OUT

        return super().classify(tx)
