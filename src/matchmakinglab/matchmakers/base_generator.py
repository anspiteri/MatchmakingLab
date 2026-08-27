from abc import ABC, abstractmethod


class RequestGenerator(ABC):
    @abstractmethod
    def start(self):
        pass
