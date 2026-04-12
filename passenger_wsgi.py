"""
Entry WSGI cho hosting dùng Phusion Passenger hoặc cPanel « Setup Python App ».

Cách dùng:
  • Upload toàn bộ project lên server (có `license_guard.py`, thư mục `license_server/`, file `.env`).
  • Trong panel, Application root = thư mục chứa file này.
  • Startup / Application file = `passenger_wsgi.py` (chính file này).

Passenger sẽ import biến `application` — không cần nginx trên máy bạn nếu hosting đã phục vụ HTTPS.

Lưu ý: cPanel đôi khi tự tạo `passenger_wsgi.py` có đoạn chỉ tới virtualenv — giữ đoạn đó
và thêm `sys.path` + dòng `from license_server.app import app as application` nếu cần.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from license_server.app import app as application
