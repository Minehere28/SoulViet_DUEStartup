class UserRequest:
    def __init__(self, data):
        self.location = data.get("location")
        self.duration = int(data.get("duration", 1))
        self.vibe = data.get("vibe")
