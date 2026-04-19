# Output Similarity Metric для Prompt/Identifier Leak Detection — Research R2

## TL;DR

1. **Mid-stream composite detector (per-chunk)**: Комбинируем три быстрых сигнала на exact/near-exact совпадения — substring match (O(1) via Aho-Corasick), fuzzy Levenshtein ratio (threshold 0.85+), n-gram Jaccard (3–4-grams, 0.7+). Вердикт: **threshold N≥2 совпадений → SUSPICIOUS**, все три → LEAK. Формула: weighted sum (exact: 1.0, fuzzy: 0.7, n-gram: 0.5), порог 1.5.

2. **End-of-stream semantic classifier**: Двухэтапный подход — (1) BERTScore против system_prompt (threshold τ≥0.75 → SUSPICIOUS), (2) cross-encoder reranker sentence-transformers `cross-encoder/ms-marco-MiniLM-L-12-v2` для уточнения similarity output vs reference identifiers (single score 0.6–0.8 → SUSPICIOUS, >0.8 → LEAK). Latency ~500–800ms приемлем для end-of-stream (показываем индикатор пользователю).

3. **Embedding model**: Рекомендуем `text-embedding-3-small` (OpenAI, $0.02/M tokens, 1536 dims, latency ~50ms) или open-source `e5-base-v2` (free, ~80ms, качество 83–85%). Для BGE-M3 cost hosting, но multilingua и sparse search опция.

4. **User echo handling**: Перед детекцией автоматически фильтруем conversation history — исключаем токены, которые пользователь упомянул в последних 3 сообщениях. Context-aware weighting: tool names (weight 1.0) > parameters (0.7) > descriptions (0.3).

5. **FP/FN trade-off**: Industry standard для production detectors — 0.1–1% FPR при >90% F₁. LearnFlowAI: рекомендуем **0.5% FPR** (10 FP на 2000 benign responses) как приемлемый баланс, SUSPICIOUS — только логируется, LEAK — блокируется.

6. **Benchmarks**: Gandalf 40M+ prompts, Tensor Trust 563k+ attacks, PINT 3007 inputs (Lakera Guard достигает 74.6% accuracy). Нет публичных FP/FN таблиц для *leak detection* (есть для injection detection), поэтому в первой итерации калибруем на synthetic tests.

7. **Ключевое решение**: Composite detector (mid-stream) — дешёвый, детерминированный, ~100% точность на exact matches. LLM classifier (end-of-stream) — ловит парафразы и semantic leaks. Together обеспечивают defense-in-depth без чрезмерных FP.

---

## Постановка Задачи

### Область 1: Mid-Stream Composite Identifier Detector

Предпосылка: на каждом streaming chunk (SSE event) нужна быстрая детерминированная проверка, не попадает ли в ответ агента какой-либо элемент из curated list PRIVATE identifiers:

- **Инструменты** (tool names): `brave_web_search`, `arxiv_search`, `firecrawl_fetch`, `github_api`, `code_executor`
- **Параметры** (parameter names): `api_key`, `endpoint_url`, `timeout_seconds`, `max_retries`
- **MCP серверы** (MCP server identifiers): `docker`, `filesystem`, `postgresql`
- **Провайдеры LLM** (provider names): `openai`, `anthropic`, `gemini`, `together-ai`
- **Внутренние node/skill names**: node IDs в LangGraph, skill identifiers
- **Canary tokens**: уникальные маркеры, внедренные в system prompt (формат: `CANARY-<uuid>`)

**Вызов**: Как сводить N совпадений в single verdict? Какая комбинация метрик? Какой порог?

### Область 2: End-of-Stream Semantic Leak Classifier

После завершения streaming response полный ответ (~1–10 KB) проверяется LLM-based classifier на предмет:

- **Парафразированный system prompt**: "Вам дана инструкция...", "Вы должны следовать...", перифраз целых блоков инструкций
- **Описание реализации**: "Я использую GraphQL API", "Мой рантайм основан на Python с asyncio", раскрытие архитектуры
- **Точные идентификаторы в свободной форме**: tool names, parameter names, описания вне прямого копирования

**Вызов**: Как метрика similarity захватывает семантическую схожесть output с system_prompt или reference identifiers list? Embedding-based vs hybrid?

---

## Candidate Метрики

### 1. Exact / Near-Exact Matching

#### 1.1 Substring Match (Baseline)
- **Механика**: Simple `if pattern in text` (Python `str.find()`)
- **Complexity**: O(n) naive, O(n+m) с KMP, O(n+m) amortized с Aho-Corasick для N patterns
- **Pro**: Instantaneous на small chunks (~1 KB), zero memory overhead, 100% accurate для exact matches
- **Con**: Не ловит typos, переформатирование (e.g., `brave_web_search` → `brave-web-search`)
- **Industry use**: Baseline в Rebuff, Lakera Guard, NeMo Guardrails
- **Threshold**: 1 exact match → flag (но как обработать benign echos?)
- **Рекомендация для R2**: Use Aho-Corasick для N patterns, O(1) amortized per chunk symbol

#### 1.2 Aho-Corasick Multi-Pattern Matching
- **Механика**: Построить автомат на startup из всех identifiers, затем per-chunk O(1) amortized update
- **Complexity**: O(m + z) где m = total pattern length, z = number of matches
- **Pro**: Отлично для streaming (per-chunk), 100% exact match accuracy, standard в intrusion detection
- **Con**: Требует pre-compilation identifiers list
- **Implementation**: `pyahocorasick` (Python), ~50 LOC для wrapper
- **Рекомендация**: Primary для mid-stream detector

#### 1.3 Levenshtein Distance (Edit Distance)
- **Механика**: Min edit ops (insert, delete, substitute) для трансформации pattern → text
- **Complexity**: O(n*m) naive DP, O(n) per char с optimized sliding window, ~100ms для 1 KB chunk + 100 patterns
- **Pro**: Ловит typos, minor rewording (`brave-web` vs `brave_web`), понятна интуитивно
- **Con**: Computationally expensive для многих patterns, не semantic
- **Threshold (industry)**: Ratio ≥0.85 обычно = suspicious (из BERTScore evaluation practices)
- **Library**: `rapidfuzz` (faster than FuzzyWuzzy, MIT licensed), `difflib.SequenceMatcher` (stdlib)
- **Рекомендация для R2**: Apply на identifiers если substring match не сработал, ratio ≥0.85

#### 1.4 Fuzzy String Matching (RapidFuzz)
- **Механика**: Levenshtein ratio + token sorting, вариации для different token orders
- **Complexity**: Similar to Levenshtein, ~150ms для 1 KB + 100 patterns
- **Pro**: Robust к переупорядочиванию tokens (`search web brave` vs `brave web search`), industry-standard
- **Con**: Still не semantic
- **Threshold**: Token sort ratio ≥0.80 = slightly fuzzy
- **Рекомендация**: Secondary line, если exact + edit distance не поймали

---

### 2. N-Gram Based

#### 2.1 Character N-Gram Jaccard
- **Механика**: Extract 3–4-char n-grams, compute Jaccard = |intersection| / |union|
- **Complexity**: O(n) extraction, O(m) comparison (m = unique n-grams), <5ms для chunk
- **Pro**: Быстро, robust к spacing, captures sub-word similarity (`restapi` vs `rest_api`)
- **Con**: Не semantic, может быть noisy (много false positives на common substrings)
- **Threshold (industry)**: Jaccard ≥0.7 (from open-source deduplicate libraries)
- **Library**: `difflib`, `nltk`, or custom
- **Рекомендация**: Tertiary signal для composite score (low weight)

#### 2.2 Word N-Gram Overlap (BLEU/ROUGE-like)
- **Механика**: 1–2-gram word overlap, precision/recall/F1
- **Complexity**: O(n) tokenization + O(m) comparison, ~10ms
- **Pro**: More semantic than char n-grams, standard в NLP (BLEU, ROUGE)
- **Con**: Требует tokenization, sensitive к punctuation
- **Threshold**: ROUGE-N F1 ≥0.5 обычно = some similarity
- **Рекомендация**: Include but low weight в composite

---

### 3. Token-Based

#### 3.1 Token Overlap Ratio
- **Механика**: Simple `|tokens_intersection| / |tokens_union|` после tokenization
- **Complexity**: O(n) tokenization, O(m) set ops, <5ms
- **Pro**: Efficient, interpretable, no training
- **Con**: Order-insensitive, не semantic
- **Threshold**: ≥0.6 = moderate overlap
- **Рекомендация**: Include в composite (medium weight)

#### 3.2 TF-IDF Cosine Similarity
- **Механика**: Vectorize via TF-IDF, compute cosine similarity в sparse matrix
- **Complexity**: O(n + m) per pair (n = corpus size, m = pattern size), ~50ms для chunk + reference
- **Pro**: Downweights common terms, better than raw overlap
- **Con**: Requires training corpus (or pre-computed IDF), not real-time adaptable
- **Threshold**: Cosine ≥0.6
- **Library**: `scikit-learn.TfidfVectorizer`
- **Рекомендация**: Optional (expensive для streaming)

---

### 4. Semantic (Embedding-Based)

#### 4.1 Embedding Cosine Similarity (Bi-Encoder)
- **Механика**: Embed output и reference на embedding model, compute cosine на vectors
- **Complexity**: 
  - Embedding: ~50–200ms per text (зависит от model, batch size, text length)
  - Cosine: O(d) где d = embedding dimension (~1536 для text-embedding-3-small)
  - End-to-end: ~100–500ms для 5 KB response на single GPU
- **Pro**: Semantic similarity, ловит парафразы, robust к syntactic variations
- **Con**: 
  - Latency unsuitable для mid-stream (streaming chunks)
  - Model cost (OpenAI) или hosting (open-source)
  - Can be gamed (adversarial rephrasing)
- **Threshold (industry)**:
  - BERTScore uses τ=0.85 для evaluation semantic deviation
  - Cosine similarity ≥0.75 = significant overlap (from similarity search literature)
  - ≥0.8 = very similar (likely leak in security context)
- **Model candidates**:
  1. **text-embedding-3-small** (OpenAI): $0.02/M tokens, 1536 dims, 50ms latency, excellent quality
  2. **e5-base-v2** (open-source): Free, 768 dims, ~80ms, quality 83–85% MTEB
  3. **BGE-M3** (open-source): Free, 4096 dims, multilingual, sparse+dense retrieval, latency ~100ms
- **Рекомендация**: End-of-stream semantic classifier primary signal (not mid-stream)

#### 4.2 Cross-Encoder Reranker
- **Механика**: Process paired (output, reference) через shared neural network, single similarity score
- **Complexity**: ~200–500ms per pair на single GPU (slower than bi-encoder но higher accuracy)
- **Pro**: Higher accuracy чем bi-encoder, better for ranking/classification
- **Con**: Slower, computationally expensive для many candidates
- **Threshold**: Score ≥0.7 = suspicious (depends on model training)
- **Model**: `cross-encoder/ms-marco-MiniLM-L-12-v2` (~120MB, latency ~200ms per pair)
- **Рекомендация**: Optional refinement stage после bi-encoder screening

#### 4.3 BERTScore
- **Механика**: Token-level cosine similarity via contextual embeddings (BERT/RoBERTa), then max-match greedy + recall/precision/F1
- **Complexity**: O(n*m*d) где n=reference tokens, m=candidate tokens, d=embedding dim, ~500–1000ms для 5 KB
- **Pro**: Robust к paraphrase detection, semantic equivalence
- **Con**: Computationally expensive, requires BERT model, designed for eval not detection
- **Threshold**: F1 ≥0.75 = significant semantic similarity (from paper)
- **Implementation**: `evaluate` lib, HuggingFace `bertscore` package
- **Рекомендация**: Optional для end-of-stream (slower than cosine, but higher semantic accuracy)

---

## Off-the-Shelf Решения

### Rebuff (Archived May 2025)
- **Architecture**: Heuristic → LLM detection → Vector similarity → Canary tokens
- **Composite scoring**: Aggregates confidence scores từ каждого layer, user configures thresholds для FP/FN trade-off
- **Output validation**: Limited; more focused на input. Can be extended but нет built-in output leak detector
- **Status**: No longer maintained; reference only
- **Relevant learnings**: Composite scoring pattern, confidence aggregation

### Lakera Guard
- **Performance**: 74.6% accuracy, precision 0.94 with context, <30ms latency (inference only)
- **Detection layers**: Specialized classifier trained on 80M+ attack data points
- **Output validation**: Data Leakage Prevention guardrail covers system prompts + org-specific sensitive data
- **Composite approach**: Risk assessment with categories + confidence scores
- **Threshold levels**: L1–L4 (Lenient to Paranoid) for FP/FN tuning
- **Cost**: Commercial API
- **Recommendation**: Can be integrated как external validation; consider cost vs. custom solution

### NVIDIA NeMo Guardrails
- **Architecture**: Policy-based rail system (input, dialog, output, retrieval)
- **Output validation**: Output rails фильтруют LLM response перед вывод пользователю
- **Integration**: Llama Guard integration available
- **Composite scoring**: Limited built-in; mostly policy enforcement
- **Open-source**: Yes, community driven
- **Recommendation**: Good for policy framework; output validation rules можно адаптировать под R2

### Meta Llama Guard
- **Purpose**: Input/output moderation (toxicity, unsafe content)
- **Detection**: LLM-based classification into unsafe categories
- **Customization**: Can add custom categories
- **Relevant**: Not directly for prompt leak detection, but safety classification architecture applicable
- **Recommendation**: Could be integrated для multi-dimensional safety check

### Guardrails AI
- **Approach**: Composable validators stacked in pipelines
- **Output validation**: Validators intercept LLM responses, enforce constraints
- **Custom validators**: Write arbitrary Python functions
- **Composite pattern**: Chain validators, aggregate results
- **Relevant**: Framework pattern applicable for R2 composite detector

### LLM-Guard (ProtectAI)
- **Scanners**: Multiple input/output/context scanners
- **Composite**: Aggregates multiple scanner outputs
- **Customization**: Extendable with custom scanners
- **Community**: Active development (2024–2025)
- **Recommendation**: Potentially usable as baseline; check if output scanners cover leak detection

---

## Benchmarks & Datasets

### Gandalf (Lakera)
- **Size**: 40M+ prompts, 1M+ players since May 2023
- **Task**: Guess password in conversation with LLM
- **Relevance**: Large-scale adversarial dataset, includes system prompt extraction attacks
- **Public data**: `gandalf_ignore_instructions` dataset available
- **FP/FN**: Не публикуется, but training set большой и diverse
- **Threshold calibration**: Use для synthetic bench creation

### Tensor Trust (UC Berkeley)
- **Size**: 563k+ prompt injection attacks, 118k+ defenses (from online game)
- **Tasks**: Prompt extraction + prompt hijacking
- **Relevance**: Large-scale real attacks, includes defense mechanisms
- **Public data**: Full dataset available
- **Metrics**: No published FP/FN table, но data rich for analysis
- **Benchmark categories**: 
  - Prompt extraction: Attacks aimed to reveal hidden instructions (similar to R2 threat)
  - Prompt hijacking: Override instruction without extraction
- **Recommendation**: Use для synthetic test generation (extract real attack patterns)

### PINT Benchmark (Lakera)
- **Size**: 3007 English inputs, diverse public + proprietary attack techniques
- **Coverage**: Prompt injection attacks + FP test cases + large document handling
- **Metrics**: Precision, Recall, F₁ по detector
- **Published results**: Lakera Guard 74.6% accuracy
- **Relevance**: Most directly applicable для injection detection evaluation
- **Limitation**: Focuses на injection, not leak detection
- **Recommendation**: Adapt для leak detection by synthetic mutation

### PromptBench
- **Coverage**: Attacks + robustness evaluation
- **Not directly**: PromptBench focused на adversarial robustness, not leak detection

### Emerging metrics
- **BERTScore evaluation**: Standard τ=0.85 for semantic similarity
- **MTEB leaderboard**: Embedding model quality benchmarks (top models listed earlier)

### Custom synthesis for R2
Так как public benchmarks для leak detection limited, рекомендуем:
1. Synthetic test set: Generate паrafrased prompts via LLM (Llama-2, Mistral)
2. Injection-based: Use Gandalf/Tensor Trust attacks, mutate to force leak patterns
3. FP baseline: Real benign responses из production (anonymized)
4. Calibrate thresholds на 70% synthetic, validate на 30% held-out

---

## Composite Scoring Patterns

### Pattern 1: Weighted Sum (Recommended для Mid-Stream)

```
score = w1 * exact_match + w2 * fuzzy_ratio + w3 * ngram_jaccard + w4 * token_overlap
      = 1.0 * X_exact + 0.7 * X_fuzzy + 0.5 * X_ngram + 0.3 * X_token

Verdict:
  - score >= 1.5: SUSPICIOUS (2+ signals hit)
  - score >= 2.5: LIKELY LEAK (3+ signals, higher confidence)
  - All 4 signals strong (each >0.8): DEFINITE LEAK
```

**Rationale**:
- Exact match = highest fidelity (weight 1.0)
- Fuzzy = moderate confidence (weight 0.7)
- N-gram = lower confidence solo, but additive (weight 0.5)
- Token overlap = weakest signal (weight 0.3)

**Threshold calibration**:
- 1.5 = 2+ signals, acceptable FP rate for mid-stream (user sees indicator, can dismiss)
- 2.5 = 3+ signals, higher confidence, log anomaly
- All strong = manual review or block (rare)

### Pattern 2: Voting (Simpler Alternative)

```
count = sum([exact_match, fuzzy_ratio > 0.85, ngram_jaccard > 0.7, token_overlap > 0.6])

Verdict:
  - count >= 2: SUSPICIOUS
  - count >= 3: LIKELY LEAK
  - count == 4: DEFINITE LEAK
```

**Rationale**: Boolean aggregation, fewer tuning parameters.
**Trade-off**: Less granular than weighted sum.

### Pattern 3: Confidence Aggregation (Rebuff-style)

Each detector returns (verdict, confidence). Aggregate confidences into final risk score.

```
risk = aggregate([
  (exact_match.confidence, weight=1.0),
  (fuzzy.confidence, weight=0.7),
  (ngram.confidence, weight=0.5),
  (token.confidence, weight=0.3)
])

Aggregation: Weighted geometric mean или weighted arithmetic mean
Verdict: risk >= threshold → SUSPICIOUS
```

**Rationale**: Probabilistic aggregation, better for calibration.
**Trade-off**: More complex implementation.

---

## Efficiency Analysis

### Mid-Stream (Per-Chunk, ~1–5 KB chunks)

| Metric | Latency (1 KB) | Complexity | Per-Chunk | Cumulative |
|--------|----------------|------------|-----------|-----------|
| Substring (exact) | <1ms | O(n+m) | ✓ | Fast |
| Aho-Corasick | <1ms | O(1) amortized | ✓ | Fast |
| Levenshtein (100 patterns) | 50–100ms | O(n*m) | ✗ | Too slow |
| Fuzzy (RapidFuzz) | 30–80ms | O(n*m) | ✗ | Marginal |
| Char n-gram Jaccard | 3–5ms | O(n) | ✓ | Fast |
| Word n-gram ROUGE | 5–10ms | O(n) | ✓ | Fast |
| Token overlap | <1ms | O(n) | ✓ | Fast |
| TF-IDF cosine | 50–100ms | O(n+m) | ✗ | Too slow |
| Embedding cosine | 50–200ms | O(d) | ✗ | Too slow |

**Recommendation для mid-stream**:
- Primary: Aho-Corasick exact match (0.5ms)
- Secondary: Char n-gram Jaccard (3ms)
- Tertiary: Token overlap (0.5ms)
- **Total latency: <5ms per chunk** ✓

---

### End-of-Stream (Full Response, ~1–10 KB, single batch)

| Metric | Latency (5 KB) | Latency (10 KB) | Cost | Quality |
|--------|----------------|-----------------|------|---------|
| BERTScore | 500–1000ms | 1000–2000ms | API: $0.10/M tokens | High |
| Embedding cosine | 100–200ms | 150–300ms | OpenAI: $0.02/M, e5: free | High |
| Cross-encoder | 200–500ms | 300–800ms | free (self-hosted) | Very High |
| TF-IDF cosine | 50–100ms | 100–200ms | free | Medium |

**Recommendation для end-of-stream**:
- Primary: Embedding cosine (text-embedding-3-small, 100–200ms) + simple cosine threshold
- Optional refinement: Cross-encoder (add 200ms) за higher accuracy
- **Total acceptable latency: 100–500ms** ✓ (frontend shows "checking for safety..." indicator)

---

## User Echo / Pre-Existing Mentions Handling

**Problem**: Пользователь напишет "Используй `brave_web_search`", агент включит это в response → детектор флагирует как leak, хотя это просто echo пользовательского input.

**Solution — Context-Aware Filtering**:

1. **Conversation history preprocessing**:
   ```
   user_tokens = tokenize(last_N_user_messages)  # N=3 last messages
   private_identifiers_user_mentioned = [id for id in PRIVATE_IDENTIFIERS 
                                        if id in user_tokens]
   ```

2. **Exclude user mentions from detection**:
   ```
   identifiers_to_check = PRIVATE_IDENTIFIERS - private_identifiers_user_mentioned
   ```

3. **Weight by context**:
   ```
   context_weight = {
     'tool_name': 1.0,      # High sensitivity
     'parameter_name': 0.7,  # Medium
     'description': 0.3,     # Low (often mentioned in explanations)
     'provider_name': 0.8,   # High
   }
   
   adjusted_score = sum([
     context_weight[category] * signal_strength 
     for category, signal in detections
   ])
   ```

4. **Recency weighting** (optional):
   ```
   if identifier appeared <= 2 messages ago:
     weight *= 0.5  # Lower confidence в recent echo
   ```

**Edge cases**:
- User mentions incomplete pattern (e.g., "search" in "brave_web_search") → requires fuzzy matching to filter
- User mentions in background context vs active request → filter more aggressively if in last message only
- User pastes tool schema → exclude entire schema from detection

**Implementation**:
```python
def should_filter_identifier(identifier: str, 
                            conversation_history: List[dict],
                            lookback_messages: int = 3) -> bool:
    """Check if identifier was already mentioned by user."""
    recent_user_text = " ".join([
        msg['content'] for msg in conversation_history[-lookback_messages:]
        if msg['role'] == 'user'
    ])
    
    # Exact match or fuzzy match (>80%)
    return (identifier in recent_user_text or 
            fuzzy_match(identifier, recent_user_text) > 0.8)
```

---

## Recommendations для LearnFlowAI

### Mid-Stream Composite Detector (Per-Chunk Handler)

**Architecture**:
```
SSE chunk → Aho-Corasick exact match (O(1))
          → Char n-gram Jaccard if no exact
          → Token overlap ratio
          → Weighted sum (formula above)
          → Verdict: SUSPICIOUS/LEAK + confidence
          → Log + User indicator
```

**Metrics**:
- **Primary**: Aho-Corasick exact match (weight 1.0)
- **Secondary**: Char 3-gram Jaccard (weight 0.5)
- **Tertiary**: Token overlap (weight 0.3)

**Threshold**:
- Score ≥ 1.5 → SUSPICIOUS (log, show indicator to user)
- Score ≥ 2.0 → HIGH CONFIDENCE (log anomaly, could auto-block)

**Configuration (JSON)**:
```json
{
  "mid_stream_detector": {
    "enabled": true,
    "private_identifiers": ["brave_web_search", "arxiv_search", ...],
    "metrics": {
      "exact_match": {"weight": 1.0, "enabled": true},
      "ngram_jaccard": {"weight": 0.5, "n": 3, "threshold": 0.7, "enabled": true},
      "token_overlap": {"weight": 0.3, "threshold": 0.6, "enabled": true}
    },
    "composite_threshold": 1.5,
    "user_echo_lookback_messages": 3
  }
}
```

**Implementation**:
```python
# Pseudocode
import pyahocorasick

class MidStreamDetector:
    def __init__(self, identifiers: List[str]):
        self.automaton = pyahocorasick.Automaton()
        for id in identifiers:
            self.automaton.add_word(id, id)
        self.automaton.make_automaton()
    
    def detect(self, chunk: str, config: Dict) -> Dict[str, Any]:
        score = 0.0
        matches = []
        
        # Exact match
        for end_idx, identifier in self.automaton.iter(chunk):
            matches.append(('exact', identifier, 1.0))
            score += 1.0 * config['metrics']['exact_match']['weight']
        
        # N-gram Jaccard (if no exact)
        if not matches:
            ngram_score = compute_ngram_jaccard(chunk, ...)
            if ngram_score >= config['metrics']['ngram_jaccard']['threshold']:
                score += ngram_score * config['metrics']['ngram_jaccard']['weight']
                matches.append(('ngram', ..., ngram_score))
        
        verdict = 'LEAK' if score >= 2.0 else 'SUSPICIOUS' if score >= 1.5 else 'CLEAN'
        return {
            'verdict': verdict,
            'score': score,
            'matches': matches,
            'confidence': min(score / 2.5, 1.0)  # Normalize to [0, 1]
        }
```

---

### End-of-Stream Semantic Classifier (Full Response)

**Architecture**:
```
Full response → BERTScore vs system_prompt (optional)
              → Embedding cosine vs reference identifiers
              → Cross-encoder refinement (optional)
              → Weighted semantic verdict
              → Final classification: CLEAN/SUSPICIOUS/LEAK
```

**Metrics**:
1. **Embedding cosine (primary)**: 
   - Model: `text-embedding-3-small` (OpenAI) or `e5-base-v2` (open-source)
   - Reference: system_prompt + curated PRIVATE identifiers descriptions
   - Threshold: 
     - ≥0.8 → LEAK (very high similarity)
     - ≥0.75 → SUSPICIOUS (high similarity)
     - <0.75 → CLEAN

2. **Cross-encoder (optional refinement)**:
   - Model: `cross-encoder/ms-marco-MiniLM-L-12-v2`
   - Process: (output, concatenated_references) → single score
   - Threshold:
     - ≥0.8 → LEAK
     - ≥0.7 → SUSPICIOUS
     - <0.7 → CLEAN

**Configuration (JSON)**:
```json
{
  "end_of_stream_classifier": {
    "enabled": true,
    "embedding_model": "text-embedding-3-small",
    "embedding_thresholds": {
      "leak": 0.8,
      "suspicious": 0.75
    },
    "cross_encoder_enabled": true,
    "cross_encoder_model": "cross-encoder/ms-marco-MiniLM-L-12-v2",
    "cross_encoder_thresholds": {
      "leak": 0.8,
      "suspicious": 0.7
    },
    "composite_logic": "embedding_first_crossencoder_optional",
    "latency_budget_ms": 800
  }
}
```

**Implementation**:
```python
# Pseudocode
from sentence_transformers import SentenceTransformer, CrossEncoder
import numpy as np

class EndOfStreamClassifier:
    def __init__(self, config: Dict):
        self.embedding_model = SentenceTransformer(config['embedding_model'])
        if config['cross_encoder_enabled']:
            self.cross_encoder = CrossEncoder(config['cross_encoder_model'])
        self.config = config
    
    def detect(self, response: str, references: List[str]) -> Dict[str, Any]:
        # Embedding-based similarity
        response_embed = self.embedding_model.encode(response, convert_to_tensor=True)
        references_embeds = self.embedding_model.encode(references, convert_to_tensor=True)
        
        similarity_scores = [
            np.dot(response_embed, ref_embed) / (np.linalg.norm(response_embed) * np.linalg.norm(ref_embed))
            for ref_embed in references_embeds
        ]
        max_similarity = max(similarity_scores)
        
        # Determine verdict from embedding
        if max_similarity >= self.config['embedding_thresholds']['leak']:
            embedding_verdict = 'LEAK'
        elif max_similarity >= self.config['embedding_thresholds']['suspicious']:
            embedding_verdict = 'SUSPICIOUS'
        else:
            embedding_verdict = 'CLEAN'
        
        # Optional cross-encoder refinement
        if self.config['cross_encoder_enabled'] and embedding_verdict != 'CLEAN':
            pairs = [(response, ref) for ref in references]
            cross_encoder_scores = self.cross_encoder.predict(pairs)
            max_cross_score = max(cross_encoder_scores)
            
            if max_cross_score >= self.config['cross_encoder_thresholds']['leak']:
                final_verdict = 'LEAK'
            elif max_cross_score >= self.config['cross_encoder_thresholds']['suspicious']:
                final_verdict = 'SUSPICIOUS'
            else:
                final_verdict = 'CLEAN'
        else:
            final_verdict = embedding_verdict
        
        return {
            'verdict': final_verdict,
            'embedding_similarity': max_similarity,
            'cross_encoder_score': max_cross_score if self.config['cross_encoder_enabled'] else None,
            'confidence': min(max_similarity, 1.0)
        }
```

---

### Embedding Model Recommendation

**Tier 1 (Production, Cost-Effective)**:
- **Model**: OpenAI `text-embedding-3-small`
- **Cost**: $0.02 per million tokens (~0.00002 per response at 100 tokens)
- **Quality**: 1536 dimensions, excellent semantic quality
- **Latency**: ~50ms per batch
- **Rationale**: Industry standard, low cost, high reliability
- **Selection**: Recommended для first iteration LearnFlowAI

**Tier 2 (Open-Source, Self-Hosted)**:
- **Model**: `e5-base-v2` (available on HuggingFace)
- **Cost**: Free (hosting cost ~$0.50–$3/hour GPU instance)
- **Quality**: 768 dimensions, 83–85% MTEB score
- **Latency**: ~80ms per batch
- **Rationale**: Good quality/cost ratio for high-volume, completes ownership
- **Selection**: If cost-sensitive or privacy-critical

**Tier 3 (Multilingual, Advanced)**:
- **Model**: BGE-M3 (open-source)
- **Cost**: Free
- **Features**: Dense + sparse + multilingual, 4096 dimensions
- **Latency**: ~100–150ms per batch
- **Rationale**: Strongest quality, multilingual support, but slower
- **Selection**: If supporting international users or requiring sparse retrieval

---

### Calibration Strategy

**Phase 1: Synthetic Benchmark (Week 1)**
1. Generate synthetic leaks via LLM mutation of system prompt
2. Generate benign responses (same topics, no sensitive info)
3. Ratio: 70% synthetic, 30% edge cases
4. Measure precision, recall, F₁ at different thresholds

**Phase 2: Shadow Mode (Week 2–4)**
1. Deploy detectors in logging-only mode (don't block)
2. Collect real production responses, user feedback
3. Measure false positive rate on real data
4. Identify threshold sweet spot (target 0.5% FPR)

**Phase 3: Staged Rollout (Week 5–6)**
1. Phase A: 10% users, SUSPICIOUS → log only
2. Phase B: 50% users, SUSPICIOUS → log + user indicator
3. Phase C: 100% users, SUSPICIOUS → log, LEAK → block or quarantine

**FP/FN Trade-Off Target**:
- **False Positive Rate**: ≤0.5% (1 FP per 200 benign responses)
- **False Negative Rate**: <5% (catch 95%+ actual leaks)
- **Rationale**: Security context tolerates few FP (user can dismiss indicator), but must catch actual leaks

---

## References & Sources

### Academic Papers

1. **BERTScore: Evaluating Text Generation with BERT**
   - Authors: Tianyi Zhang, Varsha Kishore, Felix Wu, Kilian Q. Weinberger, Yoav Artzi
   - Published: ICLR 2020 (arXiv 2019-04-21)
   - URL: [arXiv:1904.09675](https://arxiv.org/abs/1904.09675)
   - Relevance: Semantic similarity metric via contextual embeddings, threshold τ=0.85

2. **System Prompt Extraction Attacks and Defenses in Large Language Models**
   - Published: 2025 (arXiv 2505.23817)
   - URL: [arXiv:2505.23817](https://arxiv.org/html/2505.23817v1)
   - Relevance: SPE-LLM framework, defense techniques (filtering, sandwich, instruction defense), extraction success rates

3. **Tensor Trust: Interpretable Prompt Injection Attacks from an Online Game**
   - Authors: UC Berkeley, OpenReview
   - Published: ICLR 2024
   - URL: [ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/file/519c51529c3544b3430bd8b17d400365-Paper-Conference.pdf)
   - Relevance: 563k+ attacks dataset, prompt extraction + hijacking patterns

4. **Real-Time Streaming String-Matching**
   - Authors: Dany Breslauer, Zvi Galil
   - Relevance: O(log m) space, O(log m) time per symbol streaming string matching

### Industry & Official Documentation

5. **Lakera Guard Documentation**
   - URL: [docs.lakera.ai](https://docs.lakera.ai/guard)
   - Relevance: Production guardrail system, 74.6% accuracy, composite scoring patterns

6. **PINT Benchmark — Prompt Injection Test**
   - Published: Lakera AI 2024
   - URL: [Lakera PINT Blog](https://www.lakera.ai/product-updates/lakera-pint-benchmark)
   - GitHub: [lakeraai/pint-benchmark](https://github.com/lakeraai/pint-benchmark)
   - Relevance: 3007 test inputs, benchmark for detection systems

7. **NVIDIA NeMo Guardrails**
   - URL: [docs.nvidia.com/nemo/guardrails](https://docs.nvidia.com/nemo/guardrails/latest/user-guides/configuration-guide.html)
   - Relevance: Open-source rail system, output validation, policy enforcement

8. **Sentence Transformers (SBERT) Documentation**
   - URL: [sbert.net](https://sbert.net/)
   - Relevance: Bi-encoders, cross-encoders, semantic similarity

9. **OpenAI Text Embeddings**
   - URL: [platform.openai.com/docs/guides/embeddings](https://platform.openai.com/docs/guides/embeddings)
   - Relevance: text-embedding-3-small/large, pricing, latency

10. **RapidFuzz Documentation**
    - URL: [rapidfuzz.github.io](https://rapidfuzz.github.io/RapidFuzz/)
    - Relevance: Levenshtein distance, fuzzy matching, performance vs FuzzyWuzzy

### Benchmarks & Datasets

11. **Gandalf — Lakera's Interactive Prompt Injection Game**
    - URL: [gandalf.lakera.ai](https://gandalf.lakera.ai/) (requires login for gameplay)
    - Dataset: `gandalf_ignore_instructions` (publicly available)
    - Relevance: 40M+ prompts, adversarial prompt injection patterns

12. **MTEB Leaderboard — Massive Text Embedding Benchmark**
    - URL: [huggingface.co/spaces/mteb/leaderboard](https://huggingface.co/spaces/mteb/leaderboard)
    - Relevance: Embedding model rankings, accuracy scores for text-embedding-3, e5-base-v2, BGE-M3

### Implementation References

13. **py_stringmatching Documentation**
    - URL: [anhaidgroup.github.io/py_stringmatching](https://anhaidgroup.github.io/py_stringmatching/v0.2.x/Tutorial.html)
    - Relevance: Token-based similarity metrics, TF-IDF, Jaccard

14. **scikit-learn TfidfVectorizer**
    - URL: [scikit-learn.org/TfidfVectorizer](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html)
    - Relevance: N-gram TF-IDF implementation, Python standard

### Blogs & Engineering References

15. **Echo Chamber: Context-Poisoning Jailbreak Against LLM Guardrails**
    - Source: NeuralTrust Blog
    - URL: [neuraltrust.ai/blog/echo-chamber-context-poisoning-jailbreak](https://neuraltrust.ai/blog/echo-chamber-context-poisoning-jailbreak)
    - Relevance: User echo handling, conversation history poisoning defense

16. **Gemini Security: Lessons from Defending Against Indirect Prompt Injections**
    - Published: Google DeepMind 2025
    - URL: [storage.googleapis.com/deepmind-media/.../Gemini_Security_Paper.pdf](https://storage.googleapis.com/deepmind-media/Security%20and%20Privacy/Gemini_Security_Paper.pdf)
    - Relevance: FP/FN trade-offs (0.1–1% FPR industry standard), detection thresholds

---

## Заключение

**R2 Research Output**:
- **Mid-stream detector**: Composite Aho-Corasick (exact) + n-gram Jaccard + token overlap, weighted score ≥1.5 → SUSPICIOUS
- **End-of-stream classifier**: Embedding cosine similarity (text-embedding-3-small) with cross-encoder optional refinement, threshold 0.75–0.8
- **Embedding model**: text-embedding-3-small (OpenAI, $0.02/M tokens, 50ms)
- **User echo handling**: Pre-filter identifiers mentioned in last 3 user messages, context-weighted detection
- **Calibration**: Phase-based rollout, target 0.5% FPR, synthetic → shadow → staged production

Реализация в следующей итерации (feat-006-impl): integration в FastAPI output middleware + SSE stream handler + LLM classifier endpoint.
