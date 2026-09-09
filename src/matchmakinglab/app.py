from matchmakinglab.core.state import PlatformState


class App:
    def __init__(self, platform, generator) -> None:
        self.platform = platform
        self.generator = generator
        self.state = PlatformState()

        print("Platform ready.")

    def run(self):
        # Application Loop
        pass
