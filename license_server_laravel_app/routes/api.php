<?php

use App\Http\Controllers\Api\LicenseController;
use Illuminate\Support\Facades\Route;

Route::prefix('v1/licenses')->group(function () {
    Route::get('/health', [LicenseController::class, 'health']);
    Route::post('/activate', [LicenseController::class, 'activate']);
    Route::post('/deactivate', [LicenseController::class, 'deactivate']);
    Route::post('/validate', [LicenseController::class, 'validateActivation']);
    Route::post('/usage/sync', [LicenseController::class, 'syncUsage']);
});
