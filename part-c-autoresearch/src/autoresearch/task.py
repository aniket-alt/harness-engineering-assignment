"""Task definition: what the agent may edit, what it may not, and how a run is scored."""
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Guard:
    max_bytes: int = 30_000
    forbidden_imports: tuple[str, ...] = ()
    forbidden_names: tuple[str, ...] = ()
    forbidden_attrs: tuple[str, ...] = ()
    forbidden_text: tuple[str, ...] = ()
    required_calls: tuple[str, ...] = ()
    # module name -> the only attributes a candidate may touch on it (and never assign to)
    module_allowlist: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class Task:
    root: Path
    name: str
    editable: Path
    protected: tuple[Path, ...]
    command: tuple[str, ...]
    budget_seconds: float
    timeout_seconds: float
    metric: str = "score"
    direction: str = "min"
    min_delta: float = 0.0
    baseline_runs: int = 1   # measure the starting file this many times; the best run is the bar
    confirm: bool = False    # re-run a would-be improvement; keep only if its worse run still wins
    guard: Guard = field(default_factory=Guard)

    def improves(self, new: float, best: float) -> bool:
        """Progress means beating the best by MORE than min_delta (set above the run-to-run noise),
        so a lucky run or a tie cannot ratchet the score."""
        if self.direction == "min":
            return new < best - self.min_delta
        return new > best + self.min_delta

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    @classmethod
    def from_toml(cls, path: str | Path) -> "Task":
        path = Path(path).resolve()
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        t, g = data["task"], data.get("guard", {})
        direction = t.get("direction", "min")
        if direction not in ("min", "max"):
            raise ValueError(f"direction must be 'min' or 'max', got {direction!r}")
        root = path.parent
        guard = Guard(
            max_bytes=g.get("max_bytes", 30_000),
            **{k: tuple(g.get(k, ())) for k in (
                "forbidden_imports", "forbidden_names", "forbidden_attrs",
                "forbidden_text", "required_calls")},
            module_allowlist={m: tuple(a) for m, a in g.get("module_allowlist", {}).items()},
        )
        return cls(
            root=root,
            name=t["name"],
            editable=root / t["editable"],
            protected=tuple(root / p for p in t.get("protected", ())),
            command=tuple(t["command"]),
            budget_seconds=float(t["budget_seconds"]),
            timeout_seconds=float(t["timeout_seconds"]),
            metric=t.get("metric", "score"),
            direction=direction,
            min_delta=float(t.get("min_delta", 0.0)),
            baseline_runs=int(t.get("baseline_runs", 1)),
            confirm=bool(t.get("confirm", False)),
            guard=guard,
        )
