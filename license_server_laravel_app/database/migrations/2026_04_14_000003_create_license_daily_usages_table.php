<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        Schema::create('license_daily_usages', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('license_activation_id')->constrained('license_activations')->cascadeOnDelete();
            $table->date('usage_day');
            $table->unsignedInteger('used_total')->default(0);
            $table->timestamp('last_reported_at')->nullable();
            $table->timestamps();

            $table->unique(['license_activation_id', 'usage_day'], 'license_daily_usages_activation_day_unique');
            $table->index('usage_day');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('license_daily_usages');
    }
};
