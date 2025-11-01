from django.core.management.base import BaseCommand

class AccountsCommand(BaseCommand):    

    def add_arguments(self, parser):        
        
        parser.add_argument(
        "--to-date",
        metavar="STR",
        help=(
            "specify the ending date for transactions to be pulled; "
            "use in conjunction with --from-date to specify range"
            "Date format: YYYY-MM-DD"
        ),
        )

        parser.add_argument(
            "--from-date",
            metavar="STR",
            help=(
                "specify a the starting date for transactions to be pulled; "
                "use in conjunction with --to-date to specify range"
                "Date format: YYYY-MM-DD"
            ),
        )
        
        parser.add_argument(
        "--root-file",
        metavar="STR",
        help=("specify the path to the root file for beancount"),
        )

        # Add argument for list of account names

        parser.add_argument(
            "--accounts",
            metavar="STR",
            type=lambda s: [item for item in s.split(",")],
            help="comma separated list of account names to sync transactions for",
        )