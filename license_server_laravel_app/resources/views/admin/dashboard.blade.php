<!doctype html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Quản trị key bản quyền</title>
    <style>
        body { font-family: "Segoe UI", Arial, sans-serif; background: #f4f7fb; margin: 0; color: #1e293b; }
        .wrap { max-width: 1220px; margin: 18px auto; padding: 0 14px; }
        .bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        h1 { margin: 0; font-size: 22px; color: #0f172a; }
        h3 { margin: 0 0 12px; font-size: 17px; color: #111827; }
        .card { background: #fff; border: 1px solid #dbe2ee; border-radius: 10px; padding: 14px; margin-bottom: 14px; box-shadow: 0 6px 20px rgba(31, 41, 55, 0.04); }
        .grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
        .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
        label { display: block; font-size: 12px; color: #475569; margin-bottom: 4px; font-weight: 600; }
        input, textarea, select { width: 100%; padding: 8px; border: 1px solid #bfd0ea; border-radius: 7px; box-sizing: border-box; background: #fff; }
        textarea { min-height: 120px; resize: vertical; }
        input:focus, textarea:focus, select:focus { outline: none; border-color: #3b82f6; box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15); }
        .btn { border: 0; border-radius: 8px; padding: 8px 12px; cursor: pointer; font-weight: 700; font-size: 13px; color: #fff; }
        .btn-primary { background: #2563eb; }
        .btn-primary:hover { background: #1d4ed8; }
        .btn-warn { background: #d97706; }
        .btn-warn:hover { background: #b45309; }
        .btn-danger { background: #dc2626; }
        .btn-danger:hover { background: #b91c1c; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th, td { border-bottom: 1px solid #e5ecf7; text-align: left; padding: 8px; vertical-align: top; }
        th { background: #f8fbff; color: #334155; font-weight: 700; }
        .ok { color: #15803d; font-weight: 700; }
        .bad { color: #b91c1c; font-weight: 700; }
        .msg { margin: 8px 0; padding: 9px 10px; border-radius: 8px; font-weight: 600; }
        .msg.ok { background: #e7f7ec; border: 1px solid #b7e4c7; color: #166534; }
        .muted { color: #64748b; font-size: 12px; }
        .pagination { margin-top: 10px; display: flex; justify-content: flex-end; gap: 6px; align-items: center; }
        .pg-btn { font-size: 12px; padding: 5px 8px; border-radius: 6px; border: 1px solid #c8d5ea; background: #fff; color: #334155; text-decoration: none; }
        .pg-btn:hover { background: #eef4ff; }
        .pg-btn.disabled { opacity: 0.5; pointer-events: none; }
        code { font-size: 12px; background: #f3f7ff; padding: 2px 4px; border-radius: 5px; }
        .search-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
        .search-row input[type="search"] { flex: 1; min-width: 180px; max-width: 420px; }
    </style>
</head>
<body>
<div class="wrap">
    <div class="bar">
        <h1>Quản trị key bản quyền</h1>
        <form method="post" action="{{ route('admin.logout') }}">
            @csrf
            <button type="submit" class="btn btn-warn">Đăng xuất</button>
        </form>
    </div>

    @if(session('success'))
        <div class="msg ok">{{ session('success') }}</div>
    @endif

    <div class="card">
        <h3>Thêm hoặc cập nhật nhanh 1 key</h3>
        <form method="post" action="{{ route('admin.keys.store') }}">
            @csrf
            <div class="grid">
                <div>
                    <label>Key bản quyền</label>
                    <div style="display:flex; gap:6px; align-items:center;">
                        <input id="quick-license-key" name="license_key" required>
                        <button id="btn-generate-key" type="button" class="btn btn-warn">Tạo</button>
                    </div>
                </div>
                <div><label>Giới hạn record/ngày</label><input name="daily_limit" type="number" min="1" value="500"></div>
                <div><label>Số máy tối đa</label><input name="max_machines" type="number" min="1" value="2"></div>
                <div><label>Hạn dùng</label><input name="expires_at" type="datetime-local"></div>
            </div>
            <div style="margin-top:8px;">
                <label>Ghi chú</label><input name="notes">
            </div>
            <div style="margin-top:10px;"><button type="submit" class="btn btn-primary">Lưu key</button></div>
        </form>
    </div>

    <div class="card">
        <h3>Activation đang hoạt động</h3>
        <div class="muted" style="margin-bottom:8px;">Usage theo ngày VN ({{ $usageDayVn }})</div>
        <form method="get" action="{{ route('admin.dashboard') }}" class="search-row">
            <input type="hidden" name="keys_q" value="{{ request('keys_q') }}">
            <input type="search" name="activation_q" value="{{ request('activation_q') }}" placeholder="Tìm theo mã activation, mã máy, key hoặc chú thích key…" autocomplete="off">
            <button type="submit" class="btn btn-primary">Tìm</button>
            @if(request()->filled('activation_q'))
                <a class="pg-btn" href="{{ route('admin.dashboard', array_filter(['keys_q' => request('keys_q')])) }}">Xóa lọc activation</a>
            @endif
        </form>
        <table>
            <thead>
            <tr>
                <th>ID</th><th>Mã activation</th><th>Key</th><th>Mã máy</th><th>Đã dùng hôm nay</th><th>Kích hoạt lúc</th><th>Lần cuối online</th><th>Chú thích</th><th>Thao tác</th>
            </tr>
            </thead>
            <tbody>
            @foreach($activations as $a)
                <tr>
                    <td>{{ $a->id }}</td>
                    <td>{{ $a->activation_id }}</td>
                    <td>{{ $a->licenseKey?->license_key }}</td>
                    <td><code>{{ $a->machine_fingerprint }}</code></td>
                    <td>{{ (int) (($a->dailyUsages->first()->used_total ?? 0)) }}</td>
                    <td>{{ $a->activated_at }}</td>
                    <td>{{ $a->last_seen_at }}</td>
                    <td>
                        @php($keyNotes = trim((string) ($a->licenseKey?->notes ?? '')))
                        {{ $keyNotes !== '' ? $keyNotes : (data_get($a->meta, 'notes') ?: '—') }}
                    </td>
                    <td>
                        <form method="post" action="{{ route('admin.activations.revoke', ['id' => $a->id]) }}" onsubmit="return confirm('Bạn có chắc muốn thu hồi activation này?');">
                            @csrf
                            <button class="btn btn-danger" type="submit">Thu hồi</button>
                        </form>
                    </td>
                </tr>
            @endforeach
            </tbody>
        </table>
        <div class="pagination">
            <a class="pg-btn {{ $activations->onFirstPage() ? 'disabled' : '' }}" href="{{ $activations->previousPageUrl() ?: '#' }}">← Trước</a>
            <span class="muted">Trang {{ $activations->currentPage() }}/{{ $activations->lastPage() }}</span>
            <a class="pg-btn {{ $activations->hasMorePages() ? '' : 'disabled' }}" href="{{ $activations->nextPageUrl() ?: '#' }}">Sau →</a>
        </div>
    </div>

    <div class="card">
        <h3>Danh sách key</h3>
        <form method="get" action="{{ route('admin.dashboard') }}" class="search-row">
            <input type="hidden" name="activation_q" value="{{ request('activation_q') }}">
            <input type="search" name="keys_q" value="{{ request('keys_q') }}" placeholder="Tìm theo key, key_hint hoặc chú thích…" autocomplete="off">
            <button type="submit" class="btn btn-primary">Tìm</button>
            @if(request()->filled('keys_q'))
                <a class="pg-btn" href="{{ route('admin.dashboard', array_filter(['activation_q' => request('activation_q')])) }}">Xóa lọc key</a>
            @endif
        </form>
        <table>
            <thead>
            <tr>
                <th>ID</th><th>Key</th><th>Trạng thái</th><th>Máy đang active</th><th>Record/ngày</th><th>Số máy tối đa</th><th>Hạn dùng</th><th>Cập nhật</th>
            </tr>
            </thead>
            <tbody>
            @foreach($keys as $k)
                <tr>
                    <td>{{ $k->id }}</td>
                    <td><strong>{{ $k->license_key }}</strong><div class="muted">{{ $k->notes }}</div></td>
                    <td class="{{ $k->status === 'active' ? 'ok' : 'bad' }}">{{ $k->status === 'active' ? 'hoạt động' : 'khóa' }}</td>
                    <td>{{ $k->active_activations_count }}</td>
                    <td>{{ $k->daily_limit ?? '-' }}</td>
                    <td>{{ $k->max_machines ?? '-' }}</td>
                    <td>{{ $k->expires_at ?? '-' }}</td>
                    <td>
                        <form method="post" action="{{ route('admin.keys.update', ['id' => $k->id]) }}" onsubmit="return confirm('Xác nhận cập nhật key này?');">
                            @csrf
                            <div class="grid-2">
                                <select name="status">
                                    <option value="active" @selected($k->status==='active')>hoạt động</option>
                                    <option value="blocked" @selected($k->status==='blocked')>khóa</option>
                                </select>
                                <input name="daily_limit" type="number" min="1" value="{{ $k->daily_limit }}">
                            </div>
                            <div class="grid-2" style="margin-top:6px;">
                                <input name="max_machines" type="number" min="1" value="{{ $k->max_machines }}">
                                <input name="expires_at" type="datetime-local" value="{{ $k->expires_at ? \Illuminate\Support\Carbon::parse($k->expires_at)->format('Y-m-d\TH:i') : '' }}">
                            </div>
                            <div style="margin-top:6px;"><input name="notes" value="{{ $k->notes }}"></div>
                            <div style="margin-top:6px;"><button type="submit" class="btn btn-primary">Cập nhật</button></div>
                        </form>
                    </td>
                </tr>
            @endforeach
            </tbody>
        </table>
        <div class="pagination">
            <a class="pg-btn {{ $keys->onFirstPage() ? 'disabled' : '' }}" href="{{ $keys->previousPageUrl() ?: '#' }}">← Trước</a>
            <span class="muted">Trang {{ $keys->currentPage() }}/{{ $keys->lastPage() }}</span>
            <a class="pg-btn {{ $keys->hasMorePages() ? '' : 'disabled' }}" href="{{ $keys->nextPageUrl() ?: '#' }}">Sau →</a>
        </div>
    </div>
</div>
<script>
    (function () {
        var input = document.getElementById('quick-license-key');
        var btn = document.getElementById('btn-generate-key');
        if (!input || !btn) return;

        function randomBlock(len) {
            var chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
            var out = '';
            for (var i = 0; i < len; i += 1) {
                out += chars.charAt(Math.floor(Math.random() * chars.length));
            }
            return out;
        }

        btn.addEventListener('click', function () {
            input.value = 'AFL1-' + randomBlock(4) + '-' + randomBlock(4) + '-' + randomBlock(4);
            input.focus();
        });
    })();
</script>
</body>
</html>
