# Payment & Subscription Activation Integrity V1

## الهدف

فصل حقيقة الدفع عن منح الاستحقاق. وجود طلب دفع أو provider reference لا يمنح اشتراكًا أو رصيدًا.

## تفعيل الاشتراك

activate_subscription_from_payment لا ينجح إلا إذا:
- payment موجودة ومملوكة لمستخدم.
- status = paid.
- purpose = subscription.
- paid_at موجود.
- الخطة موجودة ونشطة وليست Free.
- المبلغ والعملة يطابقان الخطة.
- مدة الاشتراك تُشتق من paid_at ومن billing_interval داخل الخطة، لا من مدخلات العميل.
- payment_id لا يمكن استخدامه لاشتراك آخر.

إعادة نفس عملية التفعيل تعيد الاشتراك السابق بدون إنشاء صف جديد.

عند تفعيل اشتراك مدفوع جديد، يُغلق الاشتراك النشط السابق للمستخدم قبل إنشاء الجديد.

## تفعيل Top-up

activate_topup_from_payment يفرض:
- status = paid.
- purpose = credit_topup.
- paid_at موجود.
- pack نشط.
- المبلغ والعملة يطابقان pack.
- عدد الأحرف يأتي من credit_packs وليس من العميل.
- payment_id لا يستخدم لرصيد إضافي ثانٍ.

## الصلاحيات

RPCs الخاصة بالتفعيل متاحة لـ service_role فقط. المستخدم المصادق لا يستطيع منح نفسه اشتراكًا أو رصيدًا.

## العلاقة مع مزود الدفع

هذه الطبقة Provider-neutral. عند ربط Moyasar لاحقًا، Webhook الموثق يحدّث payment إلى paid ثم يستدعي RPC التفعيل. قواعد الاستحقاق نفسها تبقى داخل PostgreSQL.
