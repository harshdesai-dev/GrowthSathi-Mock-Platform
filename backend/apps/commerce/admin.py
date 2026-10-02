from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from apps.exams.admin import OwnerAdmin, ProtectedInline

from .models import (
    MockAccessGrant,
    MockOffer,
    MockOfferItem,
    Order,
    OrderItem,
    Payment,
    PaymentWebhookEvent,
)
from .services import set_offer_active


class OfferItemInline(ProtectedInline):
    model = MockOfferItem

    def is_locked(self, obj):
        return obj and obj.active


@admin.register(MockOffer)
class OfferAdmin(OwnerAdmin):
    list_display = ("name", "offer_type", "price_paise", "active", "sales_start_at", "sales_end_at")
    list_filter = ("offer_type", "active")
    inlines = [OfferItemInline]
    readonly_fields = ("created_at", "updated_at", "active")
    actions = ["activate", "deactivate"]

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.active:
            return tuple(field.name for field in self.model._meta.fields)
        return super().get_readonly_fields(request, obj)

    def change_activation(self, request, queryset, active):
        for offer in queryset:
            try:
                set_offer_active(offer.pk, active, actor=request.user)
            except ValidationError as exc:
                self.message_user(request, "; ".join(exc.messages), messages.ERROR)

    @admin.action(description="Activate validated offers")
    def activate(self, request, queryset):
        self.change_activation(request, queryset, True)

    @admin.action(description="Deactivate offers for editing")
    def deactivate(self, request, queryset):
        self.change_activation(request, queryset, False)


class ReadOnlyAdmin(OwnerAdmin):
    def has_add_permission(self, request):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


@admin.register(Order)
class OrderAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "student",
        "offer_name_snapshot",
        "total_amount_paise",
        "status",
        "review_required",
        "created_at",
    )
    list_filter = ("status", "offer_type_snapshot", "review_required", "created_at")
    search_fields = ("gateway_order_id", "student__email", "id")


@admin.register(Payment)
class PaymentAdmin(ReadOnlyAdmin):
    list_display = ("gateway_payment_id", "order", "amount_paise", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("gateway_payment_id", "order__gateway_order_id")
    exclude = ("gateway_signature",)

    def get_readonly_fields(self, request, obj=None):
        return tuple(
            field
            for field in super().get_readonly_fields(request, obj)
            if field != "gateway_signature"
        )


@admin.register(MockAccessGrant)
class AccessAdmin(ReadOnlyAdmin):
    list_display = ("student", "mock_test", "status", "granted_at")
    list_filter = ("status", "mock_test", "granted_at")


@admin.register(PaymentWebhookEvent)
class WebhookAdmin(ReadOnlyAdmin):
    list_display = ("gateway_event_id", "event_type", "processing_status", "received_at")
    list_filter = ("event_type", "processing_status", "received_at")


admin.site.register(OrderItem, ReadOnlyAdmin)
admin.site.register(MockOfferItem, ReadOnlyAdmin)
