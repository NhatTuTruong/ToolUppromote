<!doctype html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <title>Quản trị key bản quyền</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{ asset('css/admin-theme.css') }}">
</head>
<body class="admin-body">
<div class="admin-wrap">
    <header class="admin-topbar">
        <div>
            <h1 class="admin-topbar-title">Quản trị key bản quyền</h1>
            <p class="admin-topbar-sub">Token Refersion · Key · Activation</p>
        </div>
        <form method="post" action="{{ route('admin.logout') }}">
            @csrf
            <button type="submit" class="btn btn-warn">Đăng xuất</button>
        </form>
    </header>

    @if(session('success'))
        <div class="admin-msg ok">{{ session('success') }}</div>
    @endif

    <div class="admin-tabs" role="tablist" aria-label="Tabs quản trị">
        <button type="button" class="tab-btn active" data-tab-target="tab-refersion" role="tab" aria-controls="tab-refersion" aria-selected="true">Token Refersion</button>
        <button type="button" class="tab-btn" data-tab-target="tab-quick-key" role="tab" aria-controls="tab-quick-key" aria-selected="false">Thêm/Cập nhật key</button>
        <button type="button" class="tab-btn" data-tab-target="tab-activations" role="tab" aria-controls="tab-activations" aria-selected="false">Activation</button>
        <button type="button" class="tab-btn" data-tab-target="tab-keys" role="tab" aria-controls="tab-keys" aria-selected="false">Danh sách key</button>
    </div>

    <div id="tab-refersion" class="tab-panel active">
    <div class="card">
        <h3>Cập nhật Token Refersion</h3>
        <form method="post" action="{{ route('admin.settings.refersion_token') }}">
            @csrf
            <div>
                <label class="field-label" for="refersion_token">Refersion token</label>
                <input id="refersion_token" name="refersion_token" type="text" value="{{ $refersionToken }}" autocomplete="off" placeholder="Nhập token Refersion">
            </div>
            <p class="muted" style="margin-top:10px;">
                Khi lưu, app client đã kích hoạt key sẽ tự đồng bộ token này vào phần Cài đặt.
            </p>
            <div style="margin-top:14px;">
                <button type="submit" class="btn btn-primary">Lưu token</button>
            </div>
        </form>
    </div>
    </div>

    <div id="tab-quick-key" class="tab-panel">
    <div class="card">
        <h3>Thêm hoặc cập nhật nhanh 1 key</h3>
        <form method="post" action="{{ route('admin.keys.store') }}">
            @csrf
            <div class="grid">
                <div>
                    <label class="field-label" for="quick-license-key">Key bản quyền</label>
                    <div class="flex-input-row">
                        <input id="quick-license-key" name="license_key" required>
                        <button id="btn-generate-key" type="button" class="btn btn-warn" style="flex-shrink:0;">Tạo</button>
                    </div>
                </div>
                <div><label class="field-label">Giới hạn record/ngày</label><input name="daily_limit" type="number" min="1" value="500"></div>
                <div><label class="field-label">Số máy tối đa</label><input name="max_machines" type="number" min="1" value="2"></div>
                <div><label class="field-label">Hạn dùng</label><input name="expires_at" type="datetime-local"></div>
            </div>
            <div style="margin-top:12px;">
                <label class="field-label">Ghi chú</label><input name="notes">
            </div>
            <div style="margin-top:12px;">
                <label class="field-label">Net được phép (theo key)</label>
                <div class="check-row">
                    <label><input type="checkbox" name="allowed_sources[]" value="uppromote" checked> Uppromote</label>
                    <label><input type="checkbox" name="allowed_sources[]" value="goaffpro" checked> Goaffpro</label>
                    <label><input type="checkbox" name="allowed_sources[]" value="refersion"> Refersion</label>
                    <label><input type="checkbox" name="allowed_sources[]" value="collabs"> Shopify Collabs</label>
                </div>
            </div>
            <div style="margin-top:12px;">
                <label class="field-label">Auto Apply Collabs (Apply Collab)</label>
                <div class="check-row">
                    <label><input type="checkbox" name="allow_auto_apply_collabs" value="1" checked> Apply Collab</label>
                </div>
                <p class="muted" style="margin-top:6px;">Tắt mục này sẽ ẩn các nút/chức năng Auto Apply Collabs trong app.</p>
            </div>
            <div style="margin-top:14px;"><button type="submit" class="btn btn-primary">Lưu key</button></div>
        </form>
    </div>
    </div>

    <div id="tab-activations" class="tab-panel">
    <div class="card">
        <h3>Activation đang hoạt động</h3>
        <p class="muted" style="margin-bottom:10px;">Usage theo ngày VN ({{ $usageDayVn }})</p>
        <form method="get" action="{{ route('admin.dashboard') }}" class="search-row">
            <input type="hidden" name="keys_q" value="{{ request('keys_q') }}">
            <input type="search" name="activation_q" value="{{ request('activation_q') }}" placeholder="Tìm theo mã activation, mã máy, key hoặc chú thích key…" autocomplete="off">
            <button type="submit" class="btn btn-primary">Tìm</button>
            @if(request()->filled('activation_q'))
                <a class="pg-btn" href="{{ route('admin.dashboard', array_filter(['keys_q' => request('keys_q')])) }}">Xóa lọc activation</a>
            @endif
        </form>
        <div class="table-scroll">
        <table class="data-table">
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
        </div>
        <div class="pagination">
            <a class="pg-btn {{ $activations->onFirstPage() ? 'disabled' : '' }}" href="{{ $activations->previousPageUrl() ?: '#' }}">← Trước</a>
            <span class="muted">Trang {{ $activations->currentPage() }}/{{ $activations->lastPage() }}</span>
            <a class="pg-btn {{ $activations->hasMorePages() ? '' : 'disabled' }}" href="{{ $activations->nextPageUrl() ?: '#' }}">Sau →</a>
        </div>
    </div>
    </div>

    <div id="tab-keys" class="tab-panel">
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
        <div class="table-scroll">
        <table class="data-table">
            <thead>
            <tr>
                <th>ID</th><th>Key</th><th>Trạng thái</th><th>Máy đang active</th><th>Record/ngày</th><th>Số máy tối đa</th><th>Net</th><th>Hạn dùng</th><th>Cập nhật</th>
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
                    <td>{{ implode(', ', $k->normalizedAllowedSources()) }}</td>
                    <td>{{ $k->expires_at ?? '-' }}</td>
                    <td>
                        <form method="post" action="{{ route('admin.keys.update', ['id' => $k->id]) }}" onsubmit="return confirm('Xác nhận cập nhật key này?');">
                            @csrf
                            @php($allowed = $k->normalizedAllowedSources())
                            <div class="grid-2">
                                <select name="status">
                                    <option value="active" @selected($k->status==='active')>hoạt động</option>
                                    <option value="blocked" @selected($k->status==='blocked')>khóa</option>
                                </select>
                                <input name="daily_limit" type="number" min="1" value="{{ $k->daily_limit }}">
                            </div>
                            <div class="grid-2" style="margin-top:8px;">
                                <input name="max_machines" type="number" min="1" value="{{ $k->max_machines }}">
                                <input name="expires_at" type="datetime-local" value="{{ $k->expires_at ? \Illuminate\Support\Carbon::parse($k->expires_at)->format('Y-m-d\TH:i') : '' }}">
                            </div>
                            <div style="margin-top:8px;">
                                <div class="check-row">
                                    <label><input type="checkbox" name="allowed_sources[]" value="uppromote" @checked(in_array('uppromote', $allowed, true))> Uppromote</label>
                                    <label><input type="checkbox" name="allowed_sources[]" value="goaffpro" @checked(in_array('goaffpro', $allowed, true))> Goaffpro</label>
                                    <label><input type="checkbox" name="allowed_sources[]" value="refersion" @checked(in_array('refersion', $allowed, true))> Refersion</label>
                                    <label><input type="checkbox" name="allowed_sources[]" value="collabs" @checked(in_array('collabs', $allowed, true))> Shopify Collabs</label>
                                </div>
                            </div>
                            <div style="margin-top:8px;">
                                <div class="check-row">
                                    <label><input type="checkbox" name="allow_auto_apply_collabs" value="1" @checked((bool) $k->allow_auto_apply_collabs)> Apply Collab</label>
                                </div>
                            </div>
                            <div style="margin-top:8px;"><input name="notes" value="{{ $k->notes }}"></div>
                            <div class="stack-btns" style="margin-top:10px;">
                                <button type="submit" class="btn btn-primary">Cập nhật</button>
                            </div>
                        </form>
                        <form method="post" action="{{ route('admin.keys.delete', ['id' => $k->id]) }}" onsubmit="return confirm('Bạn có chắc muốn xóa key {{ $k->license_key }}? Toàn bộ activation và usage liên quan sẽ bị xóa.');" style="margin-top:8px;">
                            @csrf
                            <button type="submit" class="btn btn-danger">Xóa</button>
                        </form>
                    </td>
                </tr>
            @endforeach
            </tbody>
        </table>
        </div>
        <div class="pagination">
            <a class="pg-btn {{ $keys->onFirstPage() ? 'disabled' : '' }}" href="{{ $keys->previousPageUrl() ?: '#' }}">← Trước</a>
            <span class="muted">Trang {{ $keys->currentPage() }}/{{ $keys->lastPage() }}</span>
            <a class="pg-btn {{ $keys->hasMorePages() ? '' : 'disabled' }}" href="{{ $keys->nextPageUrl() ?: '#' }}">Sau →</a>
        </div>
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
<script>
    (function () {
        var btns = Array.prototype.slice.call(document.querySelectorAll('.tab-btn[data-tab-target]'));
        var panels = Array.prototype.slice.call(document.querySelectorAll('.tab-panel'));
        if (!btns.length || !panels.length) return;

        function setActive(tabId, pushHash) {
            btns.forEach(function (b) {
                var isActive = b.getAttribute('data-tab-target') === tabId;
                b.classList.toggle('active', isActive);
                b.setAttribute('aria-selected', isActive ? 'true' : 'false');
            });
            panels.forEach(function (p) {
                p.classList.toggle('active', p.id === tabId);
            });
            if (pushHash) {
                try { window.location.hash = tabId; } catch (_) {}
            }
        }

        btns.forEach(function (b) {
            b.addEventListener('click', function () {
                var id = b.getAttribute('data-tab-target') || '';
                if (!id) return;
                setActive(id, true);
            });
        });

        var fromHash = (window.location.hash || '').replace('#', '').trim();
        if (fromHash && document.getElementById(fromHash)) {
            setActive(fromHash, false);
        }
    })();
</script>
</body>
</html>
