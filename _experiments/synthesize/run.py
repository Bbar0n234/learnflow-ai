"""
Простой запуск синтезирования материала без командной строки
Просто запустите: python synthesize/run.py
"""

import os
import sys
from pathlib import Path

# Добавляем пути для импорта модулей проекта
sys.path.append(str(Path(__file__).parent.parent))

from main import (
    load_prompts_config,
    recognize_lecture_notes,
    generate_additional_material,
    synthesize_material,
    save_results,
)
from recognition.utils import get_openai_client

# ================== НАСТРОЙКИ ==================
# Измените эти параметры под ваши нужды

input_content = "Слепая подпись Чаума и ее использование в протоколе «Электронное голосование» Протокол «Игра в покер по переписке»( Ментальный покер)"

IMAGES_FOLDER = "images/clipped"  # Папка с изображениями конспектов

OUTPUT_DIR = "data/outputs/"  # Папка для результата

# Настройки этапов (True = выполнить, False = пропустить)
DO_RECOGNITION = True  # Распознавать конспекты из изображений
DO_GENERATION = True  # Генерировать дополнительный материал
DO_SYNTHESIS = True  # Синтезировать финальный материал

# ===============================================


def main():
    """Основная функция запуска"""
    print("=" * 60)
    print("🚀 СИНТЕЗИРОВАНИЕ УЧЕБНОГО МАТЕРИАЛА")
    print("=" * 60)
    print()

    print("📝 Экзаменационный вопрос:")
    print(f"   {input_content}")
    print()

    print(f"📁 Папка с изображениями: {IMAGES_FOLDER}")
    print(f"💾 Выходной файл: {OUTPUT_DIR}")
    print()

    print("🔄 Этапы выполнения:")
    print(f"   📸 Распознавание конспектов: {'✅ ДА' if DO_RECOGNITION else '❌ НЕТ'}")
    print(f"   📚 Генерация материала: {'✅ ДА' if DO_GENERATION else '❌ НЕТ'}")
    print(f"   🔄 Синтезирование: {'✅ ДА' if DO_SYNTHESIS else '❌ НЕТ'}")
    print()

    # Проверяем .env файл
    if not os.path.exists(".env"):
        print("❌ ОШИБКА: Файл .env не найден!")
        print("   Создайте файл .env на основе env.example и добавьте OPENAI_API_KEY")
        return

    try:
        # Загружаем конфигурацию промптов
        print("📋 Загружаю конфигурацию промптов...")
        prompts_config = load_prompts_config()

        # Инициализируем OpenAI клиент
        print("🔑 Инициализирую OpenAI клиент...")
        client = get_openai_client()

        # Переменные для результатов
        lecture_notes = ""
        additional_material = ""
        synthesized_material = ""

        # Этап 1: Распознавание конспектов
        if DO_RECOGNITION:
            print("\n" + "=" * 40)
            print("📸 ЭТАП 1: РАСПОЗНАВАНИЕ КОНСПЕКТОВ")
            print("=" * 40)
            lecture_notes = recognize_lecture_notes(IMAGES_FOLDER, client)
            if not lecture_notes:
                print("⚠️  Конспекты не были распознаны, продолжаю без них...")
                lecture_notes = (
                    "Конспекты не были распознаны или отсутствуют изображения"
                )
        else:
            print("\n⏭️  Пропускаю этап распознавания конспектов")
            lecture_notes = "Этап распознавания пропущен"

        # Этап 2: Генерация дополнительного материала
        if DO_GENERATION:
            print("\n" + "=" * 40)
            print("📚 ЭТАП 2: ГЕНЕРАЦИЯ ДОПОЛНИТЕЛЬНОГО МАТЕРИАЛА")
            print("=" * 40)
            additional_material = generate_additional_material(
                input_content, client, prompts_config
            )
        else:
            print("\n⏭️  Пропускаю этап генерации дополнительного материала")
            additional_material = "Этап генерации дополнительного материала пропущен"

        # Этап 3: Синтезирование материала
        if DO_SYNTHESIS:
            print("\n" + "=" * 40)
            print("🔄 ЭТАП 3: СИНТЕЗИРОВАНИЕ МАТЕРИАЛА")
            print("=" * 40)
            synthesized_material = synthesize_material(
                input_content,
                lecture_notes,
                additional_material,
                client,
                prompts_config,
            )
        else:
            print("\n⏭️  Пропускаю этап синтезирования")
            synthesized_material = "Этап синтезирования пропущен"

        # Сохранение результатов
        print("\n" + "=" * 40)
        print("💾 СОХРАНЕНИЕ РЕЗУЛЬТАТОВ")
        print("=" * 40)

        # Создаем директорию если не существует
        os.makedirs(os.path.dirname(OUTPUT_DIR), exist_ok=True)

        save_results(
            input_content,
            lecture_notes,
            additional_material,
            synthesized_material,
            OUTPUT_DIR,
        )

        print("\n" + "=" * 60)
        print("🎉 ПРОЦЕСС УСПЕШНО ЗАВЕРШЕН!")
        print("=" * 60)
        print(f"📁 Результаты сохранены в: {OUTPUT_DIR}")
        print()

    except Exception as e:
        print(f"\n❌ ОШИБКА: {str(e)}")
        print("Проверьте настройки и повторите попытку")
        return


if __name__ == "__main__":
    main()
