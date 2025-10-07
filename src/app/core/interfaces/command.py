from abc import ABC, abstractmethod

class Command(ABC):
    """
    Interfaz de comandos
    """
    @abstractmethod
    def execute(self):
        pass