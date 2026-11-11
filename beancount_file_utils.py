"""Utilities for reading and writing beancount files.

Kept separate from main.py so these helpers can be imported in tests
without pulling in the Plaid SDK.
"""
import logging
import os

logger = logging.getLogger(__name__)


def find_open_files(root_file: str, account: str = None, item_id: str = None):
    """Return the files (root or included) that hold matching Open directives.

    Matches by account name and/or plaid_item_id metadata. Falls back to the
    root file when nothing matches, so callers can still report a clear error.
    """
    from beancount import loader
    from beancount.core.data import Open

    entries, _, _ = loader.load_file(root_file)
    files = []
    for entry in entries:
        if not isinstance(entry, Open):
            continue
        if account is not None and entry.account != account:
            continue
        if item_id is not None and entry.meta.get("plaid_item_id") != item_id:
            continue
        filename = entry.meta.get("filename")
        if filename and os.path.exists(filename) and filename not in files:
            files.append(filename)
    return files or [root_file]


def store_institution_id_in_beancount(root_file: str, item_id: str, institution_id: str):
    for path in find_open_files(root_file, item_id=item_id):
        _store_institution_id_in_file(path, item_id, institution_id)


def _store_institution_id_in_file(root_file: str, item_id: str, institution_id: str):
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
