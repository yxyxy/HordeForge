from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class InstructionLayer:
    path: str
    depth: int
    precedence: int
    applies_to: list[str]


def _normalize_target_path(raw_path: str) -> str:
    normalized = raw_path.strip().replace("\\", "/")
    if normalized.startswith("workspace/repo/"):
        normalized = normalized[len("workspace/repo/") :]
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


def _within_workspace(path: Path, workspace_root: Path) -> bool:
    try:
        path.relative_to(workspace_root)
        return True
    except ValueError:
        return False


def _collect_layer_chain_for_target(target_path: str, workspace_root: Path) -> list[str]:
    normalized = _normalize_target_path(target_path)
    if not normalized:
        return []

    resolved = workspace_root / normalized
    current_dir = resolved if resolved.is_dir() else resolved.parent
    if not _within_workspace(current_dir, workspace_root):
        return []

    chain: list[str] = []
    while _within_workspace(current_dir, workspace_root):
        candidate = current_dir / "AGENTS.md"
        if candidate.exists():
            relative = candidate.relative_to(workspace_root).as_posix()
            chain.append(relative)
        if current_dir == workspace_root:
            break
        current_dir = current_dir.parent

    chain.reverse()
    return chain


def resolve_instruction_layers(
    target_files: list[str],
    *,
    workspace_root: Path | None = None,
) -> list[dict[str, Any]]:
    root = (workspace_root or Path.cwd()).resolve()
    layers_by_path: dict[str, InstructionLayer] = {}

    normalized_targets = [
        _normalize_target_path(item)
        for item in target_files
        if isinstance(item, str) and item.strip()
    ]
    normalized_targets = [item for item in normalized_targets if item]

    for target in normalized_targets:
        chain = _collect_layer_chain_for_target(target, root)
        for layer_path in chain:
            depth = len(Path(layer_path).parts)
            existing = layers_by_path.get(layer_path)
            if existing is None:
                layers_by_path[layer_path] = InstructionLayer(
                    path=layer_path,
                    depth=depth,
                    precedence=0,
                    applies_to=[target],
                )
            elif target not in existing.applies_to:
                existing.applies_to.append(target)

    root_layer = root / "AGENTS.md"
    if root_layer.exists():
        root_rel = root_layer.relative_to(root).as_posix()
        if root_rel not in layers_by_path:
            layers_by_path[root_rel] = InstructionLayer(
                path=root_rel,
                depth=len(Path(root_rel).parts),
                precedence=0,
                applies_to=[],
            )

    ordered = sorted(
        layers_by_path.values(),
        key=lambda item: (item.depth, item.path),
    )
    for index, item in enumerate(ordered, start=1):
        item.precedence = index
        item.applies_to.sort()

    return [
        {
            "path": item.path,
            "depth": item.depth,
            "precedence": item.precedence,
            "applies_to": item.applies_to,
        }
        for item in ordered
    ]


def build_instruction_stack(
    base_stack: list[str],
    target_files: list[str],
    *,
    workspace_root: Path | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    layers = resolve_instruction_layers(target_files, workspace_root=workspace_root)
    stack = list(base_stack)
    stack.extend(f"agents_md:{layer['path']}" for layer in layers)
    return stack, layers
