# Рефакторинг GraphManager: Улучшение системы сохранения артефактов

## Текущее состояние

### Проблемы
1. **Нарушение принципа единственной ответственности (SRP)**
   - Метод `process_step` (220+ строк) выполняет слишком много задач
   - Логика сохранения артефактов смешана с обработкой событий графа
   - Высокая связанность компонентов

2. **Неполное покрытие узлов артефактами**
   - Артефакты сохраняются только после 3 из 7 узлов
   - Отсутствует автосохранение после `recognition_handwritten`, `generating_questions`, `answer_question`
   - Потенциальная потеря данных при прерывании workflow

3. **Дублирование кода**
   - Похожая логика для разных узлов повторяется
   - Сложность добавления новых узлов

### Текущая архитектура сохранения

```
data/artifacts/
└── {thread_id}/
    └── sessions/
        └── session-{timestamp}/
            ├── session_metadata.json
            ├── generated_material.md      # После generating_content
            ├── recognized_notes.md         # После recognition_handwritten (НЕ СОХРАНЯЕТСЯ)
            ├── synthesized_material.md     # После synthesis_material и edit_material
            ├── gap_questions.md           # После generating_questions (НЕ СОХРАНЯЕТСЯ В ПРОЦЕССЕ)
            └── answers/
                ├── answer_001.md          # После answer_question
                └── ...
```

### Логика работы с файлами

| Узел | Текущее поведение | Проблема |
|------|------------------|----------|
| `generating_content` | Создает сессию и `generated_material.md` | ✅ Работает |
| `recognition_handwritten` | Обновляет состояние | ❌ Не сохраняет артефакты |
| `synthesis_material` | Создает `synthesized_material.md` | ✅ Работает |
| `edit_material` | Перезаписывает `synthesized_material.md` | ✅ Работает |
| `generating_questions` | Обновляет состояние | ❌ Не сохраняет во время HITL |
| `answer_question` | Обновляет состояние | ❌ Сохраняется только в конце |

## Предлагаемое решение

### Стратегия: Конфигурационный подход с разделением методов

Выбран как оптимальный для MVP:
- Минимальные изменения в существующем коде
- Простота реализации и поддержки
- Легкое добавление новых узлов
- Отсутствие overengineering

### Архитектура решения

#### 1. Конфигурация узлов

```python
# В классе GraphManager
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

#### 2. Новая структура методов

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

#### 3. Специализированные методы сохранения

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

## План миграции (Direct Migration)

### Этап 1: Рефакторинг структуры
1. Добавить `NODE_ARTIFACT_CONFIG` в начало класса `GraphManager`
2. Разбить метод `process_step` на подметоды:
   - `_prepare_workflow`
   - `_run_workflow`
   - `_handle_workflow_event`
   - `_process_node_artifacts`
   - `_finalize_workflow`

### Этап 2: Реализация обработчиков
1. Создать специализированные методы сохранения:
   - `_save_learning_material`
   - `_save_recognized_notes`
   - `_save_synthesized_material`
   - `_save_gap_questions`
   - `_save_answers`
2. Удалить старые методы `_push_*`

### Этап 3: Очистка
1. Удалить дублирующуюся логику из `process_step`
2. Удалить неиспользуемые методы
3. Обновить логирование

## Преимущества решения

1. **Соответствие принципам SOLID**
   - Single Responsibility: каждый метод выполняет одну задачу
   - Open/Closed: легко добавлять новые узлы через конфигурацию

2. **Улучшенная поддерживаемость**
   - Код легче читать и понимать
   - Централизованная конфигурация
   - Меньше дублирования

3. **Полное покрытие артефактами**
   - Все узлы сохраняют свои артефакты
   - Единообразная обработка
   - Предотвращение потери данных

4. **MVP-подход**
   - Минимальные изменения
   - Простая реализация
   - Отсутствие overengineering

## Результат

После рефакторинга:
- Метод `process_step` сократится с 220+ до ~30 строк
- Все узлы будут автоматически сохранять артефакты
- Добавление нового узла потребует только обновления конфигурации
- Код станет более читаемым и тестируемым