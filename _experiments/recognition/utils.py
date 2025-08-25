import os
import base64
from typing import List
from openai import OpenAI


def get_image_list(input_folder: str, ext: str = ".png") -> List[str]:
    """
    Возвращает список base64-строк изображений из папки.
    """
    image_list = []
    for filename in os.listdir(input_folder):
        if filename.lower().endswith(ext):
            img_path = os.path.join(input_folder, filename)
            with open(img_path, "rb") as img_file:
                img_data = img_file.read()
                encoded = base64.b64encode(img_data).decode("utf-8")
                image_list.append(encoded)
    return image_list


def get_openai_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY не найден в переменных окружения")
    return OpenAI(api_key=api_key)
