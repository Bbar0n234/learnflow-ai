"""
GitHub интеграция для пуша артефактов LearnFlow AI.
"""

import os
import base64
import httpx
import logging
import re
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path
from pydantic import BaseModel

from .settings import get_settings


logger = logging.getLogger(__name__)


class GitHubConfig(BaseModel):
    """Конфигурация для GitHub интеграции"""
    
    token: str
    repository: str
    branch: str = "main"
    base_path: str = "artifacts"


class GitHubArtifactPusher:
    """Класс для пуша артефактов в GitHub репозиторий."""
    
    def __init__(self, config: GitHubConfig):
        self.config = config
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {config.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "LearnFlow-AI/1.0"
        }
    

    
    async def push_learning_material(
        self,
        thread_id: str,
        exam_question: str,
        generated_material: str,
    ) -> Dict[str, Any]:
        """
        Пушит обучающий материал в GitHub репозиторий.
        
        Args:
            thread_id: Идентификатор потока
            exam_question: Исходный экзаменационный вопрос
            generated_material: Сгенерированный обучающий материал
            
        Returns:
            Dict с информацией о созданном файле
        """
        try:
            # Создаем папку на основе exam_question с временной меткой
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            folder_path = f"{self.config.base_path}/{exam_question}"
            
            # Подготавливаем содержимое markdown файла
            markdown_content = self._create_learning_material_content(
                exam_question=exam_question,
                generated_material=generated_material,
                thread_id=thread_id,
                timestamp=timestamp
            )
            
            # Создаем файл в репозитории
            file_path = f"{folder_path}/learning_material.md"
            
            async with httpx.AsyncClient() as client:
                result = await self._create_file(
                    client=client,
                    file_path=file_path,
                    content=markdown_content,
                    commit_message=f"Add learning material: {exam_question} ({timestamp})"
                )
            
            logger.info(f"Successfully pushed learning material for thread {thread_id} to {file_path}")
            
            return {
                "success": True,
                "file_path": file_path,
                "folder_path": folder_path,
                "commit_sha": result.get("commit", {}).get("sha"),
                "html_url": result.get("content", {}).get("html_url"),
                "learning_material_url": f"https://github.com/{self.config.repository}/blob/{self.config.branch}/{file_path}",
                "folder_url": f"https://github.com/{self.config.repository}/tree/{self.config.branch}/{folder_path}"
            }
            
        except Exception as e:
            logger.error(f"Failed to push learning material for thread {thread_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }



    async def push_recognized_notes(
        self,
        folder_path: str,
        recognized_notes: str,
        thread_id: str,
    ) -> Dict[str, Any]:
        """
        Пушит распознанные конспекты в GitHub репозиторий.
        
        Args:
            folder_path: Путь к папке
            recognized_notes: Распознанный текст конспектов
            thread_id: Идентификатор потока
            
        Returns:
            Dict с информацией о созданном файле
        """
        try:
            # Подготавливаем содержимое markdown файла
            markdown_content = self._create_recognized_notes_content(
                recognized_notes=recognized_notes,
                thread_id=thread_id
            )
            
            # Создаем файл в репозитории
            file_path = f"{folder_path}/recognized_notes.md"
            
            async with httpx.AsyncClient() as client:
                result = await self._create_file(
                    client=client,
                    file_path=file_path,
                    content=markdown_content,
                    commit_message=f"Add recognized notes for thread {thread_id}"
                )
            
            logger.info(f"Successfully pushed recognized notes for thread {thread_id} to {file_path}")
            
            return {
                "success": True,
                "file_path": file_path,
                "commit_sha": result.get("commit", {}).get("sha"),
                "html_url": result.get("content", {}).get("html_url")
            }
            
        except Exception as e:
            logger.error(f"Failed to push recognized notes for thread {thread_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def push_synthesized_material(
        self,
        folder_path: str,
        synthesized_material: str,
        thread_id: str,
    ) -> Dict[str, Any]:
        """
        Пушит синтезированный материал в GitHub репозиторий.
        
        Args:
            folder_path: Путь к папке
            synthesized_material: Синтезированный материал
            thread_id: Идентификатор потока
            
        Returns:
            Dict с информацией о созданном файле
        """
        try:
            # Подготавливаем содержимое markdown файла
            markdown_content = self._create_synthesized_material_content(
                synthesized_material=synthesized_material,
                thread_id=thread_id
            )
            
            # Создаем файл в репозитории
            file_path = f"{folder_path}/synthesized_material.md"
            
            async with httpx.AsyncClient() as client:
                result = await self._create_file(
                    client=client,
                    file_path=file_path,
                    content=markdown_content,
                    commit_message=f"Add synthesized material for thread {thread_id}"
                )
            
            logger.info(f"Successfully pushed synthesized material for thread {thread_id} to {file_path}")
            
            return {
                "success": True,
                "file_path": file_path,
                "commit_sha": result.get("commit", {}).get("sha"),
                "html_url": result.get("content", {}).get("html_url")
            }
            
        except Exception as e:
            logger.error(f"Failed to push synthesized material for thread {thread_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def push_complete_materials(
        self,
        thread_id: str,
        exam_question: str,
        all_materials: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Комплексное сохранение всех материалов в GitHub.
        
        Args:
            thread_id: Идентификатор потока
            exam_question: Экзаменационный вопрос
            all_materials: Словарь со всеми материалами
                {
                    "generated_material": str,
                    "recognized_notes": str,
                    "synthesized_material": str,
                    "gap_questions": List[str],
                    "gap_q_n_a": List[str]
                }
                
        Returns:
            Dict с информацией обо всех созданных файлах
        """
        try:
            results = {}
            
            # 1. Создаем базовую папку и сохраняем основной материал
            learning_result = await self.push_learning_material(
                thread_id=thread_id,
                exam_question=exam_question,
                generated_material=all_materials.get("generated_material", "")
            )
            
            if not learning_result.get("success"):
                return {"success": False, "error": "Failed to create base folder"}
            
            folder_path = learning_result["folder_path"]
            results["learning_material"] = learning_result
            
            # 2. Сохраняем распознанные конспекты если есть
            recognized_notes = all_materials.get("recognized_notes", "")
            if recognized_notes.strip():
                notes_result = await self.push_recognized_notes(
                    folder_path=folder_path,
                    recognized_notes=recognized_notes,
                    thread_id=thread_id
                )
                results["recognized_notes"] = notes_result
            
            # 3. Сохраняем синтезированный материал если есть
            synthesized_material = all_materials.get("synthesized_material", "")
            if synthesized_material.strip():
                synthesis_result = await self.push_synthesized_material(
                    folder_path=folder_path,
                    synthesized_material=synthesized_material,
                    thread_id=thread_id
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
                    thread_id=thread_id
                )
                results["questions_and_answers"] = questions_result
            
            logger.info(f"Successfully pushed complete materials for thread {thread_id}")
            
            return {
                "success": True,
                "folder_path": folder_path,
                "folder_url": learning_result["folder_url"],
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Failed to push complete materials for thread {thread_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def push_questions_and_answers(
        self,
        folder_path: str,
        gap_questions: list,
        gap_q_n_a: list,
        thread_id: str,
    ) -> Dict[str, Any]:
        """
        Пушит вопросы и ответы в существующую поддиректорию GitHub репозитория.
        
        Args:
            folder_path: Путь к папке (из предыдущего пуша)
            gap_questions: Список дополнительных вопросов
            gap_q_n_a: Список Q&A пар
            thread_id: Идентификатор потока
            
        Returns:
            Dict с информацией о созданном файле
        """
        try:
            # Подготавливаем содержимое markdown файла
            markdown_content = self._create_questions_content(
                gap_questions=gap_questions,
                gap_q_n_a=gap_q_n_a,
                thread_id=thread_id
            )
            
            # Создаем файл в существующей папке
            file_path = f"{folder_path}/questions_and_answers.md"
            
            async with httpx.AsyncClient() as client:
                result = await self._create_file(
                    client=client,
                    file_path=file_path,
                    content=markdown_content,
                    commit_message=f"Add questions and answers for thread {thread_id}"
                )
            
            logger.info(f"Successfully pushed questions and answers for thread {thread_id} to {file_path}")
            
            return {
                "success": True,
                "file_path": file_path,
                "commit_sha": result.get("commit", {}).get("sha"),
                "html_url": result.get("content", {}).get("html_url"),
                "folder_url": f"https://github.com/{self.config.repository}/tree/{self.config.branch}/{folder_path}"
            }
            
        except Exception as e:
            logger.error(f"Failed to push questions and answers for thread {thread_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _create_recognized_notes_content(
        self,
        recognized_notes: str,
        thread_id: str = ""
    ) -> str:
        """Создает содержимое markdown файла с распознанными конспектами."""
        
        content = f"""# Распознанные конспекты

**Thread ID:** {thread_id}  
**Дата создания:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  

## Содержание конспектов

{recognized_notes}
"""
        
        return content

    def _create_synthesized_material_content(
        self,
        synthesized_material: str,
        thread_id: str = ""
    ) -> str:
        """Создает содержимое markdown файла с синтезированным материалом."""
        
        content = f"""# Синтезированный материал

**Thread ID:** {thread_id}  
**Дата создания:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  

## Финальный материал

Этот материал объединяет автоматически сгенерированный контент с распознанными рукописными конспектами для создания наиболее полного и точного учебного материала.

{synthesized_material}
"""
        
        return content
    
    def _create_learning_material_content(
        self,
        exam_question: str,
        generated_material: str,
        thread_id: str = "",
        timestamp: str = ""
    ) -> str:
        """Создает содержимое markdown файла с обучающим материалом."""
        
        content = f"""# Обучающий материал

**Thread ID:** {thread_id}  
**Дата создания:** {timestamp}  

## Исходный экзаменационный вопрос

{exam_question}

## Сгенерированный материал

{generated_material}
"""
        
        return content
    
    def _create_questions_content(
        self,
        gap_questions: list,
        gap_q_n_a: list,
        thread_id: str = ""
    ) -> str:
        """Создает содержимое markdown файла с вопросами и ответами."""
        
        content = f"""# Дополнительные вопросы и ответы

**Thread ID:** {thread_id}  

## Дополнительные вопросы

"""
        
        for i, question in enumerate(gap_questions, 1):
            content += f"{i}. {question}\n"
        
        content += "\n## Вопросы и ответы\n\n"
        
        for i, qa in enumerate(gap_q_n_a, 1):
            content += f"### {i}. Q&A\n\n{qa}\n\n---\n\n"
        
        return content


    
    async def _create_file(
        self,
        client: httpx.AsyncClient,
        file_path: str,
        content: str,
        commit_message: str
    ) -> Dict[str, Any]:
        """
        Создает файл в GitHub репозитории.
        
        Args:
            client: HTTP клиент
            file_path: Путь к файлу в репозитории
            content: Содержимое файла
            commit_message: Сообщение коммита
            
        Returns:
            Ответ от GitHub API
        """
        # Кодируем содержимое в base64
        content_encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        
        # Подготавливаем данные для API
        data = {
            "message": commit_message,
            "content": content_encoded,
            "branch": self.config.branch
        }
        
        # URL для создания файла
        url = f"{self.base_url}/repos/{self.config.repository}/contents/{file_path}"
        
        # Отправляем запрос
        response = await client.put(url, json=data, headers=self.headers)
        
        if response.status_code == 201:
            return response.json()
        else:
            response.raise_for_status()
    
    async def test_connection(self) -> bool:
        """
        Тестирует подключение к GitHub API.
        
        Returns:
            True если подключение успешно, False иначе
        """
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/repos/{self.config.repository}"
                response = await client.get(url, headers=self.headers)
                return response.status_code == 200
        except Exception as e:
            logger.error(f"GitHub connection test failed: {e}")
            return False 