from abc import ABC, abstractmethod


class FeatureGenerator(ABC):
    @abstractmethod
    def generate(self):
        pass
