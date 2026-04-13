<?php

use App\Http\Controllers\Admin\AuthController;
use App\Http\Controllers\Admin\LicenseManagementController;
use Illuminate\Support\Facades\Route;

Route::get('/', function () {
    return redirect()->route('admin.dashboard');
});

Route::get('/admin/login', [AuthController::class, 'showLogin'])->name('admin.login');
Route::post('/admin/login', [AuthController::class, 'login'])->name('admin.login.submit');
Route::post('/admin/logout', [AuthController::class, 'logout'])->name('admin.logout');

Route::middleware('license.admin')->group(function (): void {
    Route::get('/admin', [LicenseManagementController::class, 'dashboard'])->name('admin.dashboard');
    Route::post('/admin/keys', [LicenseManagementController::class, 'storeKey'])->name('admin.keys.store');
    Route::post('/admin/keys/import', [LicenseManagementController::class, 'bulkImport'])->name('admin.keys.import');
    Route::post('/admin/keys/{id}', [LicenseManagementController::class, 'updateKey'])->name('admin.keys.update');
    Route::post('/admin/activations/{id}/revoke', [LicenseManagementController::class, 'revokeActivation'])->name('admin.activations.revoke');
});
