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
        $keys = LicenseKey::query()
            ->withCount(['activations as active_activations_count' => function ($query): void {
                $query->whereNull('deactivated_at');
            }])
            ->orderByDesc('id')
            ->paginate(20, ['*'], 'keys_page');

        $activations = LicenseActivation::query()
            ->with('licenseKey')
            ->whereNull('deactivated_at')
            ->orderByDesc('activated_at')
            ->paginate(20, ['*'], 'activations_page');

        return view('admin.dashboard', [
            'keys' => $keys,
            'activations' => $activations,
        ]);
    }

    public function storeKey(Request $request): RedirectResponse
    {
        $data = $request->validate([
            'license_key' => ['required', 'string', 'max:120'],
            'daily_limit' => ['nullable', 'integer', 'min:1'],
            'max_machines' => ['nullable', 'integer', 'min:1'],
            'expires_at' => ['nullable', 'date'],
            'notes' => ['nullable', 'string', 'max:2000'],
        ]);

        $key = strtoupper(trim($data['license_key']));
        $model = LicenseKey::query()->firstOrNew(['license_key' => $key]);
        $model->key_hint = substr($key, -6);
        $model->status = $model->status ?: 'active';
        $model->daily_limit = $data['daily_limit'] ?? $model->daily_limit ?? (int) config('license.default_daily_limit', 500);
        $model->max_machines = $data['max_machines'] ?? $model->max_machines ?? (int) config('license.max_machines_per_key', 2);
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
        ]);

        $dailyLimit = $data['daily_limit'] ?? (int) config('license.default_daily_limit', 500);
        $maxMachines = $data['max_machines'] ?? (int) config('license.max_machines_per_key', 2);
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
            'expires_at' => ['nullable', 'date'],
            'notes' => ['nullable', 'string', 'max:2000'],
        ]);

        $key = LicenseKey::query()->findOrFail($id);
        $key->status = $data['status'];
        $key->daily_limit = $data['daily_limit'] ?? null;
        $key->max_machines = $data['max_machines'] ?? null;
        $key->expires_at = $data['expires_at'] ?? null;
        $key->notes = $data['notes'] ?? null;
        $key->save();

        return back()->with('success', 'Đã cập nhật key.');
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
