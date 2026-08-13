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
            <p class="admin-topbar-sub">Token Refersion · Thêm/Cập nhật key · Activation · Danh sách key</p>
        </div>
        <form method="post" action="{{ route('admin.logout') }}">
            @csrf
            <button type="submit" class="btn btn-warn">Đăng xuất</button>
        </form>
    </header>

    @if(session('success'))
        <div class="admin-msg ok" role="status">{{ session('success') }}</div>
    @endif

    @php($activeTab = $activeTab ?? 'tab-refersion')
    <div class="admin-tabs" role="tablist" aria-label="Tabs quản trị">
        <button type="button" class="tab-btn {{ $activeTab === 'tab-refersion' ? 'active' : '' }}" data-tab-target="tab-refersion" role="tab" aria-controls="tab-refersion" aria-selected="{{ $activeTab === 'tab-refersion' ? 'true' : 'false' }}">Token Refersion</button>
        <button type="button" class="tab-btn {{ $activeTab === 'tab-collabs' ? 'active' : '' }}" data-tab-target="tab-collabs" role="tab" aria-controls="tab-collabs" aria-selected="{{ $activeTab === 'tab-collabs' ? 'true' : 'false' }}">Collabs session</button>
        <button type="button" class="tab-btn {{ $activeTab === 'tab-quick-key' ? 'active' : '' }}" data-tab-target="tab-quick-key" role="tab" aria-controls="tab-quick-key" aria-selected="{{ $activeTab === 'tab-quick-key' ? 'true' : 'false' }}">Thêm / Cập nhật key</button>
        <button type="button" class="tab-btn {{ $activeTab === 'tab-activations' ? 'active' : '' }}" data-tab-target="tab-activations" role="tab" aria-controls="tab-activations" aria-selected="{{ $activeTab === 'tab-activations' ? 'true' : 'false' }}">Activation</button>
        <button type="button" class="tab-btn {{ $activeTab === 'tab-keys' ? 'active' : '' }}" data-tab-target="tab-keys" role="tab" aria-controls="tab-keys" aria-selected="{{ $activeTab === 'tab-keys' ? 'true' : 'false' }}">Danh sách key</button>
    </div>

    {{-- Tab: Refersion token --}}
    <div id="tab-refersion" class="tab-panel {{ $activeTab === 'tab-refersion' ? 'active' : '' }}">
        <div class="card">
            <div class="card-head">
                <h3>Cập nhật Token Refersion</h3>
                <p class="card-desc">Token dùng chung cho app client. Sau khi lưu, máy đã kích hoạt key sẽ tự đồng bộ vào phần Cài đặt.</p>
            </div>
            <div class="card-body">
                <form method="post" action="{{ route('admin.settings.refersion_token') }}">
                    @csrf
                    <input type="hidden" name="tab" value="tab-refersion">
                    <div class="token-field">
                        <label class="field-label" for="refersion_token">Refersion token</label>
                        <div class="flex-input-row">
                            <input id="refersion_token" name="refersion_token" type="text" value="{{ $refersionToken }}" autocomplete="off" placeholder="Dán token Refersion vào đây">
                            <button id="btn-refresh-refersion-token" type="button" class="btn btn-warn" style="flex-shrink:0;" title="Lấy token từ phiên Refersion đang đăng nhập trên trình duyệt">Update</button>
                        </div>
                    </div>
                    <div class="form-actions">
                        <button type="submit" class="btn btn-primary">Lưu token</button>
                    </div>
                </form>
            </div>
        </div>
    </div>

    {{-- Tab: Collabs cookie + CSRF --}}
    <div id="tab-collabs" class="tab-panel {{ $activeTab === 'tab-collabs' ? 'active' : '' }}">
        <div class="card">
            <div class="card-head">
                <h3>Cập nhật Collabs cookie + CSRF</h3>
                <p class="card-desc">Cookie request (COLLABS_COOKIE) và X-CSRF-Token (COLLABS_CSRF_TOKEN) dùng chung cho app client. Sau khi lưu, máy đã kích hoạt key sẽ tự đồng bộ vào phần Cài đặt.</p>
            </div>
            <div class="card-body">
                <form method="post" action="{{ route('admin.settings.collabs_session') }}">
                    @csrf
                    <input type="hidden" name="tab" value="tab-collabs">
                    <div class="token-field">
                        <label class="field-label" for="collabs_cookie">Cookie request (COLLABS_COOKIE)</label>
                        <textarea id="collabs_cookie" name="collabs_cookie" rows="4" autocomplete="off" placeholder="Dán cookie Collabs vào đây">{{ $collabsCookie ?? '' }}</textarea>
                    </div>
                    <div class="token-field" style="margin-top:14px;">
                        <label class="field-label" for="collabs_csrf_token">X-CSRF-Token (COLLABS_CSRF_TOKEN)</label>
                        <div class="flex-input-row">
                            <input id="collabs_csrf_token" name="collabs_csrf_token" type="text" value="{{ $collabsCsrfToken ?? '' }}" autocomplete="off" placeholder="Dán CSRF token Collabs vào đây">
                            <button id="btn-refresh-collabs-session" type="button" class="btn btn-warn" style="flex-shrink:0;" title="Lấy cookie + CSRF từ phiên Collabs đang đăng nhập trên trình duyệt">Update</button>
                        </div>
                    </div>
                    <div class="form-actions">
                        <button type="submit" class="btn btn-primary">Lưu session</button>
                    </div>
                </form>
            </div>
        </div>
    </div>

    {{-- Tab: Quick key --}}
    <div id="tab-quick-key" class="tab-panel {{ $activeTab === 'tab-quick-key' ? 'active' : '' }}">
        <div class="card">
            <div class="card-head">
                <h3>Thêm hoặc cập nhật nhanh 1 key</h3>
                <p class="card-desc">Tạo key mới hoặc ghi đè key đã có (cùng mã key). Điền đủ hạn mức và net được phép.</p>
            </div>
            <div class="card-body">
                <form method="post" action="{{ route('admin.keys.store') }}">
                    @csrf
                    <input type="hidden" name="tab" value="tab-quick-key">

                    <div class="form-section">
                        <p class="form-section-title">Thông tin key</p>
                        <div class="grid" style="grid-template-columns: 1fr;">
                            <div style="max-width: 100%;">
                                <label class="field-label" for="quick-license-key">Key bản quyền</label>
                                <div class="flex-input-row">
                                    <input id="quick-license-key" name="license_key" required placeholder="AFL1-XXXX-XXXX-XXXX">
                                    <button id="btn-generate-key" type="button" class="btn btn-warn" style="flex-shrink:0;">Tạo mã</button>
                                </div>
                            </div>
                        </div>
                        <div class="grid" style="margin-top:14px;">
                            <div>
                                <label class="field-label">Giới hạn record / ngày</label>
                                <input name="daily_limit" type="number" min="1" value="500">
                            </div>
                            <div>
                                <label class="field-label">Số máy tối đa</label>
                                <input name="max_machines" type="number" min="1" value="2">
                            </div>
                            <div>
                                <label class="field-label">Hạn dùng</label>
                                <input name="expires_at" type="datetime-local">
                            </div>
                            <div>
                                <label class="field-label">Ghi chú</label>
                                <input name="notes" placeholder="Tuỳ chọn">
                            </div>
                        </div>
                    </div>

                    <div class="form-section">
                        <p class="form-section-title">Net được phép (theo key)</p>
                        <div class="check-group">
                            <label class="check-chip"><input type="checkbox" name="allowed_sources[]" value="uppromote" checked> Uppromote</label>
                            <label class="check-chip"><input type="checkbox" name="allowed_sources[]" value="goaffpro" checked> Goaffpro</label>
                            <label class="check-chip"><input type="checkbox" name="allowed_sources[]" value="refersion"> Refersion</label>
                            <label class="check-chip"><input type="checkbox" name="allowed_sources[]" value="collabs"> Shopify Collabs</label>
                        </div>
                    </div>

                    <div class="form-section">
                        <p class="form-section-title">Tính năng app</p>
                        <div class="check-group">
                            <label class="check-chip"><input type="checkbox" name="allow_auto_apply_collabs" value="1" checked> Bật Auto Apply Collabs</label>
                            <label class="check-chip"><input type="checkbox" name="allow_auto_apply_refersion" value="1"> Bật Auto Apply Refersion</label>
                        </div>
                        <p class="muted" style="margin-top:8px;">Tắt mục này sẽ ẩn tab/chức năng tương ứng trên app client.</p>
                    </div>

                    <div class="form-actions">
                        <button type="submit" class="btn btn-primary">Lưu key</button>
                    </div>
                </form>
            </div>
        </div>
    </div>

    {{-- Tab: Activations --}}
    <div id="tab-activations" class="tab-panel {{ $activeTab === 'tab-activations' ? 'active' : '' }}">
        <div class="card">
            <div class="card-head">
                <h3>Activation đang hoạt động</h3>
                <p class="card-desc">Usage theo ngày VN: <strong>{{ $usageDayVn }}</strong>. Tìm theo mã activation, máy, key hoặc chú thích.</p>
            </div>
            <div class="card-body">
                <form method="get" action="{{ route('admin.dashboard') }}" class="search-bar">
                    <input type="hidden" name="tab" value="tab-activations">
                    <input type="hidden" name="keys_q" value="{{ request('keys_q') }}">
                    <input type="search" name="activation_q" value="{{ request('activation_q') }}" placeholder="Tìm activation, mã máy, key, chú thích…" autocomplete="off">
                    <button type="submit" class="btn btn-primary">Tìm</button>
                    @if(request()->filled('activation_q'))
                        <a class="btn btn-ghost" href="{{ route('admin.dashboard', array_filter(['tab' => 'tab-activations', 'keys_q' => request('keys_q')])) }}">Xóa lọc</a>
                    @endif
                </form>

                <div class="table-wrap">
                    <div class="table-scroll">
                        <table class="data-table">
                            <thead>
                            <tr>
                                <th class="col-id">ID</th>
                                <th>Mã activation</th>
                                <th>Key</th>
                                <th>Mã máy</th>
                                <th>Đã dùng hôm nay</th>
                                <th>Kích hoạt</th>
                                <th>Online cuối</th>
                                <th>Chú thích</th>
                                <th class="col-actions">Thao tác</th>
                            </tr>
                            </thead>
                            <tbody>
                            @foreach($activations as $a)
                                <tr class="mobile-card-row">
                                    <td class="col-id" data-label="ID">{{ $a->id }}</td>
                                    <td data-label="Mã activation"><code class="code-inline">{{ $a->activation_id }}</code></td>
                                    <td class="col-key" data-label="Key"><span class="key-display">{{ $a->licenseKey?->license_key }}</span></td>
                                    <td data-label="Mã máy"><code class="code-inline">{{ $a->machine_fingerprint }}</code></td>
                                    <td data-label="Đã dùng hôm nay"><strong>{{ (int) (($a->dailyUsages->first()->used_total ?? 0)) }}</strong></td>
                                    <td data-label="Kích hoạt">{{ $a->activated_at }}</td>
                                    <td data-label="Online cuối">{{ $a->last_seen_at }}</td>
                                    <td data-label="Chú thích">
                                        @php($keyNotes = trim((string) ($a->licenseKey?->notes ?? '')))
                                        <span class="muted">{{ $keyNotes !== '' ? $keyNotes : (data_get($a->meta, 'notes') ?: '—') }}</span>
                                    </td>
                                    <td class="col-actions" data-label="Thao tác">
                                        <form method="post" action="{{ route('admin.activations.revoke', ['id' => $a->id]) }}" onsubmit="return confirm('Thu hồi activation này? Máy sẽ không dùng key được nữa.');">
                                            @csrf
                                            <input type="hidden" name="tab" value="tab-activations">
                                            <input type="hidden" name="activation_q" value="{{ request('activation_q') }}">
                                            <input type="hidden" name="activations_page" value="{{ request('activations_page') }}">
                                            <input type="hidden" name="keys_q" value="{{ request('keys_q') }}">
                                            <button class="btn btn-danger btn-sm" type="submit">Thu hồi</button>
                                        </form>
                                    </td>
                                </tr>
                            @endforeach
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="pagination">
                    <span class="pg-info">Trang {{ $activations->currentPage() }} / {{ $activations->lastPage() }}</span>
                    <div class="pagination-nav">
                        <a class="pg-btn {{ $activations->onFirstPage() ? 'disabled' : '' }}" href="{{ $activations->previousPageUrl() ?: '#' }}">← Trước</a>
                        <a class="pg-btn {{ $activations->hasMorePages() ? '' : 'disabled' }}" href="{{ $activations->nextPageUrl() ?: '#' }}">Sau →</a>
                    </div>
                </div>
            </div>
        </div>
    </div>

    {{-- Tab: Keys list --}}
    <div id="tab-keys" class="tab-panel {{ $activeTab === 'tab-keys' ? 'active' : '' }}">
        <div class="card">
            <div class="card-head">
                <h3>Danh sách key</h3>
                <p class="card-desc">Mỗi key có một hàng thông tin và hàng chỉnh sửa ngay bên dưới. Xuất file CSV toàn bộ key (tên file = ngày xuất).</p>
            </div>
            <div class="card-body">
                <div class="keys-toolbar">
                    <form method="get" action="{{ route('admin.dashboard') }}" class="search-bar keys-toolbar-search">
                        <input type="hidden" name="tab" value="tab-keys">
                        <input type="hidden" name="activation_q" value="{{ request('activation_q') }}">
                        <input type="search" name="keys_q" value="{{ request('keys_q') }}" placeholder="Tìm theo key, key_hint hoặc chú thích…" autocomplete="off">
                        <button type="submit" class="btn btn-primary">Tìm</button>
                        @if(request()->filled('keys_q'))
                            <a class="btn btn-ghost" href="{{ route('admin.dashboard', array_filter(['tab' => 'tab-keys', 'activation_q' => request('activation_q')])) }}">Xóa lọc</a>
                        @endif
                    </form>
                    <a class="btn btn-ghost keys-export-btn" href="{{ route('admin.keys.export') }}" download>Xuất</a>
                </div>

                <div class="table-wrap">
                    <div class="table-scroll">
                        <table class="data-table data-table-keys">
                            <thead>
                            <tr>
                                <th class="col-id">ID</th>
                                <th class="col-key">Key</th>
                                <th>Trạng thái</th>
                                <th>Máy active</th>
                                <th>Record/ngày</th>
                                <th>Số máy max</th>
                                <th>Net</th>
                                <th>Hạn dùng</th>
                            </tr>
                            </thead>
                            <tbody>
                            @foreach($keys as $k)
                                @php($allowed = $k->normalizedAllowedSources())
                                <tr class="key-row mobile-card-row">
                                    <td class="col-id" data-label="ID">{{ $k->id }}</td>
                                    <td class="col-key" data-label="Key">
                                        <div class="key-display">{{ $k->license_key }}</div>
                                        @if($k->notes)
                                            <div class="key-notes">{{ $k->notes }}</div>
                                        @endif
                                    </td>
                                    <td data-label="Trạng thái">
                                        @if($k->status === 'active')
                                            <span class="badge badge-ok">Hoạt động</span>
                                        @else
                                            <span class="badge badge-bad">Khóa</span>
                                        @endif
                                    </td>
                                    <td data-label="Máy active"><span class="badge badge-muted">{{ $k->active_activations_count }}</span></td>
                                    <td data-label="Record/ngày">{{ $k->daily_limit ?? '—' }}</td>
                                    <td data-label="Số máy max">{{ $k->max_machines ?? '—' }}</td>
                                    <td data-label="Net"><span class="muted">{{ implode(', ', $allowed) }}</span></td>
                                    <td data-label="Hạn dùng">{{ $k->expires_at ?? '—' }}</td>
                                </tr>
                                <tr class="key-edit-row">
                                    <td colspan="8">
                                        <div class="edit-panel edit-panel--row">
                                            <div class="edit-panel-grid">
                                                <form id="update-key-{{ $k->id }}" method="post" action="{{ route('admin.keys.update', ['id' => $k->id]) }}" class="edit-panel-form" onsubmit="return confirm('Cập nhật key {{ $k->license_key }}?');">
                                                    @csrf
                                                    <input type="hidden" name="tab" value="tab-keys">
                                                    <input type="hidden" name="keys_q" value="{{ request('keys_q') }}">
                                                    <input type="hidden" name="keys_page" value="{{ request('keys_page') }}">
                                                    <input type="hidden" name="activation_q" value="{{ request('activation_q') }}">
                                                    <div class="edit-field">
                                                        <label class="field-label">Trạng thái</label>
                                                        <select name="status">
                                                            <option value="active" @selected($k->status==='active')>Hoạt động</option>
                                                            <option value="blocked" @selected($k->status==='blocked')>Khóa</option>
                                                        </select>
                                                    </div>
                                                    <div class="edit-field edit-field--narrow">
                                                        <label class="field-label">Record/ngày</label>
                                                        <input name="daily_limit" type="number" min="1" value="{{ $k->daily_limit }}">
                                                    </div>
                                                    <div class="edit-field edit-field--narrow">
                                                        <label class="field-label">Số máy max</label>
                                                        <input name="max_machines" type="number" min="1" value="{{ $k->max_machines }}">
                                                    </div>
                                                    <div class="edit-field edit-field--date">
                                                        <label class="field-label">Hạn dùng</label>
                                                        <input name="expires_at" type="datetime-local" value="{{ $k->expires_at ? \Illuminate\Support\Carbon::parse($k->expires_at)->format('Y-m-d\TH:i') : '' }}">
                                                    </div>
                                                    <div class="edit-field edit-field--grow">
                                                        <label class="field-label">Ghi chú</label>
                                                        <input name="notes" value="{{ $k->notes }}" placeholder="Chú thích key">
                                                    </div>
                                                    <div class="edit-field edit-field--full">
                                                        <label class="field-label">Net &amp; tính năng</label>
                                                        <div class="check-group">
                                                            <label class="check-chip"><input type="checkbox" name="allowed_sources[]" value="uppromote" @checked(in_array('uppromote', $allowed, true))> Uppromote</label>
                                                            <label class="check-chip"><input type="checkbox" name="allowed_sources[]" value="goaffpro" @checked(in_array('goaffpro', $allowed, true))> Goaffpro</label>
                                                            <label class="check-chip"><input type="checkbox" name="allowed_sources[]" value="refersion" @checked(in_array('refersion', $allowed, true))> Refersion</label>
                                                            <label class="check-chip"><input type="checkbox" name="allowed_sources[]" value="collabs" @checked(in_array('collabs', $allowed, true))> Collabs</label>
                                                            <label class="check-chip"><input type="checkbox" name="allow_auto_apply_collabs" value="1" @checked((bool) $k->allow_auto_apply_collabs)> Auto Apply Collabs</label>
                                                            <label class="check-chip"><input type="checkbox" name="allow_auto_apply_refersion" value="1" @checked((bool) $k->allow_auto_apply_refersion)> Auto Apply Refersion</label>
                                                        </div>
                                                    </div>
                                                </form>
                                                <div class="edit-field edit-field--actions">
                                                    <span class="field-label field-label--spacer" aria-hidden="true">&nbsp;</span>
                                                    <div class="edit-panel-actions">
                                                        <button type="submit" class="btn btn-primary btn-sm" form="update-key-{{ $k->id }}">Cập nhật</button>
                                                        <form method="post" action="{{ route('admin.keys.delete', ['id' => $k->id]) }}" class="edit-inline-form" onsubmit="return confirm('Xóa key {{ $k->license_key }}? Toàn bộ activation và usage liên quan sẽ bị xóa.');">
                                                            @csrf
                                                            <input type="hidden" name="tab" value="tab-keys">
                                                            <input type="hidden" name="keys_q" value="{{ request('keys_q') }}">
                                                            <input type="hidden" name="keys_page" value="{{ request('keys_page') }}">
                                                            <input type="hidden" name="activation_q" value="{{ request('activation_q') }}">
                                                            <button type="submit" class="btn btn-danger btn-sm">Xóa key</button>
                                                        </form>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                            @endforeach
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="pagination">
                    <span class="pg-info">Trang {{ $keys->currentPage() }} / {{ $keys->lastPage() }}</span>
                    <div class="pagination-nav">
                        <a class="pg-btn {{ $keys->onFirstPage() ? 'disabled' : '' }}" href="{{ $keys->previousPageUrl() ?: '#' }}">← Trước</a>
                        <a class="pg-btn {{ $keys->hasMorePages() ? '' : 'disabled' }}" href="{{ $keys->nextPageUrl() ?: '#' }}">Sau →</a>
                    </div>
                </div>
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
        var btn = document.getElementById('btn-refresh-refersion-token');
        var input = document.getElementById('refersion_token');
        if (!btn || !input) return;
        var edgeApiUrl = @json(route('admin.settings.refersion_token.from_edge'));

        btn.addEventListener('click', async function () {
            btn.disabled = true;
            try {
                var res = await fetch(edgeApiUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': @json(csrf_token())
                    },
                    body: JSON.stringify({})
                });
                var data = await res.json().catch(function () { return {}; });
                if (!res.ok || !data.ok) {
                    alert(data.error || 'Không lấy được Refersion token từ Edge CDP.');
                    return;
                }
                var token = String(data.token || '').trim();
                input.value = token;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                alert(data.message || 'Đã cập nhật Refersion token từ Edge CDP.');
            } catch (e) {
                alert('Lỗi gọi backend lấy Refersion token: ' + (e && e.message ? e.message : e));
            } finally {
                btn.disabled = false;
            }
        });

    })();
</script>
<script>
    (function () {
        var btn = document.getElementById('btn-refresh-collabs-session');
        var cookieInput = document.getElementById('collabs_cookie');
        var csrfInput = document.getElementById('collabs_csrf_token');
        if (!btn || !cookieInput || !csrfInput) return;
        var edgeApiUrl = @json(route('admin.settings.collabs_session.from_edge'));

        btn.addEventListener('click', async function () {
            btn.disabled = true;
            try {
                var res = await fetch(edgeApiUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': @json(csrf_token())
                    },
                    body: JSON.stringify({})
                });
                var data = await res.json().catch(function () { return {}; });
                if (!res.ok || !data.ok) {
                    alert(data.error || 'Không lấy được Collabs session từ Edge CDP.');
                    return;
                }
                cookieInput.value = String(data.cookie || '').trim();
                csrfInput.value = String(data.csrf_token || '').trim();
                cookieInput.dispatchEvent(new Event('input', { bubbles: true }));
                csrfInput.dispatchEvent(new Event('input', { bubbles: true }));
                alert(data.message || 'Đã cập nhật Collabs session từ Edge CDP.');
            } catch (e) {
                alert('Lỗi gọi backend lấy Collabs session: ' + (e && e.message ? e.message : e));
            } finally {
                btn.disabled = false;
            }
        });
    })();
</script>
<script>
    (function () {
        var btns = Array.prototype.slice.call(document.querySelectorAll('.tab-btn[data-tab-target]'));
        var panels = Array.prototype.slice.call(document.querySelectorAll('.tab-panel'));
        if (!btns.length || !panels.length) return;

        var defaultTab = @json($activeTab ?? 'tab-refersion');

        function resolveTabId() {
            try {
                var q = new URLSearchParams(window.location.search).get('tab');
                if (q && document.getElementById(q)) return q;
            } catch (_) {}
            var h = (window.location.hash || '').replace('#', '').trim();
            if (h && document.getElementById(h)) return h;
            if (defaultTab && document.getElementById(defaultTab)) return defaultTab;
            return 'tab-refersion';
        }

        function setActive(tabId, updateUrl) {
            btns.forEach(function (b) {
                var isActive = b.getAttribute('data-tab-target') === tabId;
                b.classList.toggle('active', isActive);
                b.setAttribute('aria-selected', isActive ? 'true' : 'false');
            });
            panels.forEach(function (p) {
                p.classList.toggle('active', p.id === tabId);
            });
            if (updateUrl) {
                try {
                    var u = new URL(window.location.href);
                    u.searchParams.set('tab', tabId);
                    u.hash = tabId;
                    history.replaceState(null, '', u.pathname + u.search + u.hash);
                } catch (_) {
                    try { window.location.hash = tabId; } catch (_e) {}
                }
            }
        }

        btns.forEach(function (b) {
            b.addEventListener('click', function () {
                var id = b.getAttribute('data-tab-target') || '';
                if (!id) return;
                setActive(id, true);
            });
        });

        setActive(resolveTabId(), false);
    })();
</script>
</body>
</html>
