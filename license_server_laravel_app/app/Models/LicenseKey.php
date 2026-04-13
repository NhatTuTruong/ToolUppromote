<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class LicenseKey extends Model
{
    protected $fillable = [
        'license_key',
        'key_hint',
        'status',
        'daily_limit',
        'max_machines',
        'expires_at',
        'notes',
    ];

    protected $casts = [
        'expires_at' => 'datetime',
    ];

    public function activations(): HasMany
    {
        return $this->hasMany(LicenseActivation::class);
    }
}
