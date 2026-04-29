"""Utilities for reading and writing beancount files.

Kept separate from main.py so these helpers can be imported in tests
without pulling in the Plaid SDK.
"""
import logging

logger = logging.getLogger(__name__)


def store_institution_id_in_beancount(root_file: str, item_id: str, institution_id: str):
    """Add plaid_institution_id metadata to every account with the given item_id.

    Inserts the metadata line immediately after each plaid_item_id line that
    matches item_id, unless plaid_institution_id is already present in that
    account block.
    """
    with open(root_file, 'r') as f:
        lines = f.readlines()

    new_lines = []
    i = 0
    while i < len(lines):
        new_lines.append(lines[i])

        if f'plaid_item_id: "{item_id}"' in lines[i]:
            # Look ahead to check whether institution_id is already in this account block
            j = i + 1
            already_stored = False
            while j < len(lines) and lines[j].startswith('  '):
                if 'plaid_institution_id:' in lines[j]:
                    already_stored = True
                    break
                j += 1

            if not already_stored:
                new_lines.append(f'  plaid_institution_id: "{institution_id}"\n')

        i += 1

    if len(new_lines) == len(lines):
        logger.warning(
            f"store_institution_id_in_beancount: no account with plaid_item_id "
            f'"{item_id}" found in {root_file} — institution_id not written'
        )
        return

    with open(root_file, 'w') as f:
        f.writelines(new_lines)

    logger.info(f"Stored institution_id {institution_id} for item {item_id} in {root_file}")
