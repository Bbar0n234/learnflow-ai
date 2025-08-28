# Implementation Plan: GraphManager Artifact Saving System Refactoring

## Смысл и цель задачи

Рефакторинг системы сохранения артефактов в GraphManager для устранения нарушения принципа единственной ответственности (SRP), обеспечения полного покрытия всех узлов workflow автосохранением и устранения дублирования кода. Текущий метод `process_step` (220+ строк) смешивает логику обработки событий графа с сохранением артефактов, что затрудняет поддержку и расширение системы.

## Архитектура решения

Основные компоненты рефакторинга:
- **NODE_ARTIFACT_CONFIG** - централизованная конфигурация сохранения артефактов для каждого узла
- **Разделение методов** - декомпозиция `process_step` на специализированные методы
- **Универсальный обработчик** - единая точка обработки артефактов `_process_node_artifacts`
- **Специализированные методы сохранения** - отдельные методы для каждого типа артефактов

Расположение файлов:
- `/home/bbaron/dev/my-pet-projects/learnflow-ai/learnflow/core/graph_manager.py` - основной файл рефакторинга

## Полный flow работы функционала

1. Пользователь отправляет запрос через `process_step` с thread_id, query и опциональными image_paths
2. Метод `_prepare_workflow` подготавливает начальное состояние и конфигурацию
3. `_run_workflow` запускает граф и обрабатывает события через stream
4. Для каждого события вызывается `_handle_workflow_event`
5. `_process_node_artifacts` проверяет конфигурацию узла и вызывает соответствующий обработчик сохранения
6. Специализированные методы (`_save_learning_material`, `_save_recognized_notes` и т.д.) сохраняют артефакты
7. `_finalize_workflow` завершает работу, сохраняет финальные артефакты и очищает thread при необходимости

## API и интерфейсы

### Конфигурация узлов (NODE_ARTIFACT_CONFIG)
```python
NODE_ARTIFACT_CONFIG = {
    "generating_content": {
        "condition": lambda node_data, state: bool(node_data.get("generated_material")),
        "handler": "_save_learning_material",
        "requires_session": False  # Создает новую сессию
    },
    "recognition_handwritten": {
        "condition": lambda node_data, state: bool(node_data.get("recognized_notes")),
        "handler": "_save_recognized_notes",
        "requires_session": True
    },
    "synthesis_material": {
        "condition": lambda node_data, state: bool(node_data.get("synthesized_material")),
        "handler": "_save_synthesized_material",
        "requires_session": True
    },
    "edit_material": {
        "condition": lambda node_data, state: node_data.get("last_action") == "edit",
        "handler": "_save_synthesized_material",  # Тот же метод, перезапись
        "requires_session": True
    },
    "generating_questions": {
        "condition": lambda node_data, state: bool(node_data.get("gap_questions")),
        "handler": "_save_gap_questions",
        "requires_session": True
    },
    "answer_question": {
        "condition": lambda node_data, state: bool(node_data.get("gap_q_n_a")),
        "handler": "_save_answers",
        "requires_session": True
    }
}
```

### Новая структура методов
```python
class GraphManager:
    async def process_step(self, thread_id: str, query: str, 
                          image_paths: List[str] = None) -> Dict[str, Any]:
        """Упрощенный главный метод"""
        # 1. Подготовка
        thread_id, input_state, cfg = await self._prepare_workflow(
            thread_id, query, image_paths
        )
        
        # 2. Выполнение workflow
        await self._run_workflow(thread_id, input_state, cfg)
        
        # 3. Финализация
        return await self._finalize_workflow(thread_id)
    
    async def _prepare_workflow(self, thread_id: str, query: str, 
                               image_paths: List[str]) -> Tuple:
        """Подготовка workflow: thread_id, начальное состояние, конфигурация"""
        # Логика инициализации thread_id, input_state, cfg
        pass
    
    async def _run_workflow(self, thread_id: str, input_state: Any, 
                           cfg: Dict) -> None:
        """Запуск workflow и обработка событий"""
        await self._ensure_setup()
        
        async with AsyncPostgresSaver.from_conn_string(
            self.settings.database_url
        ) as saver:
            graph = self.workflow.compile(checkpointer=saver)
            
            async for event in graph.astream(input_state, cfg, stream_mode="updates"):
                await self._handle_workflow_event(event, thread_id)
    
    async def _handle_workflow_event(self, event: Dict, thread_id: str) -> None:
        """Обработка одного события workflow"""
        for node_name, node_data in event.items():
            await self._process_node_artifacts(node_name, node_data, thread_id)
    
    async def _process_node_artifacts(self, node_name: str, 
                                     node_data: Dict, 
                                     thread_id: str) -> None:
        """Универсальная обработка артефактов для узла"""
        config = self.NODE_ARTIFACT_CONFIG.get(node_name)
        if not config:
            return
        
        # Получаем текущее состояние
        state = await self._get_state(thread_id)
        
        # Проверяем условие сохранения
        if not config["condition"](node_data, state.values):
            return
        
        logger.info(f"Saving artifacts for {node_name}, thread {thread_id}")
        
        # Вызываем соответствующий обработчик
        handler = getattr(self, config["handler"])
        await handler(thread_id, node_data, state.values)
    
    async def _finalize_workflow(self, thread_id: str) -> Dict[str, Any]:
        """Завершение workflow: обработка прерываний или финальная очистка"""
        # Логика обработки final_state, interrupts, удаления thread
        pass
```

### Специализированные методы сохранения
```python
async def _save_learning_material(self, thread_id: str, 
                                 node_data: Dict, 
                                 state_values: Dict) -> None:
    """Создает новую сессию и сохраняет обучающий материал"""
    if not self.artifacts_manager:
        return
    
    result = await self.artifacts_manager.push_learning_material(
        thread_id=thread_id,
        exam_question=state_values.get("exam_question", ""),
        generated_material=node_data.get("generated_material", ""),
        display_name=state_values.get("display_name")
    )
    
    if result.get("success"):
        # Сохраняем пути в локальном словаре
        if thread_id not in self.artifacts_data:
            self.artifacts_data[thread_id] = {}
        
        self.artifacts_data[thread_id].update({
            "local_session_path": result.get("folder_path"),
            "local_folder_path": result.get("folder_path"),
            "session_id": result.get("session_id"),
            "local_learning_material_path": result.get("file_path")
        })
        
        # Обновляем состояние графа
        await self._update_state(thread_id, self.artifacts_data[thread_id])

async def _save_recognized_notes(self, thread_id: str, 
                                node_data: Dict, 
                                state_values: Dict) -> None:
    """Сохраняет распознанные конспекты в существующую сессию"""
    if not self.artifacts_manager:
        return
        
    folder_path = self.artifacts_data.get(thread_id, {}).get("local_folder_path")
    if not folder_path:
        logger.warning(f"No folder path for thread {thread_id}")
        return
    
    await self.artifacts_manager.push_recognized_notes(
        folder_path=folder_path,
        recognized_notes=node_data.get("recognized_notes", ""),
        thread_id=thread_id
    )

async def _save_synthesized_material(self, thread_id: str, 
                                    node_data: Dict, 
                                    state_values: Dict) -> None:
    """Сохраняет или перезаписывает синтезированный материал"""
    if not self.artifacts_manager:
        return
        
    folder_path = self.artifacts_data.get(thread_id, {}).get("local_folder_path")
    if not folder_path:
        logger.warning(f"No folder path for thread {thread_id}")
        return
    
    # Для edit_material берем из состояния, для synthesis_material из node_data
    material = (state_values.get("synthesized_material") 
                if "edit_material" in str(node_data) 
                else node_data.get("synthesized_material", ""))
    
    await self.artifacts_manager.push_synthesized_material(
        folder_path=folder_path,
        synthesized_material=material,
        thread_id=thread_id
    )

async def _save_gap_questions(self, thread_id: str, 
                             node_data: Dict, 
                             state_values: Dict) -> None:
    """Сохраняет gap questions"""
    if not self.artifacts_manager:
        return
        
    folder_path = self.artifacts_data.get(thread_id, {}).get("local_folder_path")
    if not folder_path:
        return
    
    # Сохраняем только вопросы без ответов
    await self.artifacts_manager.push_questions_and_answers(
        folder_path=folder_path,
        gap_questions=node_data.get("gap_questions", []),
        gap_q_n_a=[],  # Пустой список, т.к. ответов еще нет
        thread_id=thread_id
    )

async def _save_answers(self, thread_id: str, 
                       node_data: Dict, 
                       state_values: Dict) -> None:
    """Сохраняет ответы на вопросы"""
    if not self.artifacts_manager:
        return
        
    folder_path = self.artifacts_data.get(thread_id, {}).get("local_folder_path")
    if not folder_path:
        return
    
    # Обновляем файл с вопросами и ответами
    await self.artifacts_manager.push_questions_and_answers(
        folder_path=folder_path,
        gap_questions=state_values.get("gap_questions", []),
        gap_q_n_a=state_values.get("gap_q_n_a", []),
        thread_id=thread_id
    )
```

## Взаимодействие компонентов

```
process_step -> _prepare_workflow -> ExamState/Command
                |
                v
            _run_workflow -> graph.astream -> events
                |
                v
         _handle_workflow_event -> _process_node_artifacts
                |
                v
         NODE_ARTIFACT_CONFIG check -> handler call
                |
                v
         _save_* methods -> artifacts_manager.push_*
                |
                v
         _finalize_workflow -> _push_complete_materials -> delete_thread
```

## Порядок реализации

### Этап 1: Рефакторинг структуры (безопасная подготовка)
1. Добавить `NODE_ARTIFACT_CONFIG` в начало класса `GraphManager`
2. Создать новые методы-заглушки (`_prepare_workflow`, `_run_workflow`, `_handle_workflow_event`, `_process_node_artifacts`, `_finalize_workflow`) рядом с существующим кодом
3. Создать специализированные методы сохранения (`_save_learning_material`, `_save_recognized_notes`, `_save_synthesized_material`, `_save_gap_questions`, `_save_answers`)
4. Протестировать, что существующий код продолжает работать

### Этап 2: Миграция логики (поэтапный перенос)
1. Перенести логику подготовки workflow из `process_step` в `_prepare_workflow`
2. Перенести логику запуска и обработки событий в `_run_workflow` и `_handle_workflow_event`
3. Реализовать универсальную обработку артефактов в `_process_node_artifacts`
4. Перенести логику финализации в `_finalize_workflow`
5. Обновить `process_step` для использования новых методов
6. Удалить старые методы `_push_*` после проверки работоспособности

### Этап 3: Очистка и оптимизация
1. Удалить дублирующийся код из старой версии `process_step`
2. Упростить логику обработки interrupts и сообщений
3. Обновить логирование для лучшей трассировки
4. Провести финальное тестирование всех узлов workflow
5. Обновить документацию

## Критичные граничные случаи

1. **Отсутствие artifacts_manager** - все методы сохранения должны корректно обрабатывать случай, когда manager не настроен
2. **Отсутствие folder_path для thread** - методы должны проверять наличие пути перед сохранением
3. **Прерывание workflow на любом узле** - система должна корректно сохранять промежуточные артефакты
4. **Повторные вызовы edit_material** - должны корректно перезаписывать синтезированный материал
5. **Параллельные запросы для одного thread_id** - защита через PostgreSQL checkpointer