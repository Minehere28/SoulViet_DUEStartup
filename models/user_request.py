class UserRequest:
    def __init__(self, data):
        self.location = data.get("location")
        self.duration = int(data.get("duration", 1))
        self.budget = float(data.get("budget", 0))
        self.vibe = data.get("vibe")