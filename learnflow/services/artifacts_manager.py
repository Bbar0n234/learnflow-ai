"""
Local Artifacts Manager для LearnFlow AI.
"""

import os
import json
import uuid
import hashlib
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ArtifactsConfig(BaseModel):
    """Конфигурация для локального хранения артефактов"""

    base_path: str = "data/artifacts"
    ensure_permissions: bool = True
    atomic_writes: bool = True
    max_file_size: int = 10 * 1024 * 1024  # 10MB


class LocalArtifactsManager:
    """Класс для управления локальными артефактами."""

    def __init__(self, config: ArtifactsConfig):
        self.config = config
        self.base_path = Path(config.base_path)
        self._ensure_base_directory_exists()

    def _ensure_base_directory_exists(self):
        """Создает базовую директорию если она не существует"""
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
            if self.config.ensure_permissions:
                os.chmod(self.base_path, 0o755)
            logger.info(f"Artifacts base directory ensured: {self.base_path}")
        except Exception as e:
            logger.error(f"Failed to create base directory {self.base_path}: {e}")
            raise

    def _ensure_directory_exists(self, path: Path) -> None:
        """Создание директорий с proper permissions"""
        try:
            path.mkdir(parents=True, exist_ok=True)
            if self.config.ensure_permissions:
                os.chmod(path, 0o755)
            logger.debug(f"Directory ensured: {path}")
        except Exception as e:
            logger.error(f"Failed to create directory {path}: {e}")
            raise

    def _atomic_write_file(self, file_path: Path, content: str) -> None:
        """Атомарная запись файла (temp file + rename)"""
        try:
            # Create temporary file in the same directory
            temp_path = file_path.with_suffix(f".tmp.{uuid.uuid4().hex[:8]}")

            # Write content to temporary file
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(content)

            # Atomic rename
            temp_path.rename(file_path)

            # Set permissions if configured
            if self.config.ensure_permissions:
                os.chmod(file_path, 0o666)

            logger.debug(f"File written atomically: {file_path}")

        except Exception as e:
            # Cleanup temp file if it exists
            if temp_path.exists():
                temp_path.unlink()
            logger.error(f"Failed to write file {file_path}: {e}")
            raise

    def _generate_session_id(self) -> str:
        """Генерация уникального session ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        return f"session-{timestamp}"

    def _create_thread_metadata(
        self, thread_id: str, exam_question: str
    ) -> Dict[str, Any]:
        """Создание thread-level metadata.json"""
        now = datetime.now().isoformat()
        return {
            "thread_id": thread_id,
            "created": now,
            "last_activity": now,
            "sessions_count": 1,
            "exam_question": exam_question,
            "user_info": None,
        }

    def _create_session_metadata(
        self,
        session_id: str,
        thread_id: str,
        exam_question: str,
        display_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Создание session-level metadata.json"""
        now = datetime.now().isoformat()
        return {
            "session_id": session_id,
            "thread_id": thread_id,
            "exam_question": exam_question,
            "display_name": display_name,
            "created": now,
            "modified": now,
            "status": "active",
            "workflow_data": None,
            "files": [],
        }

    def _update_thread_metadata(
        self, thread_path: Path, updates: Dict[str, Any]
    ) -> None:
        """Обновление thread metadata"""
        metadata_file = thread_path / "metadata.json"

        # Load existing metadata
        metadata = {}
        if metadata_file.exists():
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load thread metadata, creating new: {e}")

        # Update metadata
        metadata.update(updates)
        metadata["last_activity"] = datetime.now().isoformat()

        # Save atomically
        self._atomic_write_file(
            metadata_file, json.dumps(metadata, indent=2, ensure_ascii=False)
        )

    def _update_session_metadata(
        self, session_path: Path, updates: Dict[str, Any]
    ) -> None:
        """Обновление session metadata"""
        metadata_file = session_path / "session_metadata.json"

        # Load existing metadata
        metadata = {}
        if metadata_file.exists():
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load session metadata, creating new: {e}")

        # Update metadata
        metadata.update(updates)
        metadata["modified"] = datetime.now().isoformat()

        # Save atomically
        self._atomic_write_file(
            metadata_file, json.dumps(metadata, indent=2, ensure_ascii=False)
        )

    def _create_learning_material_content(
        self,
        exam_question: str,
        generated_material: str,
        thread_id: str = "",
        session_id: str = "",
    ) -> str:
        """Создает содержимое markdown файла с обучающим материалом."""

        content = f"""# Обучающий материал

**Thread ID:** {thread_id}  
**Session ID:** {session_id}  
**Дата создания:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  

## Исходный экзаменационный вопрос

{exam_question}

## Сгенерированный материал

{generated_material}
"""

        return content

    def _create_questions_content(
        self, gap_questions: list, gap_q_n_a: list, thread_id: str = ""
    ) -> str:
        """Создает содержимое markdown файла с вопросами и ответами."""

        content = f"""# Дополнительные вопросы и ответы 

## Дополнительные вопросы

"""

        for i, question in enumerate(gap_questions, 1):
            content += f"{i}. {question}\n"

        content += "\n## Вопросы и ответы\n\n"

        for i, qa in enumerate(gap_q_n_a, 1):
            content += f"### {i}. Q&A\n\n{qa}\n\n---\n\n"

        return content

    async def push_learning_material(
        self,
        thread_id: str,
        exam_question: str,
        generated_material: str,
        display_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Создает session и сохраняет generated_material.md

        Args:
            thread_id: Идентификатор потока
            exam_question: Исходный экзаменационный вопрос
            generated_material: Сгенерированный обучающий материал

        Returns:
            Dict с информацией о созданном файле
        """
        try:
            # Generate session ID
            session_id = self._generate_session_id()

            # Create paths
            thread_path = self.base_path / thread_id
            session_path = thread_path / "sessions" / session_id

            # Ensure directories exist
            self._ensure_directory_exists(session_path)

            # Create thread metadata
            thread_metadata = self._create_thread_metadata(thread_id, exam_question)
            thread_metadata_file = thread_path / "metadata.json"
            self._atomic_write_file(
                thread_metadata_file,
                json.dumps(thread_metadata, indent=2, ensure_ascii=False),
            )

            # Create session metadata
            session_metadata = self._create_session_metadata(
                session_id, thread_id, exam_question, display_name
            )
            session_metadata_file = session_path / "session_metadata.json"
            self._atomic_write_file(
                session_metadata_file,
                json.dumps(session_metadata, indent=2, ensure_ascii=False),
            )

            # Write learning material file
            file_path = session_path / "generated_material.md"
            self._atomic_write_file(file_path, generated_material)

            # Update session metadata with new file
            self._update_session_metadata(
                session_path, {"files": ["generated_material.md"]}
            )

            logger.info(
                f"Successfully created learning material for thread {thread_id} session {session_id}"
            )

            relative_file_path = str(file_path.relative_to(self.base_path))
            relative_session_path = str(session_path.relative_to(self.base_path))
            relative_thread_path = str(thread_path.relative_to(self.base_path))

            return {
                "success": True,
                "file_path": relative_file_path,
                "folder_path": relative_session_path,  # Session folder for compatibility
                "session_id": session_id,
                "thread_path": relative_thread_path,
                "absolute_path": str(file_path),
            }

        except Exception as e:
            logger.error(
                f"Failed to push learning material for thread {thread_id}: {e}"
            )
            return {"success": False, "error": str(e)}

    async def push_recognized_notes(
        self,
        folder_path: str,
        recognized_notes: str,
        thread_id: str,
    ) -> Dict[str, Any]:
        """
        Сохраняет recognized_notes.md в существующую session

        Args:
            folder_path: Путь к session (из предыдущего вызова)
            recognized_notes: Распознанный текст
            thread_id: Для логирования

        Returns:
            success/error status + file paths
        """
        try:
            # Convert relative path back to absolute
            session_path = self.base_path / folder_path

            if not session_path.exists():
                raise ValueError(f"Session path does not exist: {session_path}")

            # Create recognized notes content
            # Write recognized notes file
            file_path = session_path / "recognized_notes.md"
            self._atomic_write_file(file_path, recognized_notes)

            # Update session metadata
            try:
                with open(
                    session_path / "session_metadata.json", "r", encoding="utf-8"
                ) as f:
                    metadata = json.load(f)
                    current_files = metadata.get("files", [])
                    if "recognized_notes.md" not in current_files:
                        current_files.append("recognized_notes.md")
                    self._update_session_metadata(
                        session_path, {"files": current_files}
                    )
            except Exception as e:
                logger.warning(f"Failed to update session metadata: {e}")

            logger.info(f"Successfully created recognized notes for thread {thread_id}")

            return {
                "success": True,
                "file_path": str(file_path.relative_to(self.base_path)),
                "absolute_path": str(file_path),
            }

        except Exception as e:
            logger.error(f"Failed to push recognized notes for thread {thread_id}: {e}")
            return {"success": False, "error": str(e)}

    async def push_synthesized_material(
        self,
        folder_path: str,
        synthesized_material: str,
        thread_id: str,
    ) -> Dict[str, Any]:
        """
        Сохраняет synthesized_material.md

        Args:
            folder_path: Путь к session
            synthesized_material: Синтезированный материал
            thread_id: Для логирования

        Returns:
            success/error status + file paths
        """
        try:
            # Convert relative path back to absolute
            session_path = self.base_path / folder_path

            if not session_path.exists():
                raise ValueError(f"Session path does not exist: {session_path}")

            # Write synthesized material file
            file_path = session_path / "synthesized_material.md"
            self._atomic_write_file(file_path, synthesized_material)

            # Update session metadata
            try:
                with open(
                    session_path / "session_metadata.json", "r", encoding="utf-8"
                ) as f:
                    metadata = json.load(f)
                    current_files = metadata.get("files", [])
                    if "synthesized_material.md" not in current_files:
                        current_files.append("synthesized_material.md")
                    self._update_session_metadata(
                        session_path, {"files": current_files}
                    )
            except Exception as e:
                logger.warning(f"Failed to update session metadata: {e}")

            logger.info(
                f"Successfully created synthesized material for thread {thread_id}"
            )

            return {
                "success": True,
                "file_path": str(file_path.relative_to(self.base_path)),
                "absolute_path": str(file_path),
            }

        except Exception as e:
            logger.error(
                f"Failed to push synthesized material for thread {thread_id}: {e}"
            )
            return {"success": False, "error": str(e)}

    async def push_questions_and_answers(
        self,
        folder_path: str,
        gap_questions: list,
        gap_q_n_a: list,
        thread_id: str,
    ) -> Dict[str, Any]:
        """
        Сохраняет gap_questions.md и отдельные answer файлы

        Args:
            folder_path: Путь к session
            gap_questions: Список gap questions
            gap_q_n_a: Список Q&A пар
            thread_id: Для логирования

        Returns:
            success/error status + файлы paths
        """
        try:
            # Convert relative path back to absolute
            session_path = self.base_path / folder_path

            if not session_path.exists():
                raise ValueError(f"Session path does not exist: {session_path}")

            created_files = []

            # Create gap questions content
            markdown_content = self._create_questions_content(
                gap_questions=gap_questions, gap_q_n_a=gap_q_n_a, thread_id=thread_id
            )

            # Write main questions file
            questions_file = session_path / "gap_questions.md"
            self._atomic_write_file(questions_file, markdown_content)
            created_files.append("gap_questions.md")

            # Create answers directory if there are individual answers
            if gap_q_n_a:
                answers_dir = session_path / "answers"
                self._ensure_directory_exists(answers_dir)

                for i, qa in enumerate(gap_q_n_a, 1):
                    answer_file = answers_dir / f"answer_{i:03d}.md"
                    answer_content = f"""# Ответ {i}

**Thread ID:** {thread_id}  
**Дата создания:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  

{qa}
"""
                    self._atomic_write_file(answer_file, answer_content)
                    created_files.append(f"answers/answer_{i:03d}.md")

            # Update session metadata
            try:
                with open(
                    session_path / "session_metadata.json", "r", encoding="utf-8"
                ) as f:
                    metadata = json.load(f)
                    current_files = metadata.get("files", [])
                    for file in created_files:
                        if file not in current_files:
                            current_files.append(file)
                    self._update_session_metadata(
                        session_path, {"files": current_files, "status": "completed"}
                    )
            except Exception as e:
                logger.warning(f"Failed to update session metadata: {e}")

            logger.info(
                f"Successfully created questions and answers for thread {thread_id}"
            )

            return {
                "success": True,
                "file_path": str(questions_file.relative_to(self.base_path)),
                "created_files": created_files,
                "absolute_path": str(questions_file),
            }

        except Exception as e:
            logger.error(
                f"Failed to push questions and answers for thread {thread_id}: {e}"
            )
            return {"success": False, "error": str(e)}

    async def push_complete_materials(
        self, thread_id: str, exam_question: str, all_materials: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Комплексное сохранение всех материалов

        Args:
            thread_id: Идентификатор потока
            exam_question: Экзаменационный вопрос
            all_materials: Словарь со всеми материалами

        Returns:
            Dict с информацией обо всех созданных файлах
        """
        try:
            results = {}

            # 1. Создаем базовую папку и сохраняем основной материал
            learning_result = await self.push_learning_material(
                thread_id=thread_id,
                exam_question=exam_question,
                generated_material=all_materials.get("generated_material", ""),
            )

            if not learning_result.get("success"):
                return {"success": False, "error": "Failed to create base session"}

            folder_path = learning_result["folder_path"]
            results["learning_material"] = learning_result

            # 2. Сохраняем распознанные конспекты если есть
            recognized_notes = all_materials.get("recognized_notes", "")
            if recognized_notes.strip():
                notes_result = await self.push_recognized_notes(
                    folder_path=folder_path,
                    recognized_notes=recognized_notes,
                    thread_id=thread_id,
                )
                results["recognized_notes"] = notes_result

            # 3. Сохраняем синтезированный материал если есть
            synthesized_material = all_materials.get("synthesized_material", "")
            if synthesized_material.strip():
                synthesis_result = await self.push_synthesized_material(
                    folder_path=folder_path,
                    synthesized_material=synthesized_material,
                    thread_id=thread_id,
                )
                results["synthesized_material"] = synthesis_result

            # 4. Сохраняем вопросы и ответы если есть
            gap_questions = all_materials.get("gap_questions", [])
            gap_q_n_a = all_materials.get("gap_q_n_a", [])
            if gap_questions or gap_q_n_a:
                questions_result = await self.push_questions_and_answers(
                    folder_path=folder_path,
                    gap_questions=gap_questions,
                    gap_q_n_a=gap_q_n_a,
                    thread_id=thread_id,
                )
                results["questions_and_answers"] = questions_result

            logger.info(
                f"Successfully pushed complete materials for thread {thread_id}"
            )

            return {
                "success": True,
                "folder_path": folder_path,
                "folder_url": str(
                    (self.base_path / folder_path).absolute()
                ),  # Local file path
                "results": results,
            }

        except Exception as e:
            logger.error(
                f"Failed to push complete materials for thread {thread_id}: {e}"
            )
            return {"success": False, "error": str(e)}
