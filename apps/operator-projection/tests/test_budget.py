import io
import tokenize
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "operator_projection"
SKIP = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER}
RENDERERS = {"render_html.py", "render_text.py"}
EVALUATORS = {"evaluators.py"}
# generator 800 -> 840 (v0.1.1): the project-1 pick-up mapping, repo-scoped boundary reads and the authority read timeout.
# generator 840 -> 880 (v0.2.0): /freshz and the document archive (P2); the redacted remote leg was withdrawn in v0.2.1.
BUDGET = {"generator": 880, "renderers": 300, "evaluators": 100}


def code_lines(path: Path) -> int:
    tokens = tokenize.generate_tokens(io.StringIO(path.read_text()).readline)
    lines: set[int] = set()
    for token in tokens:
        if token.type not in SKIP:
            lines.update(range(token.start[0], token.end[0] + 1))
    return len(lines)


def group(name: str) -> str:
    return "renderers" if name in RENDERERS else "evaluators" if name in EVALUATORS else "generator"


def counts() -> dict[str, int]:
    totals = dict.fromkeys(BUDGET, 0)
    for path in PACKAGE.glob("*.py"):
        totals[group(path.name)] += code_lines(path)
    return totals


def test_line_budget():
    totals = counts()
    assert all(totals[g] <= BUDGET[g] for g in BUDGET), totals


def test_counter_ignores_blanks_and_comments(tmp_path):
    source = tmp_path / "x.py"
    source.write_text("# c\n\nx = 1  # c\ny = (\n  2)\n")
    assert code_lines(source) == 3


if __name__ == "__main__":
    print(counts())
