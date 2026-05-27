from django.contrib import admin

from .models import Transaction, Wallet, WithdrawalRequest


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('balance',)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'type', 'amount', 'created_at')
    list_filter = ('type', 'created_at')
    search_fields = ('user__username', 'external_payment_id')
    readonly_fields = ('created_at',)


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'tutor', 'amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('tutor__username', 'requisites')
    readonly_fields = ('created_at',)
