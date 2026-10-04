"""Which assets sit either side of one in its project's grid.

Pure on purpose: the order comes from the query, and the edges (first, last,
an asset the grid does not list) are the part worth testing without a database.
"""


def neighbors_of(ordered_ids: list, current_id) -> dict:
    """prev/next around `current_id` in grid order (newest first).

    `position` is 1-based. An asset that is not in the list (a failed upload
    opened by URL) gets no neighbours and position 0, rather than borrowed ones.
    """
    try:
        i = ordered_ids.index(current_id)
    except ValueError:
        return {"prev_id": None, "next_id": None, "position": 0, "total": len(ordered_ids)}
    return {
        "prev_id": ordered_ids[i - 1] if i > 0 else None,
        "next_id": ordered_ids[i + 1] if i + 1 < len(ordered_ids) else None,
        "position": i + 1,
        "total": len(ordered_ids),
    }
