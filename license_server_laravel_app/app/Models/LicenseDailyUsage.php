<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class LicenseDailyUsage extends Model
{
    protected $fillable = [
        'license_activation_id',
        'usage_day',
        'used_total',
        'last_reported_at',
    ];

    protected $casts = [
        'usage_day' => 'date',
        'last_reported_at' => 'datetime',
    ];

    public function activation(): BelongsTo
    {
        return $this->belongsTo(LicenseActivation::class, 'license_activation_id');
    }
}
