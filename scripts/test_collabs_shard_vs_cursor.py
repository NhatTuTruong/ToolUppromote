#!/usr/bin/env python3
"""So sánh brand cursor Discovery vs shard (trùng / brand mới)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import filter as core  # noqa: E402


def fetch_all_cursor(base_url: str, page_size: int = 12, delay_ms: int = 50) -> list[dict]:
    after = None
    out: list[dict] = []
    page = 0
    while True:
        page += 1
        body = core.fetch_collabs_page(base_url, page_size, after=after)
        search = core._collabs_brands_search(body)
        nodes = search.get("nodes") or []
        if not isinstance(nodes, list) or not nodes:
            break
        out.extend([n for n in nodes if isinstance(n, dict)])
        info = search.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            break
        after = info.get("endCursor")
        if not after:
            break
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)
        if page % 20 == 0:
            print(f"  cursor: trang {page}, tổng {len(out)} brand", flush=True)
    return out


def brand_ids(nodes: list[dict]) -> set[str]:
    return {str(n.get("id") or "").strip() for n in nodes if n.get("id")}


def main() -> int:
    core.enforce_fixed_fetch_defaults()
    base_url = (os.getenv("COLLABS_API_URL") or "").strip()
    if not base_url:
        print("Thiếu COLLABS_API_URL trong .env")
        return 1

    page_size = core.DEFAULT_COLLABS_LIMIT
    print("=== 1) Lấy toàn bộ brand qua cursor (không searchQuery) ===")
    t0 = time.time()
    cursor_nodes = fetch_all_cursor(base_url, page_size=page_size)
    cursor_ids = brand_ids(cursor_nodes)
    print(
        f"  Xong: {len(cursor_nodes)} brand, {len(cursor_ids)} id duy nhất, "
        f"~{len(cursor_nodes) // page_size} trang API, {time.time() - t0:.1f}s"
    )

    print("\n=== 2) Shard fill (exclude id cursor) — brand MỚI so với cursor ===")
    t1 = time.time()
    shard_new = core.fetch_collabs_brands_shard_fill(
        base_url,
        product_categories=None,
        exclude_ids=cursor_ids,
        max_count=300,
        delay_ms=50,
        log_fn=lambda m: print(f"  {m}", flush=True),
    )
    shard_new_ids = brand_ids(shard_new)
    overlap_with_cursor = shard_new_ids & cursor_ids
    print(
        f"  Shard (đã loại cursor): {len(shard_new)} brand, "
        f"{len(shard_new_ids)} id, trùng cursor: {len(overlap_with_cursor)}, "
        f"{time.time() - t1:.1f}s"
    )

    print("\n=== 3) Mẫu shard prefix 'a' (không exclude) — % trùng cursor ===")
    t2 = time.time()
    prefix_a = core._collabs_paginate_shard(
        base_url, page_size, None, "a", delay_ms=50, max_pages=120
    )
    a_ids = brand_ids(prefix_a)
    in_cursor = len(a_ids & cursor_ids)
    only_a = len(a_ids - cursor_ids)
    print(
        f"  Shard 'a': {len(prefix_a)} brand, trùng cursor: {in_cursor}, "
        f"chỉ có trong shard 'a': {only_a}, {time.time() - t2:.1f}s"
    )

    print("\n=== 4) Vài prefix đầu (a,b,c) gộp — id mới ngoài cursor ===")
    extra_union: set[str] = set()
    for prefix in ("a", "b", "c"):
        nodes = core._collabs_paginate_shard(
            base_url, page_size, None, prefix, delay_ms=30, max_pages=30
        )
        extra_union |= brand_ids(nodes)
    only_outside_cursor = extra_union - cursor_ids
    print(
        f"  Union a+b+c (giới hạn 30 trang/prefix): {len(extra_union)} id, "
        f"mới ngoài cursor: {len(only_outside_cursor)}"
    )

    print("\n=== KẾT LUẬN ===")
    if len(overlap_with_cursor) == 0 and len(shard_new_ids) > 0:
        print("Shard (có exclude) lấy được brand KHÁC cursor — không lặp id đã có.")
    elif len(shard_new_ids) == 0:
        print("Shard không tìm thêm brand mới (có thể đã hết hoặc rate limit).")
    else:
        print(f"CẢNH BÁO: {len(overlap_with_cursor)} id shard vẫn trùng cursor dù đã exclude.")

    if len(only_outside_cursor) > 0:
        print(
            f"Có ít nhất {len(only_outside_cursor)} brand trong shard mà KHÔNG nằm trong "
            f"{len(cursor_ids)} brand cursor."
        )
    else:
        print("Mẫu a+b+c chưa thấy brand ngoài cursor (có thể cần chạy đủ alphabet).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
