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
        self, thread_id: str, input_content: str
    ) -> Dict[str, Any]:
        """Создание thread-level metadata.json"""
        now = datetime.now().isoformat()
        return {
            "thread_id": thread_id,
            "created": now,
            "last_activity": now,
            "sessions_count": 1,
            "input_content": input_content,
            "user_info": None,
        }

    def _create_session_metadata(
        self,
        session_id: str,
        thread_id: str,
        input_content: str,
        display_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Создание session-level metadata.json"""
        now = datetime.now().isoformat()
        return {
            "session_id": session_id,
            "thread_id": thread_id,
            "input_content": input_content,
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
        input_content: str,
        generated_material: str,
        thread_id: str = "",
        session_id: str = "",
    ) -> str:
        """Создает содержимое markdown файла с обучающим материалом."""

        content = f"""# Обучающий материал

## Исходный экзаменационный вопрос

{input_content}

## Сгенерированный материал

{generated_material}
"""

        return content

    def _create_questions_content(
        self, questions: list, questions_and_answers: list, thread_id: str = ""
    ) -> str:
        """Создает содержимое markdown файла с вопросами и ответами."""

        content = f"""# Дополнительные вопросы и ответы 

## Дополнительные вопросы

"""

        for i, question in enumerate(questions, 1):
            content += f"{i}. {question}\n"

        content += "\n## Вопросы и ответы\n\n"

        for i, qa in enumerate(questions_and_answers, 1):
            content += f"### {i}. Q&A\n\n{qa}\n\n---\n\n"

        return content

    async def push_learning_material(
        self,
        thread_id: str,
        input_content: str,
        generated_material: str,
        display_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Создает session и сохраняет generated_material.md

        Args:
            thread_id: Идентификатор потока
            input_content: Исходный экзаменационный вопрос
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
            thread_metadata = self._create_thread_metadata(thread_id, input_content)
            thread_metadata_file = thread_path / "metadata.json"
            self._atomic_write_file(
                thread_metadata_file,
                json.dumps(thread_metadata, indent=2, ensure_ascii=False),
            )

            # Create session metadata
            session_metadata = self._create_session_metadata(
                session_id, thread_id, input_content, display_name
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
        thread_id: str,
        session_id: str,
        recognized_notes: str,
    ) -> Dict[str, Any]:
        """
        Сохраняет recognized_notes.md в существующую session

        Args:
            thread_id: Идентификатор потока
            session_id: Идентификатор сессии
            recognized_notes: Распознанный текст

        Returns:
            success/error status + file paths
        """
        try:
            # Build session path from thread_id and session_id
            session_path = self.base_path / thread_id / "sessions" / session_id

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
        thread_id: str,
        session_id: str,
        synthesized_material: str,
    ) -> Dict[str, Any]:
        """
        Сохраняет synthesized_material.md

        Args:
            thread_id: Идентификатор потока
            session_id: Идентификатор сессии
            synthesized_material: Синтезированный материал

        Returns:
            success/error status + file paths
        """
        try:
            # Build session path from thread_id and session_id
            session_path = self.base_path / thread_id / "sessions" / session_id

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
        thread_id: str,
        session_id: str,
        questions: list,
        questions_and_answers: list,
    ) -> Dict[str, Any]:
        """
        Сохраняет questions.md и отдельные answer файлы

        Args:
            thread_id: Идентификатор потока
            session_id: Идентификатор сессии
            questions: Список gap questions
            questions_and_answers: Список Q&A пар

        Returns:
            success/error status + файлы paths
        """
        try:
            # Build session path from thread_id and session_id
            session_path = self.base_path / thread_id / "sessions" / session_id

            if not session_path.exists():
                raise ValueError(f"Session path does not exist: {session_path}")

            created_files = []

            # Create gap questions content
            markdown_content = self._create_questions_content(
                questions=questions, questions_and_answers=questions_and_answers, thread_id=thread_id
            )

            # Write main questions file
            questions_file = session_path / "questions.md"
            self._atomic_write_file(questions_file, markdown_content)
            created_files.append("questions.md")

            # Create answers directory if there are individual answers
            if questions_and_answers:
                answers_dir = session_path / "answers"
                self._ensure_directory_exists(answers_dir)

                for i, qa in enumerate(questions_and_answers, 1):
                    answer_file = answers_dir / f"answer_{i:03d}.md"
                    answer_content = f"""# Ответ {i}

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
