# Plan Entitlement Enforcement V1

هذه الطبقة تفرض صلاحيات الباقة من جهة الخادم، لا الواجهة فقط.

- Free: لا Context Review ولا Deep Review ولا Export.
- Basic: Context Review + Export، بلا Deep Review.
- Pro: Context Review + Deep Review + Export.
- قراءة نتائج Deep Review السابقة وقائمة النسخ تبقى متاحة بعد تغيير الخطة؛ الحظر يطبق على إنشاء عمل مدفوع جديد.
- Fact Lock الداخلي يبقى حاجز سلامة ولا يُعطل بحسب الخطة.

المسارات المحمية:
- Context search -> context_review
- Deep Review POST -> deep_review
- Derived Version POST -> export
- Export GET -> export

الحارس يعيد 403 مع PLAN_ENTITLEMENT_REQUIRED، ويفشل مغلقًا في Production عند تعذر خدمة الاستحقاقات.
