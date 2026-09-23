import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";

const features = [
  ["01", "مراجعة لغوية شاملة", "إملاء ونحو وصرف وعلامات ترقيم، مع تفسير واضح للملاحظة بدل التصحيح الصامت."],
  ["02", "السياق قبل الجملة", "يفهم ما قبل العبارة وما بعدها، ويستفيد من الفصل والمستند كاملًا عند الحاجة."],
  ["03", "المستندات الطويلة", "ارفع الملف كاملًا. نَضِيد يتولى التقسيم والمعالجة داخليًا دون نسخ النص على دفعات."],
  ["04", "اتساق المصطلحات", "يتتبع أسماء الجهات والمفاهيم والصيغ المتعددة عبر عشرات أو مئات الصفحات."],
  ["05", "حماية المعنى والحقائق", "يحمي الأرقام والتواريخ والأسماء والاقتباسات والنفي من التغيير غير المقصود أثناء التحرير."],
  ["06", "صياغة محسوبة", "يحسن الركاكة والتكرار والحشو بدرجات تدخل مختلفة مع إبقاء القرار النهائي للكاتب."]
];

const steps = [
  ["01", "ارفع المستند", "DOCX كاملًا دون تقسيم يدوي أو نقل الفصول واحدًا واحدًا."],
  ["02", "نقرأ بنيته", "نَضِيد يتعرف على الفصول والعناوين والفقرات والمصطلحات والحقائق."],
  ["03", "تظهر الملاحظات", "ملاحظات لغوية أولًا، ثم مراجعات أعمق للسياق والاتساق تدريجيًا."],
  ["04", "أنت تقرر", "اقبل أو ارفض كل تعديل، ثم صدّر نسخة جديدة مع بقاء الأصل محفوظًا."]
];

export default function HomePage() {
  return (
    <>
      <SiteHeader />
      <main>
        <section className="hero">
          <div className="shell hero-grid">
            <div>
              <span className="eyebrow">محرر عربي للمستند، لا للجملة وحدها</span>
              <h1>نص أدق.<br /><em>سياق أتم.</em></h1>
              <p className="hero-lead">
                نَضِيد يراجع اللغة والصياغة والسياق والاتساق في المستندات العربية
                الطويلة، ويحمي المعنى والحقائق أثناء التحرير.
              </p>
              <div className="hero-actions">
                <Link href="/upload" className="button button-primary">ارفع مستندك <span aria-hidden="true">←</span></Link>
                <Link href="/editor" className="button button-secondary">استعرض المحرر</Link>
              </div>
              <div className="hero-proof">
                <span><i /> لا حاجة لتقسيم المستند يدويًا</span>
                <span><i /> يبقى الأصل محفوظًا</span>
                <span><i /> القرار النهائي لك</span>
              </div>
            </div>

            <div className="editor-preview" aria-label="معاينة محرر نَضِيد">
              <div className="preview-topbar">
                <span className="preview-dot" /><span className="preview-dot" /><span className="preview-dot" />
                <span className="preview-document-name">دراسة تطوير المنظومة.docx</span>
              </div>
              <div className="preview-body">
                <div className="preview-page">
                  <article className="preview-paper">
                    <h3>الإطار العام للمشروع</h3>
                    <p>يهدف المشروع إلى بناء نموذج تشغيلي أكثر كفاءة، مع المحافظة على وضوح المسؤوليات وتكامل الأدوار بين الأطراف ذات العلاقة.</p>
                    <p>وقد أظهرت الدراسة أن تطوير الإجراءات <span className="issue-word">يساهم في تحسين من مستوى</span> الأداء، ويحد من التكرار في دورة العمل.</p>
                    <p>وتبلغ التكلفة التقديرية للمشروع 38,771,251 ريال، وهي قيمة محفوظة أثناء أي إعادة صياغة يقترحها المحرر.</p>
                  </article>
                </div>
                <aside className="preview-sidebar">
                  <h4>المراجعة</h4>
                  <div className="mini-issue"><strong>صياغة</strong><span>حرف الجر «من» زائد في هذا السياق.</span></div>
                  <div className="mini-issue"><strong>حماية حقيقة</strong><span>القيمة 38,771,251 ريال محمية من التغيير.</span></div>
                  <div className="mini-issue"><strong>اتساق</strong><span>هناك صيغتان لاسم المصطلح نفسه في المستند.</span></div>
                </aside>
              </div>
              <div className="preview-status">✓ حماية المعنى فعّالة</div>
            </div>
          </div>
        </section>

        <section className="section section-muted" id="capabilities">
          <div className="shell">
            <div className="section-heading">
              <span className="eyebrow">أبعد من التدقيق التقليدي</span>
              <h2>يراجع النص بوصفه مستندًا مترابطًا.</h2>
              <p>الإملاء والنحو أساس ضروري، لكن القيمة الحقيقية تظهر حين يتذكر المحرر ما قيل في الصفحات السابقة ويعرف ما الذي لا ينبغي تغييره.</p>
            </div>
            <div className="feature-grid">
              {features.map(([n, title, body]) => (
                <article className="feature-card" key={n}>
                  <span className="feature-number">{n}</span>
                  <h3>{title}</h3><p>{body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="section">
          <div className="shell">
            <div className="long-doc-banner">
              <div>
                <h2>المستند كاملًا، لا 5,000 حرف كل مرة.</h2>
                <p>نَضِيد يقسم المستند تقنيًا في الخلفية، ويبني له ذاكرة واحدة؛ لذلك لا يضطر الكاتب إلى تمزيق السياق كي يطابق حدود أداة التدقيق.</p>
              </div>
              <div className="banner-points">
                <span>كتاب أو بحث أو تقرير طويل</span>
                <span>ذاكرة للمصطلحات والحقائق</span>
                <span>إعادة فحص الأجزاء المتغيرة فقط</span>
              </div>
            </div>
          </div>
        </section>

        <section className="section" id="how">
          <div className="shell">
            <div className="section-heading">
              <span className="eyebrow">كيف يعمل نَضِيد؟</span>
              <h2>أربع خطوات بين الملف والنسخة المنقحة.</h2>
            </div>
            <div className="steps">
              {steps.map(([n, title, body]) => (
                <article className="step" key={n}><b>{n}</b><h3>{title}</h3><p>{body}</p></article>
              ))}
            </div>
          </div>
        </section>

        <section className="cta">
          <div className="shell">
            <div className="cta-card">
              <h2>ابدأ بالمستند كما هو.</h2>
              <p>لا تنسخ الفصول ولا تقسم الصفحات. ارفع ملفك، واترك لنَضِيد مهمة فهم بنيته قبل أن يبدأ التصحيح.</p>
              <Link href="/upload" className="button button-primary">ارفع مستندًا</Link>
            </div>
          </div>
        </section>
      </main>
      <footer className="site-footer"><div className="shell footer-inner"><span>نَضِيد — محرر العربية الذكي</span><span>نص أدق. سياق أتم.</span></div></footer>
    </>
  );
}
