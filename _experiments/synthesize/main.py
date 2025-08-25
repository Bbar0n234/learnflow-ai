from jinja2 import Template
import os
import yaml
import argparse
import sys
from pathlib import Path
from datetime import datetime

# Добавляем пути для импорта модулей проекта
sys.path.append(str(Path(__file__).parent.parent))

from openai import OpenAI
from recognition.utils import get_image_list, get_openai_client
from recognition.normal_recognition import RECOGNITION_PROMPT_TEMPLATE

model_name = "gpt-4.1-mini"

# Экзаменационный вопрос по умолчанию
default_exam_question = "Слепая подпись Чаума и ее использование в протоколе «Электронное голосование» Протокол «Игра в покер по переписке»( Ментальный покер)"

# Пути к конфигурационным файлам
prompts_config_path = "configs/prompts.yaml"


def load_prompts_config():
    """Загружает конфигурацию промптов"""
    with open(prompts_config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def recognize_lecture_notes(images_folder: str, client: OpenAI) -> str:
    """
    Распознает конспекты из изображений

    Args:
        images_folder: Папка с изображениями конспектов
        client: OpenAI клиент

    Returns:
        Распознанный текст конспектов
    """
    print(f"📸 Распознаю конспекты из папки: {images_folder}")

    image_list = get_image_list(images_folder, ext=".png")
    if not image_list:
        print(f"❌ Нет изображений в папке {images_folder}")
        return ""

    print(f"✅ Найдено {len(image_list)} изображений")

    messages = [
        {"role": "system", "content": RECOGNITION_PROMPT_TEMPLATE.render()},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Here is the set of handwritten student lecture notes for the information extracting:",
                },
                *[
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_data}"},
                    }
                    for img_data in image_list
                ],
            ],
        },
    ]

    print("🔄 Отправляю запрос на распознавание...")
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.2,
    )

    print("✅ Конспекты успешно распознаны")

    answer = response.choices[0].message.content
    if "[END OF REASONING]" in answer:
        print("Разбиваем на части")
        answer = answer.split("[END OF REASONING]")[1]

    return answer


def generate_additional_material(
    exam_question: str, client: OpenAI, prompts_config: dict
) -> str:
    """
    Генерирует дополнительный обучающий материал

    Args:
        exam_question: Экзаменационный вопрос
        client: OpenAI клиент
        prompts_config: Конфигурация промптов

    Returns:
        Сгенерированный дополнительный материал
    """
    print("📚 Генерирую дополнительный материал...")

    generating_content_prompt = prompts_config["generating_content_system_prompt"]

    # Подставляем экзаменационный вопрос в промпт
    template = Template(generating_content_prompt)
    prompt_content = template.render(exam_question=exam_question)

    messages = [{"role": "system", "content": prompt_content}]

    print("🔄 Отправляю запрос на генерацию материала...")
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.3,
    )

    print("✅ Дополнительный материал успешно сгенерирован")
    return response.choices[0].message.content


def synthesize_material(
    exam_question: str,
    lecture_notes: str,
    additional_material: str,
    client: OpenAI,
    prompts_config: dict,
) -> str:
    """
    Синтезирует финальный материал на основе конспектов и дополнительного материала

    Args:
        exam_question: Экзаменационный вопрос
        lecture_notes: Распознанные конспекты
        additional_material: Сгенерированный дополнительный материал
        client: OpenAI клиент
        prompts_config: Конфигурация промптов

    Returns:
        Синтезированный учебный материал
    """
    print("🔄 Синтезирую финальный материал...")

    synthesize_prompt = prompts_config["synthesize_system_prompt"]

    # Подставляем все данные в промпт для синтезирования
    template = Template(synthesize_prompt)
    prompt_content = template.render(
        exam_question=exam_question,
        lecture_notes=lecture_notes,
        additional_material=additional_material,
    )

    messages = [{"role": "system", "content": prompt_content}]

    print("🔄 Отправляю запрос на синтезирование...")
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.2,
    )

    print("✅ Материал успешно синтезирован")
    return response.choices[0].message.content


def save_markdown(filepath, content):
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def save_results(
    exam_question: str,
    lecture_notes: str,
    additional_material: str,
    synthesized_material: str,
    output_dir: str = "results",
):
    """
    Сохраняет каждый блок в отдельный .md файл в папку с датой (ГГГГ-ММ-ДД).
    """
    # Получаем текущую дату
    today = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    # Формируем итоговую директорию
    dated_dir = os.path.join(output_dir, today)
    os.makedirs(dated_dir, exist_ok=True)

    # Сохраняем экзаменационный вопрос
    save_markdown(
        os.path.join(dated_dir, "exam_question.md"),
        "# Экзаменационный вопрос\n\n" + exam_question.strip(),
    )
    # Сохраняем распознанные конспекты
    save_markdown(
        os.path.join(dated_dir, "lecture_notes.md"),
        "# Распознанные конспекты\n\n" + lecture_notes.strip(),
    )
    # Сохраняем дополнительный материал
    save_markdown(
        os.path.join(dated_dir, "additional_material.md"),
        "# Дополнительный сгенерированный материал\n\n" + additional_material.strip(),
    )
    # Сохраняем финальный синтез
    save_markdown(
        os.path.join(dated_dir, "synthesized_material.md"),
        "# Финальный синтезированный материал\n\n" + synthesized_material.strip(),
    )
    print(f"💾 Все результаты сохранены в папке: {dated_dir}")


def main():
    """Основная функция синтезирования материала"""
    parser = argparse.ArgumentParser(description="Синтезирование учебного материала")
    parser.add_argument(
        "--exam-question", default=default_exam_question, help="Экзаменационный вопрос"
    )
    parser.add_argument(
        "--images-folder",
        default="images/clipped",
        help="Папка с изображениями конспектов",
    )
    parser.add_argument(
        "--output",
        default="data/outputs/synthesized_material.md",
        help="Файл для сохранения результата",
    )
    parser.add_argument(
        "--skip-recognition",
        action="store_true",
        help="Пропустить этап распознавания конспектов",
    )
    parser.add_argument(
        "--skip-generation",
        action="store_true",
        help="Пропустить этап генерации дополнительного материала",
    )

    args = parser.parse_args()

    print("🚀 Запускаю процесс синтезирования материала")
    print(f"📝 Экзаменационный вопрос: {args.exam_question}")

    # Загружаем конфигурацию промптов
    prompts_config = load_prompts_config()

    # Инициализируем OpenAI клиент
    client = get_openai_client()

    # Этап 1: Распознавание конспектов
    lecture_notes = ""
    if not args.skip_recognition:
        lecture_notes = recognize_lecture_notes(args.images_folder, client)
    else:
        print("⏭️  Пропускаю этап распознавания конспектов")
        lecture_notes = "Конспекты не распознавались (пропущено по запросу)"

    # Этап 2: Генерация дополнительного материала
    additional_material = ""
    if not args.skip_generation:
        additional_material = generate_additional_material(
            args.exam_question, client, prompts_config
        )
    else:
        print("⏭️  Пропускаю этап генерации дополнительного материала")
        additional_material = (
            "Дополнительный материал не генерировался (пропущено по запросу)"
        )

    # Этап 3: Синтезирование материала
    synthesized_material = synthesize_material(
        args.exam_question, lecture_notes, additional_material, client, prompts_config
    )

    # Сохранение результатов
    save_results(
        args.exam_question,
        lecture_notes,
        additional_material,
        synthesized_material,
        args.output,
    )

    print("🎉 Процесс синтезирования завершен успешно!")


if __name__ == "__main__":
    main()
