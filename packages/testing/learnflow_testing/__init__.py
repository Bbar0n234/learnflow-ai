"""Shared test harness for LearnFlow AI.

Import the submodules you need directly — the package does not eagerly import
them, so the ``pytest11`` plugin loads without pulling in backend-only modules
(``app.*``) before the package source roots are on ``sys.path``:

* :mod:`learnflow_testing.fakes` — LLM/guard fakes for the model seam.
* :mod:`learnflow_testing.factories` — factory_boy factories for backend models.
* :mod:`learnflow_testing.db` — testcontainers + alembic + transactional rollback.
* :mod:`learnflow_testing.sse` — SSE collection helpers.
* :mod:`learnflow_testing.plugin` — cross-project pytest fixtures (entry point).
"""
