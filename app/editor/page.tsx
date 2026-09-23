import Link from "next/link";
import { Brand } from "@/components/SiteHeader";

const outline = [
  ["active", "مقدمة الدراسة"],
  ["sub", "خلفية المشروع"],
  ["sub", "المشكلة"],
  ["", "الإطار العام"],
  ["sub", "النموذج التشغيلي"],
  ["", "التحليل المالي"],
  ["", "المخاطر"],
  ["", "الخاتمة"]
];

export default function EditorPage() {
  return (
    <main className="editor-app">
      <header className="editor-header">
        <Brand />
        <span className="editor-doc-title">دراسة تطوير المنظومة.docx</span>
        <div className="editor-header-actions">
          <Link href="/upload" className="button button-small button-secondary">مستند جديد</Link>
          <button className="button button-small button-primary">تصدير</button>
        </div>
      </header>

      <div className="editor-layout">
        <aside className="outline-panel">
          <div className="panel-head">
            <h3>هيكل المستند</h3>
            <span className="panel-count">8</span>
          </div>
          <div className="outline-content">
            {outline.map(([kind, label], index) => (
              <div className={"outline-item " + kind} key={label + index}>
                <span>{kind === "sub" ? "ـ" : "•"}</span>
                {label}
              </div>
            ))}
          </div>
        </aside>

        <section className="document-stage">
          <article className="document-sheet">
            <h1>مقدمة الدراسة</h1>
            <p>
              تهدف هذه الدراسة إلى تقديم إطار متكامل لتطوير المنظومة التشغيلية،
              مع التركيز على رفع كفاءة الإجراءات وتحسين مستوى التنسيق بين الأطراف
              ذات العلاقة.
            </p>
            <p>
              وقد أظهرت المراجعة الأولية أن تطوير الإجراءات{" "}
              <span className="mark-grammar">يساهم في تحسين من مستوى</span>{" "}
              الأداء، كما يسهم في تقليص التكرار وتحسين وضوح المسؤوليات.
            </p>

            <h2>خلفية المشروع</h2>
            <p>
              انطلقت فكرة المشروع من الحاجة إلى توحيد عدد من المسارات المتفرقة
              ضمن نموذج أكثر اتساقًا. ويتكون النموذج من أربعة محاور رئيسية،
              ترتبط فيما بينها بعلاقات تشغيلية واضحة.
            </p>
            <p>
              وتبلغ التكلفة التقديرية للمشروع{" "}
              <span className="mark-style">38,771,251 ريال</span>، وقد صُنفت
              هذه القيمة ضمن الحقائق المحمية بحيث لا يجوز أن تتغير بسبب تحسين
              الصياغة أو اختصار الفقرة.
            </p>
            <p>
              كما يعتمد المستند مصطلح «الذكاء الاصطناعي» بوصفه الصيغة الأساسية،
              بينما رصد نَضِيد استخدام صيغة أخرى في فصل لاحق ويعرضها كملاحظة
              اتساق لا كخطأ إملائي مباشر.
            </p>
          </article>
        </section>

        <aside className="review-panel">
          <div className="panel-head">
            <h3>المراجعة</h3>
            <span className="panel-count">12</span>
          </div>

          <div className="review-tabs">
            <button className="review-tab active">الكل</button>
            <button className="review-tab">لغة</button>
            <button className="review-tab">صياغة</button>
            <button className="review-tab">اتساق</button>
          </div>

          <div className="review-list">
            <article className="review-card">
              <span className="review-card-type">صياغة · ثقة عالية</span>
              <h4>حرف جر زائد</h4>
              <p>وجود «من» هنا يضعف سلامة التركيب ولا يضيف معنى.</p>
              <div className="review-diff">
                <div className="old-text">تحسين من مستوى الأداء</div>
                <div className="new-text">تحسين مستوى الأداء</div>
              </div>
              <div className="review-actions">
                <button className="accept">قبول</button>
                <button>رفض</button>
              </div>
            </article>

            <article className="review-card">
              <span className="review-card-type">حماية معنى</span>
              <h4>قيمة مالية محمية</h4>
              <p>
                القيمة 38,771,251 ريال محفوظة في Fact Lock ولن يسمح نَضِيد
                بتغييرها ضمن إعادة الصياغة.
              </p>
            </article>

            <article className="review-card">
              <span className="review-card-type">اتساق المستند</span>
              <h4>صياغتان لمصطلح واحد</h4>
              <p>
                ورد «الذكاء الصناعي» في موضع آخر بينما الصيغة الأكثر استخدامًا
                هنا هي «الذكاء الاصطناعي».
              </p>
              <div className="review-actions">
                <button className="accept">توحيد المصطلح</button>
                <button>تجاهل</button>
              </div>
            </article>
          </div>
        </aside>
      </div>

      <div className="editor-statusbar">
        <span className="status-good">● السياق متصل</span>
        <span>12 ملاحظة</span>
        <span>3 حقائق محمية</span>
        <span>المراجعة العميقة تعمل</span>
      </div>
    </main>
  );
}
