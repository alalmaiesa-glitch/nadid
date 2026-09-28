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


const plans = [
  {
    name: "مجاني",
    price: "0",
    period: "ر.س / شهر",
    annual: "بدون بطاقة دفع",
    characters: "50,000",
    description: "للتجربة والاستخدام الخفيف.",
    features: ["المراجعة اللغوية الأساسية", "رفع مستندات DOCX", "الاحتفاظ بالأصل"],
    ads: true,
    href: "/upload",
    cta: "ابدأ مجانًا"
  },
  {
    name: "أساسي",
    price: "29",
    period: "ر.س / شهر",
    annual: "290 ر.س سنويًا · شهران دون تكلفة",
    characters: "500,000",
    description: "لمن يراجع تقارير وبحوثًا ومستندات طويلة بانتظام.",
    features: ["كل مزايا المجاني بدون إعلانات", "مراجعة السياق والاتساق عبر المستند", "تحسين الصياغة وتصدير النسخ المنقحة"],
    featured: true,
    href: "/documents",
    cta: "اختر الأساسي"
  },
  {
    name: "احترافي",
    price: "59",
    period: "ر.س / شهر",
    annual: "590 ر.س سنويًا · شهران دون تكلفة",
    characters: "2,000,000",
    description: "للمستندات الحساسة والمراجعة الأعمق.",
    features: ["كل مزايا الأساسي", "المراجعة العميقة للسياق", "حماية الحقائق والأرقام وسجل النسخ"],
    href: "/documents",
    cta: "اختر الاحترافي"
  }
];

const topupPacks = [
  { chars: "100,000", price: "9", note: "للاحتياج السريع" },
  { chars: "500,000", price: "29", note: "للعمل الإضافي المتوسط" },
  { chars: "1,000,000", price: "49", note: "للمستندات الكبيرة" }
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


        <section className="pricing-section" id="pricing">
          <div className="shell">
            <div className="pricing-heading">
              <span className="eyebrow">باقات نَضِيد</span>
              <h2>ابدأ مجانًا، وترقَّ عندما تحتاج مراجعة أعمق.</h2>
              <p>أسعار إطلاق للمستخدم الفردي، مع بقاء الباقة المجانية متاحة بوجود إعلانات Google بعد اعتماد الموقع للإعلانات.</p>
            </div>
            <div className="pricing-grid">
              {plans.map((plan) => (
                <article className={"pricing-card" + (plan.featured ? " pricing-card-featured" : "")} key={plan.name}>
                  {plan.featured && <span className="pricing-badge">الأكثر توازنًا</span>}
                  <h3>{plan.name}</h3>
                  <p className="pricing-description">{plan.description}</p>
                  <div className="pricing-price"><strong>{plan.price}</strong><span>{plan.period}</span></div>
                  <div className="pricing-annual">{plan.annual}</div>
                  <div className="pricing-character-quota"><strong>{plan.characters}</strong><span>حرف شهريًا</span></div>
                  <ul>{plan.features.map((feature) => <li key={feature}>{feature}</li>)}</ul>
                  {plan.ads && <div className="pricing-ad-note">تتضمن هذه الباقة إعلانات.</div>}
                  <Link href={plan.href} className={"button " + (plan.featured ? "button-primary" : "button-secondary")}>{plan.cta}</Link>
                </article>
              ))}
            </div>
            <p className="pricing-footnote">أسعار الإطلاق قابلة للمراجعة بعد قياس تكلفة المعالجة والاستخدام الفعلي.</p>
          </div>
        </section>


        <section className="topup-section">
          <div className="shell">
            <div className="topup-card">
              <div className="topup-copy">
                <span className="eyebrow">رصيد إضافي</span>
                <h2>نفد رصيدك قبل نهاية الشهر؟</h2>
                <p>يمكنك إضافة أحرف إلى رصيدك دون تغيير باقتك أو انتظار موعد التجديد الشهري.</p>
              </div>
              <div className="topup-grid">
                {topupPacks.map((pack) => (
                  <article className="topup-pack" key={pack.chars}>
                    <strong>{pack.chars}</strong>
                    <span>حرف إضافي</span>
                    <b>{pack.price} ر.س</b>
                    <small>{pack.note}</small>
                    <Link href="/documents" className="button button-secondary">إضافة رصيد</Link>
                  </article>
                ))}
              </div>
              <p className="topup-note">الرصيد الإضافي لا يغيّر موعد تجديد الباقة، ويُستهلك بعد نفاد الرصيد الشهري.</p>
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
