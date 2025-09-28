def build_rank_order(rows, starting_rank: int, mode: str) -> list[int]:
    max_rank = max(r.ranking for r in rows)
    order = list(range(1, max_rank + 1))
    if mode == "count_up":
        return [r for r in order if r >= starting_rank]
    if mode == "count_down":
        return [r for r in order if r <= starting_rank][::-1]
    # random
    import random
    out = [r for r in order if r >= starting_rank]
    random.shuffle(out)
    return out
