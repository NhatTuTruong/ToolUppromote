<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\AppSetting;
use App\Models\LicenseActivation;
use App\Models\LicenseKey;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Str;
use Illuminate\View\View;
use Symfony\Component\Process\Process;
use Symfony\Component\HttpFoundation\StreamedResponse;

class LicenseManagementController extends Controller
{
    private const ADMIN_TABS = [
        'tab-refersion',
        'tab-quick-key',
        'tab-activations',
        'tab-keys',
    ];

    private function resolveActiveTab(Request $request): string
    {
        $tab = trim((string) $request->query('tab', 'tab-refersion'));
        if (! in_array($tab, self::ADMIN_TABS, true)) {
            return 'tab-refersion';
        }

        return $tab;
    }

    /** Redirect về dashboard, giữ tab + bộ lọc/phân trang hiện tại. */
    private function redirectToDashboard(Request $request, string $defaultTab = 'tab-refersion'): RedirectResponse
    {
        $tab = trim((string) $request->input('tab', $defaultTab));
        if (! in_array($tab, self::ADMIN_TABS, true)) {
            $tab = $defaultTab;
        }

        $query = array_filter([
            'tab' => $tab,
            'keys_q' => $request->input('keys_q'),
            'activation_q' => $request->input('activation_q'),
            'keys_page' => $request->input('keys_page'),
            'activations_page' => $request->input('activations_page'),
        ], static fn ($v) => $v !== null && $v !== '');

        return redirect()->route('admin.dashboard', $query);
    }

    public function dashboard(): View
    {
        $activeTab = $this->resolveActiveTab(request());
        $todayVn = now('Asia/Ho_Chi_Minh')->toDateString();
        $keysQ = trim((string) request('keys_q', ''));
        $keysQuery = LicenseKey::query()
            ->withCount(['activations as active_activations_count' => function ($query): void {
                $query->whereNull('deactivated_at');
            }])
            ->orderByDesc('id');

        if ($keysQ !== '') {
            $keysQuery->where(function ($q) use ($keysQ): void {
                $q->where('license_key', 'like', '%'.$keysQ.'%')
                    ->orWhere('notes', 'like', '%'.$keysQ.'%')
                    ->orWhere('key_hint', 'like', '%'.$keysQ.'%');
            });
        }

        $keys = $keysQuery->paginate(20, ['*'], 'keys_page')
            ->appends(request()->only(['tab', 'activation_q']));

        $activationQ = trim((string) request('activation_q', ''));
        $activationsQuery = LicenseActivation::query()
            ->with(['licenseKey', 'dailyUsages' => function ($q) use ($todayVn): void {
                $q->where('usage_day', $todayVn);
            }])
            ->whereNull('deactivated_at')
            ->orderByDesc('activated_at');

        if ($activationQ !== '') {
            $activationsQuery->where(function ($q) use ($activationQ): void {
                $q->where('activation_id', 'like', '%'.$activationQ.'%')
                    ->orWhere('machine_fingerprint', 'like', '%'.$activationQ.'%')
                    ->orWhereHas('licenseKey', function ($q2) use ($activationQ): void {
                        $q2->where('license_key', 'like', '%'.$activationQ.'%')
                            ->orWhere('notes', 'like', '%'.$activationQ.'%');
                    });
            });
        }

        $activations = $activationsQuery->paginate(20, ['*'], 'activations_page')
            ->appends(request()->only(['tab', 'keys_q']));

        $refersionIngestNonce = (string) Str::uuid();
        Cache::put('refersion_ingest_nonce:'.$refersionIngestNonce, true, now()->addMinutes(10));

        return view('admin.dashboard', [
            'activeTab' => $activeTab,
            'keys' => $keys,
            'activations' => $activations,
            'usageDayVn' => $todayVn,
            'refersionToken' => AppSetting::getValue('refersion_token', ''),
            'refersionIngestNonce' => $refersionIngestNonce,
            'refersionIngestUrl' => route('admin.settings.refersion_token.ingest'),
        ]);
    }

    public function ingestRefersionToken(Request $request): JsonResponse
    {
        $data = $request->validate([
            'nonce' => ['required', 'string', 'max:120'],
            'token' => ['required', 'string', 'max:4000'],
        ]);
        $nonce = trim((string) $data['nonce']);
        $token = trim((string) $data['token']);
        if ($nonce === '' || $token === '') {
            return response()->json(['ok' => false, 'error' => 'Thiếu nonce/token'], 400);
        }
        $cacheKey = 'refersion_ingest_nonce:'.$nonce;
        if (!Cache::pull($cacheKey)) {
            return response()->json(['ok' => false, 'error' => 'Nonce không hợp lệ hoặc đã hết hạn'], 403);
        }
        AppSetting::query()->updateOrCreate(
            ['key' => 'refersion_token'],
            ['value' => $token]
        );
        return response()->json(['ok' => true, 'message' => 'Đã cập nhật Refersion token.']);
    }

    public function updateRefersionToken(Request $request): RedirectResponse
    {
        $data = $request->validate([
            'refersion_token' => ['nullable', 'string', 'max:4000'],
        ]);

        $token = trim((string) ($data['refersion_token'] ?? ''));

        AppSetting::query()->updateOrCreate(
            ['key' => 'refersion_token'],
            ['value' => $token]
        );

        return $this->redirectToDashboard($request, 'tab-refersion')->with('success', 'Đã cập nhật Refersion token.');
    }

    public function refreshRefersionTokenFromEdge(Request $request): JsonResponse
    {
        $node = trim((string) env('NODE_BIN', 'node'));
        $script = base_path('scripts/refersion_token_from_edge.mjs');
        if (!is_file($script)) {
            return response()->json(['ok' => false, 'error' => 'Thiếu script JS lấy token từ Edge CDP.'], 500);
        }
        $process = new Process([$node, $script], base_path());
        $process->setTimeout(120);
        try {
            $process->run();
        } catch (\Throwable $e) {
            return response()->json(['ok' => false, 'error' => 'Không chạy được tiến trình Node: '.$e->getMessage()], 500);
        }
        $stdout = trim((string) $process->getOutput());
        $stderr = trim((string) $process->getErrorOutput());
        if (!$process->isSuccessful()) {
            return response()->json([
                'ok' => false,
                'error' => $stderr !== '' ? $stderr : ($stdout !== '' ? $stdout : 'Lấy token từ Edge CDP thất bại.'),
            ], 400);
        }
        $payload = json_decode($stdout, true);
        if (!is_array($payload) || !($payload['ok'] ?? false)) {
            return response()->json([
                'ok' => false,
                'error' => is_array($payload) ? (string) ($payload['error'] ?? 'Payload không hợp lệ.') : ($stdout ?: 'Payload không hợp lệ.'),
            ], 400);
        }
        $token = trim((string) ($payload['token'] ?? ''));
        if ($token === '') {
            return response()->json(['ok' => false, 'error' => 'Không đọc được refersion-token từ Edge CDP.'], 400);
        }
        AppSetting::query()->updateOrCreate(
            ['key' => 'refersion_token'],
            ['value' => $token]
        );
        return response()->json([
            'ok' => true,
            'token' => $token,
            'message' => 'Đã cập nhật Refersion token từ Edge CDP.',
        ]);
    }

    public function storeKey(Request $request): RedirectResponse
    {
        $data = $request->validate([
            'license_key' => ['required', 'string', 'max:120'],
            'daily_limit' => ['nullable', 'integer', 'min:1'],
            'max_machines' => ['nullable', 'integer', 'min:1'],
            'allowed_sources' => ['required', 'array', 'min:1'],
            'allowed_sources.*' => ['string', 'in:uppromote,goaffpro,refersion,collabs'],
            'allow_auto_apply_collabs' => ['nullable', 'boolean'],
            'allow_auto_apply_refersion' => ['nullable', 'boolean'],
            'expires_at' => ['nullable', 'date'],
            'notes' => ['nullable', 'string', 'max:2000'],
        ]);

        $key = strtoupper(trim($data['license_key']));
        $model = LicenseKey::query()->firstOrNew(['license_key' => $key]);
        $model->key_hint = substr($key, -6);
        $model->status = $model->status ?: 'active';
        $model->daily_limit = $data['daily_limit'] ?? $model->daily_limit ?? (int) config('license.default_daily_limit', 500);
        $model->max_machines = $data['max_machines'] ?? $model->max_machines ?? (int) config('license.max_machines_per_key', 2);
        $model->allowed_sources = array_values(array_unique($data['allowed_sources'] ?? LicenseKey::DEFAULT_ALLOWED_SOURCES));
        $model->allow_auto_apply_collabs = $request->boolean('allow_auto_apply_collabs', true);
        $model->allow_auto_apply_refersion = $request->boolean('allow_auto_apply_refersion', false);
        $model->expires_at = $data['expires_at'] ?? null;
        $model->notes = $data['notes'] ?? null;
        $model->save();

        return $this->redirectToDashboard($request, 'tab-quick-key')->with('success', 'Đã lưu key.');
    }

    public function bulkImport(Request $request): RedirectResponse
    {
        $data = $request->validate([
            'bulk_keys' => ['required', 'string'],
            'daily_limit' => ['nullable', 'integer', 'min:1'],
            'max_machines' => ['nullable', 'integer', 'min:1'],
            'allowed_sources' => ['required', 'array', 'min:1'],
            'allowed_sources.*' => ['string', 'in:uppromote,goaffpro,refersion,collabs'],
        ]);

        $dailyLimit = $data['daily_limit'] ?? (int) config('license.default_daily_limit', 500);
        $maxMachines = $data['max_machines'] ?? (int) config('license.max_machines_per_key', 2);
        $allowedSources = array_values(array_unique($data['allowed_sources'] ?? LicenseKey::DEFAULT_ALLOWED_SOURCES));
        $created = 0;
        $updated = 0;

        $lines = preg_split('/\r\n|\r|\n/', $data['bulk_keys']) ?: [];
        foreach ($lines as $line) {
            $key = strtoupper(trim($line));
            if ($key === '' || str_starts_with($key, '#')) {
                continue;
            }
            $model = LicenseKey::query()->firstOrNew(['license_key' => $key]);
            $isNew = !$model->exists;
            $model->key_hint = substr($key, -6);
            $model->status = $model->status ?: 'active';
            $model->daily_limit = $model->daily_limit ?? $dailyLimit;
            $model->max_machines = $model->max_machines ?? $maxMachines;
            $model->allowed_sources = is_array($model->allowed_sources) && $model->allowed_sources !== []
                ? $model->allowed_sources
                : $allowedSources;
            $model->save();
            if ($isNew) {
                $created++;
            } else {
                $updated++;
            }
        }

        return $this->redirectToDashboard($request, 'tab-quick-key')->with('success', "Import xong. Created={$created}, Updated={$updated}");
    }

    public function updateKey(Request $request, int $id): RedirectResponse
    {
        $data = $request->validate([
            'status' => ['required', 'in:active,blocked'],
            'daily_limit' => ['nullable', 'integer', 'min:1'],
            'max_machines' => ['nullable', 'integer', 'min:1'],
            'allowed_sources' => ['required', 'array', 'min:1'],
            'allowed_sources.*' => ['string', 'in:uppromote,goaffpro,refersion,collabs'],
            'allow_auto_apply_collabs' => ['nullable', 'boolean'],
            'allow_auto_apply_refersion' => ['nullable', 'boolean'],
            'expires_at' => ['nullable', 'date'],
            'notes' => ['nullable', 'string', 'max:2000'],
        ]);

        $key = LicenseKey::query()->findOrFail($id);
        $key->status = $data['status'];
        $key->daily_limit = $data['daily_limit'] ?? null;
        $key->max_machines = $data['max_machines'] ?? null;
        $key->allowed_sources = array_values(array_unique($data['allowed_sources'] ?? []));
        $key->allow_auto_apply_collabs = $request->boolean('allow_auto_apply_collabs');
        $key->allow_auto_apply_refersion = $request->boolean('allow_auto_apply_refersion');
        $key->expires_at = $data['expires_at'] ?? null;
        $key->notes = $data['notes'] ?? null;
        $key->save();

        return $this->redirectToDashboard($request, 'tab-keys')->with('success', 'Đã cập nhật key.');
    }

    public function exportKeys(): StreamedResponse
    {
        $filename = now('Asia/Ho_Chi_Minh')->format('Y-m-d').'.csv';

        return response()->streamDownload(function (): void {
            $handle = fopen('php://output', 'wb');
            if ($handle === false) {
                return;
            }

            fwrite($handle, "\xEF\xBB\xBF");

            fputcsv($handle, [
                'ID',
                'Key bản quyền',
                'Key hint',
                'Trạng thái',
                'Máy đang active',
                'Record/ngày',
                'Số máy max',
                'Net được phép',
                'Auto Apply Collabs',
                'Auto Apply Refersion',
                'Hạn dùng',
                'Ghi chú',
                'Ngày tạo',
                'Cập nhật lúc',
            ]);

            LicenseKey::query()
                ->withCount(['activations as active_activations_count' => function ($query): void {
                    $query->whereNull('deactivated_at');
                }])
                ->orderByDesc('id')
                ->chunk(200, function ($keys) use ($handle): void {
                    foreach ($keys as $key) {
                        $expiresAt = $key->expires_at instanceof Carbon
                            ? $key->expires_at->timezone('Asia/Ho_Chi_Minh')->format('Y-m-d H:i:s')
                            : '';

                        fputcsv($handle, [
                            $key->id,
                            $key->license_key,
                            $key->key_hint ?? '',
                            $key->status,
                            (int) ($key->active_activations_count ?? 0),
                            $key->daily_limit ?? '',
                            $key->max_machines ?? '',
                            implode(', ', $key->normalizedAllowedSources()),
                            $key->allow_auto_apply_collabs ? 'Bat' : 'Tat',
                            $key->allow_auto_apply_refersion ? 'Bat' : 'Tat',
                            $expiresAt,
                            $key->notes ?? '',
                            $key->created_at?->timezone('Asia/Ho_Chi_Minh')->format('Y-m-d H:i:s') ?? '',
                            $key->updated_at?->timezone('Asia/Ho_Chi_Minh')->format('Y-m-d H:i:s') ?? '',
                        ]);
                    }
                });

            fclose($handle);
        }, $filename, [
            'Content-Type' => 'text/csv; charset=UTF-8',
        ]);
    }

    public function deleteKey(Request $request, int $id): RedirectResponse
    {
        $key = LicenseKey::query()->findOrFail($id);
        $keyText = (string) $key->license_key;
        $key->delete();

        return $this->redirectToDashboard($request, 'tab-keys')->with('success', "Đã xóa key {$keyText}.");
    }

    public function revokeActivation(Request $request, int $id): RedirectResponse
    {
        $activation = LicenseActivation::query()->findOrFail($id);
        if ($activation->deactivated_at === null) {
            $activation->deactivated_at = now();
            $activation->last_seen_at = now();
            $activation->save();
        }
        return $this->redirectToDashboard($request, 'tab-activations')->with('success', 'Đã thu hồi activation.');
    }
}
