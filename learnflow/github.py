"""
GitHub интеграция для пуша артефактов LearnFlow AI.
"""

import os
import base64
import httpx
import logging
import re
from datetime import datetime
from typing import Dict, Any, Optional
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