<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\LicenseActivation;
use App\Models\LicenseKey;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\View\View;

class LicenseManagementController extends Controller
{
    public function dashboard(): View
    {
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

        $keys = $keysQuery->paginate(20, ['*'], 'keys_page')->withQueryString();

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

        $activations = $activationsQuery->paginate(20, ['*'], 'activations_page')->withQueryString();

        return view('admin.dashboard', [
            'keys' => $keys,
            'activations' => $activations,
            'usageDayVn' => $todayVn,
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
        $model->expires_at = $data['expires_at'] ?? null;
        $model->notes = $data['notes'] ?? null;
        $model->save();

        return back()->with('success', 'Đã lưu key.');
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

        return back()->with('success', "Import xong. Created={$created}, Updated={$updated}");
    }

    public function updateKey(Request $request, int $id): RedirectResponse
    {
        $data = $request->validate([
            'status' => ['required', 'in:active,blocked'],
            'daily_limit' => ['nullable', 'integer', 'min:1'],
            'max_machines' => ['nullable', 'integer', 'min:1'],
            'allowed_sources' => ['required', 'array', 'min:1'],
            'allowed_sources.*' => ['string', 'in:uppromote,goaffpro,refersion,collabs'],
            'expires_at' => ['nullable', 'date'],
            'notes' => ['nullable', 'string', 'max:2000'],
        ]);

        $key = LicenseKey::query()->findOrFail($id);
        $key->status = $data['status'];
        $key->daily_limit = $data['daily_limit'] ?? null;
        $key->max_machines = $data['max_machines'] ?? null;
        $key->allowed_sources = array_values(array_unique($data['allowed_sources'] ?? []));
        $key->expires_at = $data['expires_at'] ?? null;
        $key->notes = $data['notes'] ?? null;
        $key->save();

        return back()->with('success', 'Đã cập nhật key.');
    }

    public function deleteKey(Request $request, int $id): RedirectResponse
    {
        $key = LicenseKey::query()->findOrFail($id);
        $keyText = (string) $key->license_key;
        $key->delete();

        return back()->with('success', "Đã xóa key {$keyText}.");
    }

    public function revokeActivation(Request $request, int $id): RedirectResponse
    {
        $activation = LicenseActivation::query()->findOrFail($id);
        if ($activation->deactivated_at === null) {
            $activation->deactivated_at = now();
            $activation->last_seen_at = now();
            $activation->save();
        }
        return back()->with('success', 'Đã thu hồi activation.');
    }
}
