# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
import time
from filter import fetch_all_collabs_brands_nodes

collected = fetch_all_collabs_brands_nodes(
    base_url='https://www.dovetale.com',
    delay_ms=300,
    log_fn=lambda m: print(f"[LOG] {m}"),
)
print(f'\n=== TONG BRAND TU API: {len(collected)} ===')
