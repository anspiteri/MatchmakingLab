from matchmakinglab.matchmakers.base_generator import RequestGenerator
from matchmakinglab.matchmakers.bradley_terry.generator import BradleyTerryGenerator


class Generator:
    def __init__(self, generator: RequestGenerator = BradleyTerryGenerator()):
        self._generator = generator
