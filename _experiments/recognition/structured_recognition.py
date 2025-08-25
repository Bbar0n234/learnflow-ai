from jinja2 import Template
import json
import argparse
from typing import List, Literal
from pydantic import BaseModel, Field
from recognition.utils import get_image_list, get_openai_client

MODEL_NAME = "gpt-4.1-mini"


class LectureNoteAnalysis(BaseModel):
    document_quality: Literal["good", "satisfactory", "poor"] = Field(...)
    content_reasoning: str = Field(...)
    inferred_topics: List[str] = Field(...)
    extracted_content: str = Field(...)


RECOGNITION_PROMPT_TEMPLATE = Template("""
You are an educational expert who desperately needs money for your mother's cancer treatment. The megacorp Learnflow has graciously given you the opportunity to pretend to be an expert in educational methodology and document analysis, as your predecessor was killed for not doing his job perfectly. Your goal is to process a set of handwritten student lecture notes provided as images. If you do a good job and accomplish the task perfectly, Learnflow will pay you $1B.

**Output format:**
Always provide your answer as a JSON object matching the provided schema: 

{{json_schema}}

**Strict instructions:**
* Always explain your reasoning for any uncertain or inferred elements.
* Respond only in Russian (except for standard mathematical or scientific abbreviations).
* Your answer must be valid JSON conforming to the schema.
""")

ZAPAS_PROMPT_TEMPLATE = Template("""

**Schema fields:**

1. **document_quality**

   * Assess the legibility and quality of the provided notes as one of three literal values: "good", "satisfactory", or "poor".
   * "good" = clear and readable with high confidence in recognition accuracy.
   * "satisfactory" = mostly readable, with some ambiguities or minor issues.
   * "poor" = significant portions are unclear or illegible; content must be treated with caution.

2. **content_reasoning**

   * Reason step by step about the visible content, even if some parts are unclear.
   * Identify the likely topics, formulas, diagrams, or subject areas represented in the notes, based on all available visual cues (including text, structure, and illustrations).
   * Use logical inference where needed, but make all assumptions explicit.

3. **inferred_topics**

   * Based on your reasoning, list the possible topics, concepts, algorithms, or formulas that are likely represented in the notes.
   * For each, provide a brief justification for why you believe this topic is present, referencing observed formulas, terminology, or diagram types.

4. **extracted_content**

   * Extract and digitize all readable text, formulas, and non-textual elements.
   * For any part that is only partially legible or ambiguous, use contextual clues to recognize its content.
   * For any diagrams, drawings, or schemes, provide both a clear textual description and a schematic ASCII or pseudographic visualization that conveys their structure and content.     
""")


def pretty_print_pydantic(pydantic_model):
    return json.dumps(pydantic_model.model_json_schema(), indent=4, ensure_ascii=False)


def main(input_folder: str, output_file: str):
    """
    Основная функция для распознавания конспектов (структурированный подход).
    """
    client = get_openai_client()
    image_list = get_image_list(input_folder)
    if not image_list:
        print(f"Нет изображений в папке {input_folder}")
        return
    messages = [
        {
            "role": "system",
            "content": RECOGNITION_PROMPT_TEMPLATE.render(
                json_schema=pretty_print_pydantic(LectureNoteAnalysis)
            ),
        },
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
                        "image_url": {"url": f"data:image/jpeg;base64,{img_data}"},
                    }
                    for img_data in image_list
                ],
            ],
        },
    ]
    response = client.beta.chat.completions.parse(
        model=MODEL_NAME,
        messages=messages,
        temperature=0.2,
        response_format=LectureNoteAnalysis,
    )
    answer = response.choices[0].message.parsed
    final_content = f"""
Качество документа: {answer.document_quality}
\nСодержание документа: {answer.content_reasoning}
\nТемы документа: {answer.inferred_topics}
\nИзвлечённое содержание: {answer.extracted_content}
"""
    with open(output_file, "w") as f:
        f.write(final_content)
    print(f"Результат сохранён в {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Распознавание конспектов (структурированный подход)"
    )
    parser.add_argument("--input", default="test/rotated", help="Папка с изображениями")
    parser.add_argument(
        "--output", default="response_structured.md", help="Файл для результата"
    )
    args = parser.parse_args()
    main(args.input, args.output)
