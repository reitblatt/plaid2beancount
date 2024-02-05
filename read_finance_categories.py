import csv
from models import FinanceCategory

def read_csv_file(file_path):
    finance_categories = []

    with open(file_path, 'r') as csv_file:
        csv_reader = csv.reader(csv_file)
        next(csv_reader)  # Skip the header row

        for row in csv_reader:
            print(row)
            primary, detailed, description = row                        
            FinanceCategory(primary=primary, detailed=detailed, description=description).save()    

if __name__ == '__main__':
    file_path = 'transactions-personal-finance-category-taxonomy.csv'
    read_csv_file(file_path)

    # Print out new categories
    for category in FinanceCategory.select():
        print(category)
