"""Focused contracts for coarse program-grid region merging."""

from vql.adopt.program_grid import merge_grid_colors


def test_merge_grid_colors_merges_maximal_uniform_rectangle() -> None:
    red = (255, 0, 0)
    blue = (0, 0, 255)

    regions = merge_grid_colors(
        [[red, red, blue], [red, red, blue], [blue, blue, blue]],
        grid=3,
    )

    assert regions == [
        (0, 0, 2, 2, red),
        (2, 0, 1, 3, blue),
        (0, 2, 2, 1, blue),
    ]
