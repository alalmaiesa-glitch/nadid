# Billing-Cycle Aligned Character Quota Windows V1

## المشكلة

كان خصم الأحرف يستخدم بداية الشهر الميلادي كنافذة للحصة لجميع المستخدمين:

`date_trunc('month', clock_timestamp())`

هذا صحيح للمستخدم المجاني، لكنه غير صحيح للاشتراك المدفوع الذي تبدأ دورته من `paid_at`. مثال: اشتراك يبدأ في 30 سبتمبر كان يستطيع استهلاك حصته ثم الحصول على حصة جديدة في 1 أكتوبر، رغم أن دورة الاشتراك نفسها ما زالت مستمرة.

## السياسة الجديدة

- **Free**: تبقى نافذة الحصة من أول الشهر الميلادي، لعدم وجود دورة دفع.
- **Monthly paid plan**: تبدأ نافذة الحصة من `subscription.current_period_start`.
- **Annual paid plan**: تظل الحصة **شهرية**، لكن كل نافذة شهرية مرتبطة بذكرى يوم بدء الاشتراك داخل السنة، وليست بأول الشهر الميلادي.
- التجديد المستقبلي المكدّس لا يمنح حصة قبل وصول `current_period_start` الخاصة به.
- الخصم الفعلي يبقى ذريًا وIdempotent ويستهلك included قبل Top-up كما في طبقة Usage Quota السابقة.

## الأمان

تمت إضافة:

`resolve_character_quota_window(user_id)`

وهي:

- `SECURITY DEFINER`
- محجوبة عن `anon` و`authenticated`
- متاحة فقط لـ `service_role`
- لا تسمح للعميل باختيار نافذة أو خطة يدويًا.

## Regression Guards

- Paid monthly subscription crossing a calendar boundary does not receive a duplicate included allowance.
- Annual plan receives monthly anniversary-aligned windows.
- Queued future renewal cannot become effective early.
- Free-plan behavior remains calendar-month based.
- Privileged RPC permissions remain fail-closed.
