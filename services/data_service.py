import torch
from models.place import Place

class DataService:

    def __init__(self, path):
        self.path = path

    def load(self):
        data = torch.load(self.path)

        nodes = data["nodes"]

        places = []
        for node in nodes:
            place = Place(node)
            places.append(place)

        return places