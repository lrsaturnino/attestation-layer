from __future__ import annotations

from pathlib import Path

from nlreq.real_evidence import (
    FINAL_REAL_EVIDENCE_PHASES,
    MILESTONE_NAMES,
    adr_markdown,
    milestone_digest_markdown,
    phase_markdown,
)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    docs = root / "docs"
    adr_dir = docs / "adr"
    docs.mkdir(exist_ok=True)
    adr_dir.mkdir(exist_ok=True)

    for plan in FINAL_REAL_EVIDENCE_PHASES:
        phase_slug = _slug(plan.name)
        (docs / f"phase-{plan.phase}-{phase_slug}.md").write_text(phase_markdown(plan))
        (adr_dir / f"{plan.required_adr:04d}-{phase_slug}.md").write_text(
            adr_markdown(plan)
        )

    for milestone in MILESTONE_NAMES:
        digest_slug = _slug(MILESTONE_NAMES[milestone])
        (docs / f"milestone-group-{milestone}-{digest_slug}-digest.md").write_text(
            milestone_digest_markdown(milestone)
        )
    return 0


def _slug(value: str) -> str:
    return "-".join(
        chunk
        for chunk in "".join(
            char.lower() if char.isalnum() else "-" for char in value
        ).split("-")
        if chunk
    )


if __name__ == "__main__":
    raise SystemExit(main())
