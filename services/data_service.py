import pandas as pd
from models.place import Place

class DataService:
    def __init__(self, path):
        self.path = path

    def load(self):
        df = pd.read_csv(self.path)
        return [Place(row) for _, row in df.iterrows()]