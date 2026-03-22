"""GRAFIK workflows — predefined multi-step pipelines."""

from grafik.workflows.base import WorkflowBase, StepResult
from grafik.workflows.map_localization import MapLocalizationWorkflow
from grafik.workflows.hero_edit import HeroEditWorkflow

WORKFLOWS = {
    "map_localization": MapLocalizationWorkflow,
    "hero_edit": HeroEditWorkflow,
}

__all__ = [
    "WorkflowBase", "StepResult",
    "MapLocalizationWorkflow", "HeroEditWorkflow",
    "WORKFLOWS",
]
