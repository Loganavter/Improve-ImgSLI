"""Unit tests for the slow-path unroll guard in ``devtools.compile_shaders``.

The guard exists because qsb kills its external compiler after a fixed 30 s, so a
shader whose *unrolled* fxc build is minutes long can only be baked out-of-band.
``[loop]`` keeps the loop; semantics are unchanged, so the only thing worth
pinning in a test is that the rewrite marks exactly the loops and touches
nothing else.
"""

from __future__ import annotations

from devtools.compile_shaders import LOOP_HINT, loop_hint_hlsl


def test_marks_for_and_while_loops_and_preserves_indentation() -> None:
    hlsl = "\n".join(
        [
            "void main() {",
            "    for (int j = -6; j <= 6; j++) {",
            "        for (int k = -6; k <= 6; k++) {",
            "            sum += tex.Sample(s, uv);",
            "        }",
            "    }",
            "    while (n < 4) { n++; }",
            "}",
        ]
    )

    hinted, count = loop_hint_hlsl(hlsl)

    assert count == 3
    assert hinted.splitlines() == [
        "void main() {",
        f"    {LOOP_HINT}",
        "    for (int j = -6; j <= 6; j++) {",
        f"        {LOOP_HINT}",
        "        for (int k = -6; k <= 6; k++) {",
        "            sum += tex.Sample(s, uv);",
        "        }",
        "    }",
        f"    {LOOP_HINT}",
        "    while (n < 4) { n++; }",
        "}",
    ]


def test_ignores_lookalikes_and_comments() -> None:
    hlsl = "\n".join(
        [
            "// a note about for (int i = 0; i < 4; i++) loops",
            "float x = format (value);",
            "texture2D(tex, uv);",
            "forwards(value);",
        ]
    )

    hinted, count = loop_hint_hlsl(hlsl)

    assert count == 0
    assert hinted == hlsl + "\n"


def test_only_adds_lines_and_keeps_the_loop_text_intact() -> None:
    hlsl = "for (int i = 0; i < 8; i++)\n{\n    value += i;\n}\n"

    hinted, count = loop_hint_hlsl(hlsl)

    assert count == 1
    assert [line for line in hinted.splitlines() if line != LOOP_HINT] == hlsl.splitlines()
    # No hint line may swallow code: every original line survives verbatim.
    for line in hlsl.splitlines():
        assert line in hinted.splitlines()
