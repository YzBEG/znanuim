from django.contrib import admin, messages
from django.utils import timezone

from communications.models import Notification, create_notification
from payments.services import complete_paid_lesson
from .models import AvailabilitySlot, Dispute, LessonOrder, LessonSession


@admin.register(AvailabilitySlot)
class AvailabilitySlotAdmin(admin.ModelAdmin):
    list_display = ('tutor', 'start_at', 'end_at', 'is_booked')
    list_filter = ('is_booked', 'start_at')
    search_fields = ('tutor__user__username', 'tutor__user__first_name', 'tutor__user__last_name')


@admin.register(LessonOrder)
class LessonOrderAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'student',
        'tutor',
        'status',
        'price',
        'tutor_completed_at',
        'student_confirmed_at',
        'cancelled_at',
        'created_at',
    )
    list_filter = ('status', 'created_at', 'tutor_completed_at', 'student_confirmed_at')
    search_fields = ('student__username', 'tutor__username')
    readonly_fields = ('created_at', 'updated_at', 'tutor_completed_at', 'student_confirmed_at', 'cancelled_at')


@admin.register(LessonSession)
class LessonSessionAdmin(admin.ModelAdmin):
    list_display = ('order', 'room_name', 'started_at', 'ended_at')
    search_fields = ('room_name', 'order__id')


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display = ('order', 'initiated_by', 'decision', 'created_at', 'resolved_at')
    list_filter = ('decision', 'created_at', 'resolved_at')
    search_fields = ('order__id', 'initiated_by__username', 'order__student__username', 'order__tutor__username')
    readonly_fields = ('created_at', 'resolved_at')
    actions = ('pay_tutor_for_dispute', 'cancel_without_payment')

    @admin.action(description='Решить спор: оплатить репетитору')
    def pay_tutor_for_dispute(self, request, queryset):
        paid_count = 0
        for dispute in queryset.select_related('order', 'order__student', 'order__tutor'):
            order = dispute.order
            if order.status != LessonOrder.Status.IN_DISPUTE:
                self.message_user(
                    request,
                    f'Заказ #{order.id} не находится в споре.',
                    level=messages.WARNING,
                )
                continue

            try:
                complete_paid_lesson(order)
            except ValueError as error:
                self.message_user(request, f'Заказ #{order.id}: {error}', level=messages.ERROR)
                continue

            order.status = LessonOrder.Status.COMPLETED
            order.save(update_fields=['status', 'updated_at'])
            dispute.decision = Dispute.Decision.PAY_TUTOR
            dispute.resolved_at = timezone.now()
            dispute.save(update_fields=['decision', 'resolved_at'])

            create_notification(
                recipient=order.student,
                title='Спор по уроку закрыт',
                body='Администратор подтвердил проведение урока. Оплата списана согласно правилам платформы.',
                url='',
                kind=Notification.Kind.LESSON,
            )
            create_notification(
                recipient=order.tutor,
                title='Спор по уроку закрыт',
                body='Администратор подтвердил проведение урока. Выплата начислена с учётом комиссии платформы.',
                url='',
                kind=Notification.Kind.LESSON,
            )
            paid_count += 1

        if paid_count:
            self.message_user(request, f'Оплачено спорных уроков: {paid_count}.', level=messages.SUCCESS)

    @admin.action(description='Решить спор: отменить без оплаты')
    def cancel_without_payment(self, request, queryset):
        cancelled_count = 0
        for dispute in queryset.select_related('order', 'order__student', 'order__tutor', 'order__slot'):
            order = dispute.order
            if order.status != LessonOrder.Status.IN_DISPUTE:
                self.message_user(
                    request,
                    f'Заказ #{order.id} не находится в споре.',
                    level=messages.WARNING,
                )
                continue

            order.status = LessonOrder.Status.CANCELLED
            order.cancelled_by = request.user
            order.cancelled_at = timezone.now()
            if order.slot_id:
                order.slot.is_booked = False
                order.slot.save(update_fields=['is_booked'])
            order.save(update_fields=['status', 'cancelled_by', 'cancelled_at', 'updated_at'])
            dispute.decision = Dispute.Decision.REFUND_STUDENT
            dispute.resolved_at = timezone.now()
            dispute.save(update_fields=['decision', 'resolved_at'])

            create_notification(
                recipient=order.student,
                title='Спор по уроку закрыт',
                body='Администратор отменил урок. Оплата по нему не списана.',
                url='',
                kind=Notification.Kind.LESSON,
            )
            create_notification(
                recipient=order.tutor,
                title='Спор по уроку закрыт',
                body='Администратор отменил урок. Выплата по нему не начислена.',
                url='',
                kind=Notification.Kind.LESSON,
            )
            cancelled_count += 1

        if cancelled_count:
            self.message_user(request, f'Отменено спорных уроков без оплаты: {cancelled_count}.', level=messages.SUCCESS)
