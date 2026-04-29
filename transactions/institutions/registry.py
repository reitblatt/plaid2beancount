from typing import Optional
from .base import Institution
from .vanguard import VanguardInstitution

# Maps Plaid institution_id -> Institution subclass.
# Add a new entry here when an institution needs custom classification logic.
INSTITUTION_REGISTRY: dict = {
    "ins_116527": VanguardInstitution,  # Vanguard
}


def get_institution(institution_id: Optional[str]) -> Institution:
    """Return the Institution instance for the given Plaid institution_id.

    Falls back to the base Institution (generic Plaid type/subtype logic)
    for unknown or missing institution IDs.
    """
    cls = INSTITUTION_REGISTRY.get(institution_id, Institution)
    return cls()
