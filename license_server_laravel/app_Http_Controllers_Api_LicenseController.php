<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\LicenseActivation;
use App\Models\LicenseKey;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;

class LicenseController extends Controller
{
    public function health(): JsonResponse
    {
        return response()->json([
            'ok' => true,
            'service' => 'laravel-license-server',
        ]);
    }

    public function activate(Request $request): JsonResponse
    {
        if (!$this->authorized($request)) {
            return response()->json(['ok' => false, 'error' => 'Unauthorized'], 401);
        }

        $data = $request->validate([
            'license_key' => ['required', 'string', 'max:120'],
            'machine_fingerprint' => ['required', 'string', 'max:128'],
            'client' => ['nullable', 'string', 'max:50'],
        ]);

        $normalized = strtoupper(trim($data['license_key']));
        $machine = trim($data['machine_fingerprint']);

        $result = DB::transaction(function () use ($normalized, $machine) {
            $license = LicenseKey::query()->where('license_key', $normalized)->lockForUpdate()->first();
            if (!$license) {
                return ['ok' => false, 'error' => 'Key không tồn tại.'];
            }
            if ($license->status !== 'active') {
                return ['ok' => false, 'error' => 'Key đã bị khóa hoặc chưa kích hoạt.'];
            }
            if ($license->expires_at && now()->greaterThan($license->expires_at)) {
                return ['ok' => false, 'error' => 'Key đã hết hạn.'];
            }

            $existing = LicenseActivation::query()
                ->where('license_key_id', $license->id)
                ->where('machine_fingerprint', $machine)
                ->whereNull('deactivated_at')
                ->first();
            if ($existing) {
                return ['ok' => true, 'activation' => $existing, 'license' => $license];
            }

            $activeCount = LicenseActivation::query()
                ->where('license_key_id', $license->id)
                ->whereNull('deactivated_at')
                ->count();
            $maxMachines = max(1, (int) ($license->max_machines ?? config('license.max_machines_per_key', 2)));
            if ($activeCount >= $maxMachines) {
                return ['ok' => false, 'error' => "Key đã dùng đủ {$maxMachines} máy."];
            }

            $activation = LicenseActivation::query()->create([
                'license_key_id' => $license->id,
                'activation_id' => (string) Str::uuid(),
                'machine_fingerprint' => $machine,
                'activated_at' => now(),
                'last_seen_at' => now(),
                'meta' => null,
            ]);

            return ['ok' => true, 'activation' => $activation, 'license' => $license];
        });

        if (!$result['ok']) {
            return response()->json($result, 400);
        }

        /** @var LicenseActivation $activation */
        $activation = $result['activation'];
        /** @var LicenseKey $license */
        $license = $result['license'];

        $activation->update(['last_seen_at' => now()]);

        return response()->json([
            'ok' => true,
            'activation_id' => $activation->activation_id,
            'key_hint' => $license->key_hint ?? substr($license->license_key, -6),
            'daily_limit' => (int) ($license->daily_limit ?: config('license.default_daily_limit', 500)),
            'expires_at' => optional($license->expires_at)->toIso8601String(),
        ]);
    }

    public function deactivate(Request $request): JsonResponse
    {
        if (!$this->authorized($request)) {
            return response()->json(['ok' => false, 'error' => 'Unauthorized'], 401);
        }

        $data = $request->validate([
            'activation_id' => ['required', 'string', 'max:100'],
            'machine_fingerprint' => ['required', 'string', 'max:128'],
        ]);

        $activation = LicenseActivation::query()
            ->where('activation_id', trim($data['activation_id']))
            ->where('machine_fingerprint', trim($data['machine_fingerprint']))
            ->whereNull('deactivated_at')
            ->first();

        if (!$activation) {
            return response()->json(['ok' => false, 'error' => 'Activation không tồn tại hoặc đã hủy.'], 404);
        }

        $activation->update([
            'deactivated_at' => now(),
            'last_seen_at' => now(),
        ]);

        return response()->json(['ok' => true, 'message' => 'Đã hủy kích hoạt.']);
    }

    public function validateActivation(Request $request): JsonResponse
    {
        if (!$this->authorized($request)) {
            return response()->json(['ok' => false, 'error' => 'Unauthorized'], 401);
        }

        $data = $request->validate([
            'activation_id' => ['required', 'string', 'max:100'],
            'machine_fingerprint' => ['required', 'string', 'max:128'],
        ]);

        $activation = LicenseActivation::query()
            ->where('activation_id', trim($data['activation_id']))
            ->where('machine_fingerprint', trim($data['machine_fingerprint']))
            ->whereNull('deactivated_at')
            ->with('licenseKey')
            ->first();

        if (!$activation) {
            return response()->json(['ok' => false, 'error' => 'Activation không hợp lệ.'], 404);
        }

        $license = $activation->licenseKey;
        if (!$license || $license->status !== 'active') {
            return response()->json(['ok' => false, 'error' => 'Key không còn hiệu lực.'], 400);
        }
        if ($license->expires_at && now()->greaterThan($license->expires_at)) {
            return response()->json(['ok' => false, 'error' => 'Key đã hết hạn.'], 400);
        }

        $activation->update(['last_seen_at' => now()]);

        return response()->json([
            'ok' => true,
            'activation_id' => $activation->activation_id,
            'daily_limit' => (int) ($license->daily_limit ?: config('license.default_daily_limit', 500)),
            'expires_at' => optional($license->expires_at)->toIso8601String(),
            'key_hint' => $license->key_hint ?? substr($license->license_key, -6),
        ]);
    }

    private function authorized(Request $request): bool
    {
        $expected = (string) config('license.api_token', '');
        if ($expected === '') {
            return false;
        }
        $header = (string) $request->header('Authorization', '');
        $prefix = 'Bearer ';
        if (!str_starts_with($header, $prefix)) {
            return false;
        }
        $token = trim(substr($header, strlen($prefix)));
        return hash_equals($expected, $token);
    }
}
