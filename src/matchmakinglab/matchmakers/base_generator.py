from abc import ABC, abstractmethod


class RequestGenerator(ABC):
    @abstractmethod
    def generate_requests(self, number) -> list:
        pass
