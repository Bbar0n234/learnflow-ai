from jinja2 import Template
import json
import argparse
from recognition.utils import get_image_list, get_openai_client

MODEL_NAME = "gpt-4.1-mini"

RECOGNITION_PROMPT_TEMPLATE = Template("""
You are an expert educational methodologist. Your goal is to process a set of handwritten student lecture notes provided as images.
                                       
Carefully analyze the content of these notes. Begin by reasoning step by step about what the notes represent: analyze the subject, main topics covered, and the structure of the material. Consider the context, underlying themes, and any implicit knowledge reflected in the notes.
While reasoning, if any protocol, concept, or term is partially illegible or unclear, use all available context, including formulas, descriptions, and relationships in the notes, to accurately infer its identity. Clearly explain your reasoning for each such case. 
                                       
After completing the reasoning and analysis of the notes, output the line `[END OF REASONING]` on a separate line.

Next, convert the handwritten content into a clear, structured, and informative digital format suitable for inclusion in a digital knowledge base. Present the extracted information in a logical and organized manner, making explicit the relationships between topics and subtopics.

If the notes contain any drawings, diagrams, or schemes, interpret them and describe their meaning and relevance in a way that makes their purpose and content unambiguous.
For any diagrams, drawings, or schemes, provide both a clear textual description and a schematic ASCII or pseudographic visualization that conveys their structure and content.                                   

Your output must include:
* Step by step reasoning about the notes.
* Identified subject and main topics.
* Structured summary of all material, with explicit sections and subsections as appropriate.
* Clear, descriptive reconstructions of all non-textual content, with explanations of what each drawing or diagram conveys.

Only include information that is present or directly inferable from the notes. Do not fabricate or introduce any additional content. Aim for maximum informativeness, clarity, and precision.
                                       
Your outputs should be always in Russian (with keeping abbreviations on the English), independent of the language of the notes.
""")

def pretty_print_pydantic(pydantic_model):
    """
    Возвращает красиво отформатированную JSON-схему Pydantic-модели.

    Args:
        pydantic_model: Pydantic-модель

    Returns:
        str: JSON-схема модели с отступами
    """
    return json.dumps(pydantic_model.model_json_schema(), indent=4, ensure_ascii=False)

def main(input_folder: str, output_file: str):
    """
    Основная функция для распознавания конспектов (свободный подход).
    """
    client = get_openai_client()
    image_list = get_image_list(input_folder)
    if not image_list:
        print(f"Нет изображений в папке {input_folder}")
        return
    messages = [
        {"role": "system", "content": RECOGNITION_PROMPT_TEMPLATE.render()},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Here is the set of handwritten student lecture notes for the information extracting:"},
                * [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_data}"}} for img_data in image_list]
            ],
        },
    ]
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        temperature=0.2,
    )
    with open(output_file, 'w') as f:
        f.write(response.choices[0].message.content)
    print(f"Результат сохранён в {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Распознавание конспектов (свободный подход)")
    parser.add_argument('--input', default='test/rotated', help='Папка с изображениями')
    parser.add_argument('--output', default='response.md', help='Файл для результата')
    args = parser.parse_args()
    main(args.input, args.output)