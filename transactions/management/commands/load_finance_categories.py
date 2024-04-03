import csv
from django.core.management.base import BaseCommand
from transactions.models import FinanceCategory

class Command(BaseCommand):
    help = 'Load finance categories from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str)

    def handle(self, *args, **options):
        with open(options['csv_file'], 'r') as f:
            reader = csv.reader(f)
            next(reader)  # Skip the header row
            for row in reader:
                _, created = FinanceCategory.objects.get_or_create(
                    primary=row[0],
                    detailed=row[1],
                    description=row[2],
                    expense_account=None
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f'Created finance category {row[1]}'))