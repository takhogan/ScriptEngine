from abc import ABC, abstractmethod


class DeviceManager(ABC):

    @abstractmethod
    def screenshot(self):
        raise NotImplementedError(f"screenshot not implemented for {self.__class__.__name__}")

    @abstractmethod
    def keyDown(self):
        raise NotImplementedError(f"key_down not implemented for {self.__class__.__name__}")

    @abstractmethod
    def keyUp(self):
        raise NotImplementedError(f"key_up not implemented for {self.__class__.__name__}")

    @abstractmethod
    def keyPress(self):
        raise NotImplementedError(f"key press not implemented for {self.__class__.__name__}")

    @abstractmethod
    def hotkey(self):
        raise NotImplementedError(f"hotkey not implemented for {self.__class__.__name__}")

    @abstractmethod
    def mouse_down(self):
        raise NotImplementedError(f"mouse_down not implemented for {self.__class__.__name__}")

    @abstractmethod
    def mouse_up(self):
        raise NotImplementedError(f"mouse_up not implemented for {self.__class__.__name__}")

    @abstractmethod
    def smooth_move(self):
        raise NotImplementedError(f"mouse_move not implemented for {self.__class__.__name__}")

    @abstractmethod
    def click(self):
        raise NotImplementedError(f"click not implemented for {self.__class__.__name__}")
    
    @abstractmethod
    def click_and_drag(self):
        raise NotImplementedError(f"click_and_drag not implemented for {self.__class__.__name__}")

    @abstractmethod
    def scroll(self):
        raise NotImplementedError(f"scroll not implemented for {self.__class__.__name__}")
    
    @abstractmethod
    def start_device(self):
        raise NotImplementedError(f"start_device not implemented for {self.__class__.__name__}")

    @abstractmethod
    def stop_device(self):
        raise NotImplementedError(f"stop_device not implemented for {self.__class__.__name__}")
