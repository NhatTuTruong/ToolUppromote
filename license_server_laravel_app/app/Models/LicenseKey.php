<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class LicenseKey extends Model
{
    public const DEFAULT_ALLOWED_SOURCES = ['uppromote', 'goaffpro'];

    public const SUPPORTED_SOURCES = ['uppromote', 'goaffpro', 'refersion'];

    protected $fillable = [
        'license_key',
        'key_hint',
        'status',
        'daily_limit',
        'max_machines',
        'allowed_sources',
        'expires_at',
        'notes',
    ];

    protected $casts = [
        'expires_at' => 'datetime',
        'allowed_sources' => 'array',
    ];

    public function activations(): HasMany
    {
        return $this->hasMany(LicenseActivation::class);
    }

    public function normalizedAllowedSources(): array
    {
        $raw = $this->allowed_sources;
        if (!is_array($raw) || $raw === []) {
            return self::DEFAULT_ALLOWED_SOURCES;
        }

        $normalized = [];
        foreach ($raw as $source) {
            $s = strtolower(trim((string) $source));
            if ($s !== '' && in_array($s, self::SUPPORTED_SOURCES, true)) {
                $normalized[] = $s;
            }
        }

        $normalized = array_values(array_unique($normalized));

        return $normalized !== [] ? $normalized : self::DEFAULT_ALLOWED_SOURCES;
    }
}
