"""WorkflowBase — pipeline runner for multi-step layer operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from grafik.core.project import LayerProject


@dataclass
class StepResult:
    name: str
    success: bool
    data: dict = field(default_factory=dict)
    error: str = ""


class WorkflowBase:
    """Base class for GRAFIK workflows.

    Subclasses define steps as methods and register them in `setup()`.
    The runner executes steps sequentially, passing context between them.
    """

    name: str = "base"
    description: str = ""

    def __init__(self, project: LayerProject, project_dir: Path):
        self.project = project
        self.project_dir = project_dir
        self.steps: list[tuple[str, Callable]] = []
        self.context: dict[str, Any] = {}
        self.results: list[StepResult] = []
        self.setup()

    def setup(self) -> None:
        """Override to register steps via self.add_step()."""
        pass

    def add_step(self, name: str, fn: Callable) -> None:
        self.steps.append((name, fn))

    def run(self, **kwargs) -> list[StepResult]:
        """Execute all steps in order. Stops on first failure."""
        self.context.update(kwargs)
        self.results = []

        for name, fn in self.steps:
            try:
                result_data = fn(self.context)
                if isinstance(result_data, dict):
                    self.context.update(result_data)
                self.results.append(StepResult(name=name, success=True, data=result_data or {}))
            except Exception as e:
                self.results.append(StepResult(name=name, success=False, error=str(e)))
                break

        # Save project after workflow
        self.project.save(self.project_dir)
        return self.results

    @property
    def succeeded(self) -> bool:
        return all(r.success for r in self.results)
