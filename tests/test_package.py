"""
Test that the package is correctly configured and all modules can be imported.

These tests ensure that the package installation works correctly and would catch
issues like missing modules in pyproject.toml.
"""
import subprocess
import sys


def test_import_main():
    """Test that main module can be imported."""
    try:
        import main
        assert hasattr(main, 'main')
    except ImportError as e:
        raise AssertionError(f"Failed to import main: {e}")


def test_import_beancount_renderer():
    """Test that beancount_renderer module can be imported."""
    try:
        from transactions import beancount_renderer
        assert hasattr(beancount_renderer, 'BeancountRenderer')
    except ImportError as e:
        raise AssertionError(f"Failed to import transactions.beancount_renderer: {e}")


def test_import_transaction_models():
    """Test that transaction_models module can be imported."""
    try:
        import transaction_models
        assert hasattr(transaction_models, 'PlaidTransaction')
        assert hasattr(transaction_models, 'PlaidInvestmentTransaction')
    except ImportError as e:
        raise AssertionError(f"Failed to import transaction_models: {e}")


def test_import_transactions_package():
    """Test that transactions package can be imported."""
    try:
        import transactions
        assert hasattr(transactions, 'beancount_renderer')
    except ImportError as e:
        raise AssertionError(f"Failed to import transactions package: {e}")


def test_import_plaid_models():
    """Test that plaid_models module can be imported."""
    try:
        import plaid_models
    except ImportError as e:
        raise AssertionError(f"Failed to import plaid_models: {e}")


def test_import_plaid_link_server():
    """Test that plaid_link_server module can be imported."""
    try:
        import plaid_link_server
    except ImportError as e:
        raise AssertionError(f"Failed to import plaid_link_server: {e}")


def test_cli_entry_point_exists():
    """Test that the CLI entry point is available."""
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'show', 'plaid2beancount'],
        capture_output=True,
        text=True
    )

    # If the package is installed, check that the entry point works
    if result.returncode == 0:
        # Try to run the help command
        help_result = subprocess.run(
            ['plaid2beancount', '--help'],
            capture_output=True,
            text=True
        )
        # We expect this to fail with missing arguments or succeed with help text
        # But it should NOT fail with ModuleNotFoundError
        assert 'ModuleNotFoundError' not in help_result.stderr, \
            f"CLI entry point has import errors: {help_result.stderr}"


def test_beancount_renderer_imports_from_main():
    """Test that BeancountRenderer can be imported from main context."""
    try:
        # This simulates what happens when main.py imports BeancountRenderer
        from transactions.beancount_renderer import BeancountRenderer
        from transaction_models import PlaidTransaction, PlaidInvestmentTransaction

        # Verify the renderer can be instantiated
        renderer = BeancountRenderer([], [])
        assert renderer is not None
    except ImportError as e:
        raise AssertionError(f"Failed to import dependencies needed by main: {e}")


def test_all_required_modules_in_same_import_context():
    """
    Test that all modules required by the application can be imported
    in the same context, simulating the actual runtime environment.
    """
    try:
        # Import in the order they're used in the application
        import main
        from transaction_models import PlaidTransaction, PlaidInvestmentTransaction
        from transactions.beancount_renderer import BeancountRenderer
        import plaid_link_server

        # Verify key functionality
        assert callable(main.main)
        assert callable(BeancountRenderer)

    except ImportError as e:
        raise AssertionError(
            f"Failed to import all required modules together: {e}\n"
            "This likely indicates a packaging issue where not all modules "
            "are listed in pyproject.toml's py-modules or packages."
        )
