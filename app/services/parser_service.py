from app.services.hotline_parser import HotlineParser
from app.services.comfy_parser import ComfyParser
from app.services.brain_parser import BrainParser

class ParserFactory:
    @staticmethod
    def get_parser(url: str):
        if "hotline.ua" in url:
            return HotlineParser()
        elif "comfy.ua" in url:
            return ComfyParser()
        elif "brain.com.ua" in url:
            return BrainParser()
        else:
            raise ValueError("Unsupported source URL")
